from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.simulation.interfaces.rest_api import router
from app.simulation.models import ClockSpec, SimulationDefinition, SourceBinding, TargetBinding
from app.simulation.runtime import SimulationManager


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_hold_last_keeps_api_live_without_republishing_final_frame(tmp_path) -> None:
    async def run() -> None:
        manager = SimulationManager(tmp_path / "runtime.json")
        definition = SimulationDefinition(
            simulation_id="sim-api-hold",
            name="Finite API fixture",
            source=SourceBinding(
                kind="inline",
                config={
                    "rows": [
                        {"OrderId": "A-1", "Temperature": 20.0},
                        {"OrderId": "A-2", "Temperature": 21.0},
                    ]
                },
            ),
            clock=ClockSpec(mode="fixed_rate", frequency_hz=100.0),
            loop_mode="hold_last",
            targets=[TargetBinding(
                target_id="orders-api",
                kind="api",
                config={
                    "method": "GET",
                    "path": "/held-orders",
                    "response_mode": "history",
                    "fields": "OrderId,Temperature",
                    "include_system_fields": False,
                    "history_size": 10,
                    "default_page_size": 10,
                    "max_page_size": 10,
                },
            )],
        )
        await manager.create(definition)
        await manager.start(definition.simulation_id)

        for _ in range(200):
            status = manager.status(definition.simulation_id)
            if status.emitted_count == 2 and status.source_position == 2 and status.targets[0].published_frames == 2:
                break
            await asyncio.sleep(0.005)
        else:
            raise AssertionError("Finite API fixture did not publish both source rows.")

        await asyncio.sleep(0.08)
        held = manager.status(definition.simulation_id)
        assert held.state == "running"
        assert held.emitted_count == 2
        assert held.targets[0].published_frames == 2

        response = _client().get("/sim-api/held-orders")
        assert response.status_code == 200
        assert response.json() == [
            {"OrderId": "A-1", "Temperature": 20.0},
            {"OrderId": "A-2", "Temperature": 21.0},
        ]

        await manager.stop(definition.simulation_id)
        assert manager.status(definition.simulation_id).state == "stopped"
        assert _client().get("/sim-api/held-orders").status_code == 404
        await manager.shutdown()

    asyncio.run(run())
