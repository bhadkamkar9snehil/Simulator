from __future__ import annotations

import asyncio

from app.simulation.models import ClockSpec, SimulationDefinition, SourceBinding, TargetBinding, WorldDefinition
from app.simulation.runtime import SimulationManager


def _inline_definition(simulation_id: str, start: int) -> SimulationDefinition:
    return SimulationDefinition(
        simulation_id=simulation_id,
        name=simulation_id,
        source=SourceBinding(
            kind="inline",
            config={
                "rows": [
                    {"timestamp": "2026-01-01T00:00:00Z", "value": start},
                    {"timestamp": "2026-01-01T00:00:01Z", "value": start + 1},
                    {"timestamp": "2026-01-01T00:00:02Z", "value": start + 2},
                ]
            },
        ),
        clock=ClockSpec(mode="fixed_rate", frequency_hz=1000.0),
        loop_mode="once",
        targets=[TargetBinding(target_id=f"{simulation_id}-memory", kind="memory")],
    )


async def _wait_completed(manager: SimulationManager, *simulation_ids: str) -> None:
    for _ in range(200):
        states = [manager.status(simulation_id).state for simulation_id in simulation_ids]
        if all(state == "completed" for state in states):
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"Simulations did not complete: {states}")


def test_multiple_simulations_run_independently(tmp_path) -> None:
    async def run() -> None:
        manager = SimulationManager(tmp_path / "runtime.json")
        left = _inline_definition("sim-left", 10)
        right = _inline_definition("sim-right", 100)

        await manager.create(left)
        await manager.create(right)
        await asyncio.gather(manager.start(left.simulation_id), manager.start(right.simulation_id))
        await _wait_completed(manager, left.simulation_id, right.simulation_id)

        left_snapshot = manager.snapshot(left.simulation_id)
        right_snapshot = manager.snapshot(right.simulation_id)

        assert left_snapshot["status"]["emitted_count"] == 3
        assert right_snapshot["status"]["emitted_count"] == 3
        assert left_snapshot["frame"]["values"]["value"]["value"] == 12
        assert right_snapshot["frame"]["values"]["value"]["value"] == 102
        await manager.shutdown()

    asyncio.run(run())


def test_world_groups_existing_simulations_and_persists(tmp_path) -> None:
    async def run() -> None:
        state_path = tmp_path / "runtime.json"
        manager = SimulationManager(state_path)
        one = _inline_definition("sim-one", 1)
        two = _inline_definition("sim-two", 20)
        await manager.create(one)
        await manager.create(two)

        world = WorldDefinition(world_id="world-plant-a", name="Plant A", simulation_ids=["sim-one", "sim-two"])
        await manager.create_world(world)

        restored = SimulationManager(state_path)
        assert {item.simulation_id for item in restored.list_definitions()} == {"sim-one", "sim-two"}
        assert restored.worlds["world-plant-a"].simulation_ids == ["sim-one", "sim-two"]
        await manager.shutdown()
        await restored.shutdown()

    asyncio.run(run())


def test_duplicate_target_ids_are_rejected() -> None:
    try:
        SimulationDefinition(
            simulation_id="duplicate-targets",
            source=SourceBinding(kind="inline", config={"rows": [{"value": 1}]}),
            targets=[
                TargetBinding(target_id="same", kind="memory"),
                TargetBinding(target_id="same", kind="memory"),
            ],
        )
    except ValueError as exc:
        assert "Target ids must be unique" in str(exc)
    else:
        raise AssertionError("Duplicate target ids should fail validation.")


def test_http_target_keeps_last_frame_in_simulation_snapshot(tmp_path) -> None:
    async def run() -> None:
        manager = SimulationManager(tmp_path / "runtime.json")
        definition = SimulationDefinition(
            simulation_id="sim-http",
            source=SourceBinding(kind="inline", config={"rows": [{"value": 7}, {"value": 8}]}),
            clock=ClockSpec(frequency_hz=1000.0),
            loop_mode="once",
            targets=[TargetBinding(target_id="http-main", kind="http")],
        )
        await manager.create(definition)
        await manager.start(definition.simulation_id)
        await _wait_completed(manager, definition.simulation_id)

        frame = manager.http_frame(definition.simulation_id, "http-main")
        assert frame is not None
        assert frame.values["value"].value == 8
        assert manager.status(definition.simulation_id).targets[0].kind == "http"
        await manager.shutdown()

    asyncio.run(run())
