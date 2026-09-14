from __future__ import annotations

import asyncio
from typing import Any

from app.sql_server import run_sql_action

from ..models import SignalDefinition, SimulationFrame, TargetBinding, TargetRuntimeStatus


class SqlServerTarget:
    """Batched SQL Server projection using the existing System.Data helper."""

    def __init__(self, binding: TargetBinding):
        self.target_id = binding.target_id
        self.binding = binding
        self._state = "created"
        self._last_error: str | None = None
        self._buffer: list[dict[str, Any]] = []
        self._rows_written = 0
        self._endpoint: str | None = None

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None:
        config = self.binding.config
        server = str(config.get("server", "localhost"))
        port = int(config.get("port", 1433))
        database = str(config.get("database", "master"))
        table = str(config.get("table", "dbo.tag_snapshots"))
        self._endpoint = f"sqlserver://{server}:{port}/{database}/{table}"
        self._state = "starting"
        result = await asyncio.to_thread(run_sql_action, "test", config)
        if not result.get("ok"):
            self._state = "error"
            self._last_error = str(result.get("error") or result.get("stderr") or "SQL Server connection failed.")
            raise ValueError(self._last_error)
        self._state = "running"
        self._last_error = None

    async def publish(self, frame: SimulationFrame) -> None:
        description = str(self.binding.config.get("description", frame.simulation_id))
        for name, signal in frame.values.items():
            self._buffer.append({
                "ts": frame.timestamp,
                "tag_name": name,
                "value": "" if signal.value is None else str(signal.value),
                "unit": signal.unit or "",
                "quality": signal.quality,
                "description": str(signal.metadata.get("description") or description),
            })
        if len(self._buffer) >= int(self.binding.config.get("batch_size", 50)):
            await self._flush()

    async def stop(self) -> None:
        if self._buffer:
            await self._flush()
        self._state = "stopped"

    def status(self) -> TargetRuntimeStatus:
        return TargetRuntimeStatus(
            target_id=self.target_id,
            kind="sql_server",
            state=self._state,  # type: ignore[arg-type]
            endpoint=self._endpoint,
            last_error=self._last_error,
            details={"buffered_rows": len(self._buffer), "rows_written": self._rows_written},
        )

    async def _flush(self) -> None:
        rows, self._buffer = self._buffer, []
        if not rows:
            return
        result = await asyncio.to_thread(run_sql_action, "write", self.binding.config, rows)
        if not result.get("ok"):
            self._buffer = rows + self._buffer
            self._last_error = str(result.get("error") or result.get("stderr") or "SQL Server write failed.")
            raise ValueError(self._last_error)
        self._rows_written += int(result.get("rows_written", len(rows)) or 0)
        self._last_error = None
