from __future__ import annotations

import asyncio

from app.simulation import targets
from app.simulation.models import SignalDefinition, SignalValue, SimulationFrame, TargetBinding


def test_sql_server_target_batches_and_flushes(monkeypatch) -> None:
    calls: list[tuple[str, list[dict] | None]] = []

    def fake_sql(action: str, config: dict, rows: list[dict] | None = None, timeout: int = 60) -> dict:
        calls.append((action, rows))
        if action == "write":
            return {"ok": True, "rows_written": len(rows or [])}
        return {"ok": True}

    monkeypatch.setattr(targets, "run_sql_action", fake_sql)

    binding = TargetBinding(
        target_id="historian",
        kind="sql_server",
        config={
            "server": "sql01",
            "port": 1433,
            "database": "Simulator",
            "table": "dbo.tag_snapshots",
            "batch_size": 2,
        },
    )
    target = targets.SqlServerTarget(binding)
    schema = [
        SignalDefinition(name="pressure", node_id="pressure", data_type="Double", unit="bar"),
        SignalDefinition(name="running", node_id="running", data_type="Boolean"),
    ]

    async def exercise() -> None:
        await target.start("sim_a", "Plant A", schema)
        await target.publish(
            SimulationFrame(
                simulation_id="sim_a",
                sequence=1,
                timestamp="2026-09-13T05:00:00Z",
                values={
                    "pressure": SignalValue(value=12.5, data_type="Double", unit="bar"),
                    "running": SignalValue(value=True, data_type="Boolean"),
                },
            )
        )
        assert target.status().details["rows_written"] == 2

        await target.publish(
            SimulationFrame(
                simulation_id="sim_a",
                sequence=2,
                timestamp="2026-09-13T05:00:01Z",
                values={"pressure": SignalValue(value=12.7, data_type="Double", unit="bar")},
            )
        )
        assert target.status().details["buffered_rows"] == 1
        await target.stop()

    asyncio.run(exercise())

    assert calls[0][0] == "test"
    write_calls = [rows for action, rows in calls if action == "write"]
    assert [len(rows or []) for rows in write_calls] == [2, 1]
    assert write_calls[0][0]["tag_name"] == "pressure"
    assert write_calls[0][0]["unit"] == "bar"


def test_sql_server_target_surfaces_connection_failure(monkeypatch) -> None:
    def fake_sql(action: str, config: dict, rows: list[dict] | None = None, timeout: int = 60) -> dict:
        return {"ok": False, "error": "login failed"}

    monkeypatch.setattr(targets, "run_sql_action", fake_sql)
    target = targets.SqlServerTarget(TargetBinding(target_id="sql", kind="sql", config={}))

    async def exercise() -> None:
        try:
            await target.start("sim_a", "Plant A", [])
        except ValueError as exc:
            assert "login failed" in str(exc)
        else:
            raise AssertionError("Expected SQL target startup to fail")

    asyncio.run(exercise())
    status = target.status()
    assert status.state == "error"
    assert status.last_error == "login failed"
