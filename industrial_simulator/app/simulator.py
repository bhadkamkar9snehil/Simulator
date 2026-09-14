from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app import csv_manager, dataset_manager
from app.models import CurrentValue, CurrentValuesResponse, ReplayConfig, ReplayStatus, utc_now_iso
from app.simulation.sources import IndexedCsvRows
from app.type_inference import convert_value

logger = logging.getLogger("industrial.replay")


def _log_event(level: int, event: str, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"event": event, "fields": fields, "service": "Industrial", "source": "replay"})


class ProtocolPublisher(Protocol):
    async def configure_tags(self, config: ReplayConfig) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def update_values(self, values: dict[str, tuple[Any, str]], timestamp: str | None = None, current_values: dict[str, CurrentValue] | None = None, mqtt_metadata: dict[str, dict[str, Any]] | None = None) -> None: ...
    def get_endpoint(self) -> str: ...


class SimulatorEngine:
    def __init__(self, publisher: ProtocolPublisher):
        self.publisher = publisher
        self.config: ReplayConfig | None = None
        self.columns: list[str] = []
        self.rows: list[dict[str, str]] = []
        self.indexed_rows: IndexedCsvRows | None = None
        self.row_count = 0
        self.emitted_count = 0
        self.cursor = 0
        self.direction = 1
        self.state = "idle"
        self.last_error: str | None = None
        self.task: asyncio.Task | None = None
        self.current_values: dict[str, CurrentValue] = {}
        self.updated_at: str | None = None

    async def configure(self, config: ReplayConfig, configure_adapter: bool = True) -> dict[str, Any]:
        await self.stop()
        path: Path
        if config.dataset_id:
            manifest = dataset_manager.get_dataset(config.dataset_id)
            if manifest.storage_format in ("parquet", "parquet_folder"):
                raise ValueError("Parquet dataset replay is planned but requires the pyarrow-backed columnar reader. Use CSV replay or generate a CSV dataset for this run.")
            if manifest.storage_format != "csv":
                raise ValueError("Replay currently supports CSV datasets.")
            path = dataset_manager.dataset_path(manifest)
            config.csv_file = path.name
            if manifest.source in {"uploaded", "generated", "sample"}:
                config.csv_source = manifest.source  # type: ignore[assignment]
        else:
            if not config.csv_file:
                raise ValueError("Select a CSV file or dataset before configuring replay.")
            path = csv_manager.resolve_csv_path(config.csv_file, config.csv_source)
        _log_event(logging.INFO, "replay.engine.configure.requested", "Configuring replay engine.", file=config.csv_file, source=config.csv_source, protocol=config.protocol, timestamp_mode=config.timestamp_mode, loop_mode=config.loop_mode, frequency_hz=config.frequency_hz)
        rows: list[dict[str, str]] = []
        indexed_rows: IndexedCsvRows | None = None
        if path.suffix.lower() == ".csv":
            indexed_rows = IndexedCsvRows(path, config.max_rows)
            columns = indexed_rows.columns
            row_count = indexed_rows.row_count
        else:
            columns, rows = csv_manager.read_full_csv(config.csv_file, config.csv_source, config.max_rows)
            row_count = len(rows)
        if config.timestamp_mode in ("csv_timestamp_ignore_rate", "relative_from_csv"):
            if "timestamp" not in columns:
                raise ValueError("CSV must have a 'timestamp' column for the selected timestamp mode.")
        if row_count == 0:
            raise ValueError("CSV has no data rows.")
        if config.start_row >= row_count:
            raise ValueError("start_row must be less than row_count.")
        missing = [t.csv_column for t in config.tags if t.enabled and t.csv_column not in columns]
        if missing:
            raise ValueError(f"CSV columns not found: {', '.join(missing)}")
        self.config = config
        self.columns = columns
        self.rows = rows
        self.indexed_rows = indexed_rows
        self.row_count = row_count
        self.cursor = config.start_row
        self.direction = 1
        self.current_values.clear()
        self.emitted_count = 0
        if configure_adapter:
            await self.publisher.configure_tags(config)
        self.state = "configured"
        self.last_error = None
        _log_event(logging.INFO, "replay.engine.configure.completed", "Replay engine configured.", file=config.csv_file, source=config.csv_source, protocol=config.protocol, rows=row_count, columns=len(columns), tags=len([t for t in config.tags if t.enabled]), start_row=config.start_row)
        return {"status": "configured", "protocol": config.protocol, "tag_count": len([t for t in config.tags if t.enabled]), "endpoint": self.publisher.get_endpoint()}

    async def start(self) -> dict[str, str]:
        if self.config is None:
            raise ValueError("Cannot start before replay is configured.")
        if self.state == "running":
            _log_event(logging.INFO, "replay.engine.start.skipped", "Replay engine already running.", file=self.config.csv_file, source=self.config.csv_source)
            return {"status": "running"}
        self.state = "running"
        self.task = asyncio.create_task(self._loop())
        _log_event(logging.INFO, "replay.engine.start.completed", "Replay engine started.", file=self.config.csv_file, source=self.config.csv_source, cursor=self.cursor, rows=self.row_count)
        return {"status": "running"}

    async def stop(self) -> dict[str, str]:
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None
        if self.config is not None and self.state != "completed":
            self.state = "stopped"
            _log_event(logging.INFO, "replay.engine.stop.completed", "Replay engine stopped.", file=self.config.csv_file, source=self.config.csv_source, cursor=self.cursor, state=self.state)
        return {"status": self.state}

    async def restart(self) -> dict[str, Any]:
        if self.config is None:
            raise ValueError("Cannot restart before replay is configured.")
        await self.stop()
        self.cursor = self.config.start_row
        self.direction = 1
        await self.start()
        return {"status": "running", "cursor": self.cursor}

    async def reset_cursor(self) -> dict[str, Any]:
        if self.config is None:
            raise ValueError("Cannot reset before replay is configured.")
        self.cursor = self.config.start_row
        self.direction = 1
        return {"status": "ok", "cursor": self.cursor}

    def _get_row_datetime(self, row_idx: int) -> datetime:
        ts_str = self._row_at(row_idx).get("timestamp")
        if not ts_str:
            return datetime.now(timezone.utc)
        return datetime.fromisoformat(str(ts_str).strip().replace("Z", "+00:00"))

    def _row_at(self, row_idx: int) -> dict[str, str]:
        if self.indexed_rows is not None:
            return self.indexed_rows.row(row_idx)
        return self.rows[row_idx]

    async def _loop(self) -> None:
        assert self.config is not None
        while self.state == "running":
            try:
                await self.emit_once()

                current_cursor = self.cursor
                self._advance_cursor()
                next_cursor = self.cursor

                if self.state != "running":
                    break

                if self.config.timestamp_mode == "wall_clock":
                    delay = 1.0 / self.config.frequency_hz
                else:
                    if next_cursor == current_cursor:
                        delay = 1.0 / self.config.frequency_hz
                    else:
                        t1 = self._get_row_datetime(current_cursor)
                        t2 = self._get_row_datetime(next_cursor)
                        delay = (t2 - t1).total_seconds()

                        if self.config.loop_mode == "ping_pong":
                            delay = abs(delay)
                        elif delay < 0:
                            delay = 1.0 / self.config.frequency_hz

                        if delay <= 0:
                            delay = 0.01

                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                self.state = "error"
                logger.exception(
                    "Replay loop failed.",
                    extra={
                        "event": "replay.engine.loop.failed",
                        "fields": {"file": self.config.csv_file, "source": self.config.csv_source, "cursor": self.cursor},
                        "service": "Industrial",
                        "source": "replay",
                    },
                )
                break

    async def emit_once(self) -> None:
        assert self.config is not None
        row = self._row_at(self.cursor)
        values_for_mqtt: dict[str, tuple[Any, str]] = {}
        mqtt_metadata: dict[str, dict[str, Any]] = {}

        if self.config.timestamp_mode == "csv_timestamp_ignore_rate":
            ts_str = row.get("timestamp")
            if ts_str:
                timestamp = str(ts_str).strip().replace(" ", "T")
            else:
                timestamp = utc_now_iso()
        else:
            timestamp = utc_now_iso()

        for tag in self.config.tags:
            if not tag.enabled:
                continue
            raw = row.get(tag.csv_column)
            try:
                value = convert_value(raw, tag.data_type)
            except Exception:
                value = None
            cv = CurrentValue(tag_name=tag.tag_name, node_id=tag.node_id, value=value, data_type=tag.data_type, last_updated=timestamp)
            self.current_values[tag.node_id] = cv
            values_for_mqtt[tag.node_id] = (value, tag.data_type)
            mqtt_metadata[tag.node_id] = self._mqtt_metadata_for_row(row, tag.csv_column)
        self.updated_at = timestamp
        await self.publisher.update_values(values_for_mqtt, timestamp=timestamp, current_values=self.current_values, mqtt_metadata=mqtt_metadata)
        self.emitted_count += 1

    def _mqtt_metadata_for_row(self, row: dict[str, Any], csv_column: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {"tag": csv_column, "quality": "GOOD"}
        unit = self._row_value_case_insensitive(
            row,
            [
                f"{csv_column}_unit",
                f"{csv_column} unit",
                f"{csv_column}.unit",
                f"{csv_column}/unit",
                f"unit_{csv_column}",
                f"Unit_{csv_column}",
            ],
        )
        quality = self._row_value_case_insensitive(
            row,
            [
                f"{csv_column}_quality",
                f"{csv_column} quality",
                f"{csv_column}.quality",
                f"{csv_column}/quality",
                f"quality_{csv_column}",
                f"Quality_{csv_column}",
            ],
        )

        if unit is None:
            unit = self._row_value_case_insensitive(row, ["unit", "Unit", "UNIT"])
        if quality is None:
            quality = self._row_value_case_insensitive(row, ["quality", "Quality", "QUALITY", "status", "Status"])

        if unit is not None:
            metadata["unit"] = unit
        if quality is not None:
            metadata["quality"] = quality
        return metadata

    def _row_value_case_insensitive(self, row: dict[str, Any], names: list[str]) -> Any:
        lower_map = {str(key).strip().lower(): value for key, value in row.items()}
        for name in names:
            value = lower_map.get(str(name).strip().lower())
            if value is not None and str(value).strip() != "":
                return value
        return None

    def _advance_cursor(self) -> None:
        assert self.config is not None
        last = self.row_count - 1
        start = self.config.start_row
        mode = self.config.loop_mode
        if mode == "loop_forever":
            self.cursor += 1
            if self.cursor > last:
                self.cursor = start
        elif mode == "once":
            if self.cursor >= last:
                self.state = "completed"
            else:
                self.cursor += 1
        elif mode == "hold_last":
            if self.cursor < last:
                self.cursor += 1
        elif mode == "ping_pong":
            if self.direction > 0 and self.cursor >= last:
                self.direction = -1
            elif self.direction < 0 and self.cursor <= start:
                self.direction = 1
            self.cursor += self.direction
            self.cursor = max(start, min(last, self.cursor))

    def get_status(self) -> ReplayStatus:
        return ReplayStatus(
            state=self.state,
            protocol=self.config.protocol if self.config else None,
            configured=self.config is not None,
            csv_file=self.config.csv_file if self.config else None,
            csv_source=self.config.csv_source if self.config else None,
            frequency_hz=self.config.frequency_hz if self.config else None,
            cursor=self.cursor,
            row_count=self.row_count,
            emitted_count=self.emitted_count,
            tag_count=len([t for t in self.config.tags if t.enabled]) if self.config else 0,
            loop_mode=self.config.loop_mode if self.config else None,
            timestamp_mode=self.config.timestamp_mode if self.config else None,
            last_error=self.last_error,
        )

    def get_current_values(self) -> CurrentValuesResponse:
        return CurrentValuesResponse(updated_at=self.updated_at, values=list(self.current_values.values()))
