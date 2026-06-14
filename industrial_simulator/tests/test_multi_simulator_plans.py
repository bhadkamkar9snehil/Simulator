from __future__ import annotations

import asyncio
from typing import Any

from app.models import ReplayFileSelection, ReplayFilesConfig
from app.multi_simulator import MultiSimulatorEngine


class FakeProtocolService:
    def __init__(self, name: str) -> None:
        self.name = name
        self.running = False
        self.configured: list[Any] = []
        self.updates: list[Any] = []

    async def start(self) -> None:
        self.running = True

    async def stop(self) -> None:
        self.running = False

    async def configure_tags(self, config: Any) -> None:
        self.configured.append(config)

    async def update_values(self, values: Any, timestamp: str | None = None, current_values: Any = None) -> None:
        self.updates.append((values, timestamp, current_values))

    def get_endpoint(self) -> str:
        return f"fake://{self.name}"

    def get_status(self) -> dict[str, Any]:
        return {"running": self.running, "endpoint": self.get_endpoint(), "mock_mode": True}


class FakeDualAdapter:
    def __init__(self) -> None:
        self.opcua = FakeProtocolService("opcua")
        self.mqtt = FakeProtocolService("mqtt")
        self.protocol = "opcua"
        self.configured: list[Any] = []

    async def stop(self) -> None:
        await self.mqtt.stop()
        await self.opcua.stop()

    async def configure_tags(self, config: Any) -> None:
        self.protocol = config.protocol
        self.configured.append(config)
        if config.protocol == "opcua":
            await self.opcua.start()
            await self.opcua.configure_tags(config)
        elif config.protocol == "mqtt":
            await self.mqtt.start()
            await self.mqtt.configure_tags(config)
        else:
            await self.opcua.start()
            await self.mqtt.start()
            await self.opcua.configure_tags(config)
            await self.mqtt.configure_tags(config)

    async def update_values(self, values: Any, timestamp: str | None = None, current_values: Any = None) -> None:
        if self.protocol in ("opcua", "both"):
            await self.opcua.update_values(values, timestamp, current_values)
        if self.protocol in ("mqtt", "both"):
            await self.mqtt.update_values(values, timestamp, current_values)

    def get_endpoint(self) -> str:
        return "fake://both"


def sample_file(filename: str) -> ReplayFileSelection:
    return ReplayFileSelection(filename=filename, source="sample")


def test_both_mode_uses_two_protocol_plans_and_keeps_shared_files() -> None:
    async def run() -> None:
        adapter = FakeDualAdapter()
        engine = MultiSimulatorEngine(adapter)  # type: ignore[arg-type]
        config = ReplayFilesConfig(
            protocol="both",
            files=[sample_file("sample_pipeline_normal.csv")],
            opcua_files=[sample_file("sample_pipeline_small_leak.csv")],
            mqtt_files=[sample_file("sample_pipeline_normal.csv")],
            max_rows=2,
        )

        result = await engine.configure_files(config)

        assert result["assignment_mode"] == "separate"
        assert result["opcua_file_count"] == 2
        assert result["mqtt_file_count"] == 1
        assert result["opcua_files"] == ["sample_pipeline_normal.csv", "sample_pipeline_small_leak.csv"]
        assert result["mqtt_files"] == ["sample_pipeline_normal.csv"]
        assert [c.protocol for c in engine.configs] == ["opcua", "opcua", "mqtt"]
        assert adapter.opcua.configured[-1].protocol == "opcua"
        assert adapter.mqtt.configured[-1].protocol == "mqtt"

    asyncio.run(run())


def test_both_mode_shared_file_feeds_opcua_and_mqtt() -> None:
    async def run() -> None:
        adapter = FakeDualAdapter()
        engine = MultiSimulatorEngine(adapter)  # type: ignore[arg-type]
        config = ReplayFilesConfig(protocol="both", files=[sample_file("sample_pipeline_normal.csv")], max_rows=2)

        result = await engine.configure_files(config)

        assert result["assignment_mode"] == "separate"
        assert result["opcua_file_count"] == 1
        assert result["mqtt_file_count"] == 1
        assert [c.protocol for c in engine.configs] == ["opcua", "mqtt"]

    asyncio.run(run())


def test_protocol_tag_selection_disables_unselected_tags_per_protocol() -> None:
    async def run() -> None:
        adapter = FakeDualAdapter()
        engine = MultiSimulatorEngine(adapter)  # type: ignore[arg-type]
        config = ReplayFilesConfig(
            protocol="both",
            opcua_files=[sample_file("sample_pipeline_normal.csv")],
            mqtt_files=[sample_file("sample_pipeline_small_leak.csv")],
            max_rows=2,
            tag_selections=[
                {"protocol": "opcua", "filename": "sample_pipeline_normal.csv", "source": "sample", "csv_column": "station_a_suction_pressure_bar", "enabled": False},
                {"protocol": "mqtt", "filename": "sample_pipeline_small_leak.csv", "source": "sample", "csv_column": "flow_in_m3h", "enabled": False},
            ],
        )

        result = await engine.configure_files(config)

        assert result["opcua_tag_count"] > 0
        assert result["mqtt_tag_count"] > 0
        opcua_config = [c for c in engine.configs if c.protocol == "opcua"][0]
        mqtt_config = [c for c in engine.configs if c.protocol == "mqtt"][0]
        assert not [t for t in opcua_config.tags if t.csv_column == "station_a_suction_pressure_bar" and t.enabled]
        assert not [t for t in mqtt_config.tags if t.csv_column == "flow_in_m3h" and t.enabled]

    asyncio.run(run())
