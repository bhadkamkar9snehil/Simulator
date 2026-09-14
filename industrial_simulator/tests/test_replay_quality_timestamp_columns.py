from __future__ import annotations

import asyncio
from typing import Any

from app.models import ReplayConfig, TagMapping
from app.simulator import SimulatorEngine


class CapturePublisher:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.metadata: dict[str, dict[str, Any]] = {}

    async def configure_tags(self, config: ReplayConfig) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def update_values(self, values, timestamp=None, current_values=None, mqtt_metadata=None) -> None:
        self.values = values
        self.metadata = mqtt_metadata or {}

    def get_endpoint(self) -> str:
        return "capture://test"


def test_replay_emits_configured_quality_and_source_timestamp_columns() -> None:
    async def scenario() -> None:
        publisher = CapturePublisher()
        engine = SimulatorEngine(publisher)
        engine.config = ReplayConfig(
            protocol="opcua",
            csv_file="fixture.csv",
            tags=[
                TagMapping(
                    csv_column="value",
                    tag_name="Value",
                    node_id="sim.value",
                    data_type="UInt16",
                    quality="Good",
                    quality_column="value_quality",
                    source_timestamp_column="value_source_time",
                )
            ],
        )
        engine.rows = [{
            "value": "42",
            "value_quality": "BadNoData",
            "value_source_time": "2026-09-14T12:00:00Z",
        }]
        engine.row_count = 1
        engine.cursor = 0

        await engine.emit_once()

        assert publisher.values["sim.value"] == (
            42,
            "UInt16",
            "BadNoData",
            "2026-09-14T12:00:00Z",
        )
        assert publisher.metadata["sim.value"]["quality"] == "BadNoData"
        assert publisher.metadata["sim.value"]["source_timestamp"] == "2026-09-14T12:00:00Z"

    asyncio.run(scenario())
