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

    async def update_values(self, values: Any, timestamp: str | None = None, current_values: Any = None, mqtt_metadata: Any = None) -> None:
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

    async def start(self) -> None:
        await self.start_channels(self.protocol)

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

    async def configure_channel_tags(self, protocol: str, config: Any) -> None:
        self.configured.append(config)
        if protocol == "opcua":
            await self.opcua.start()
            await self.opcua.configure_tags(config)
        elif protocol == "mqtt":
            await self.mqtt.start()
            await self.mqtt.configure_tags(config)
        self.protocol = self._running_protocol()

    async def start_channels(self, protocol: str) -> None:
        if protocol in ("opcua", "both"):
            await self.opcua.start()
        if protocol in ("mqtt", "both"):
            await self.mqtt.start()
        self.protocol = self._running_protocol()

    async def stop_channels(self, protocol: str) -> None:
        if protocol in ("mqtt", "both"):
            await self.mqtt.stop()
        if protocol in ("opcua", "both"):
            await self.opcua.stop()
        self.protocol = self._running_protocol()

    def _running_protocol(self) -> str:
        if self.opcua.running and self.mqtt.running:
            return "both"
        if self.mqtt.running:
            return "mqtt"
        return "opcua"

    async def update_values(self, values: Any, timestamp: str | None = None, current_values: Any = None, mqtt_metadata: Any = None) -> None:
        await self.update_channel_values(self.protocol, values, timestamp, current_values, mqtt_metadata)

    async def update_channel_values(self, protocol: str, values: Any, timestamp: str | None = None, current_values: Any = None, mqtt_metadata: Any = None) -> None:
        if protocol in ("opcua", "both"):
            await self.opcua.update_values(values, timestamp, current_values, mqtt_metadata)
        if protocol in ("mqtt", "both"):
            await self.mqtt.update_values(values, timestamp, current_values, mqtt_metadata)

    def get_endpoint(self) -> str:
        return "fake://both"


class SlowStartAdapter(FakeDualAdapter):
    async def start(self) -> None:
        await asyncio.sleep(1)


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


def test_each_selected_file_can_override_replay_settings() -> None:
    async def run() -> None:
        adapter = FakeDualAdapter()
        engine = MultiSimulatorEngine(adapter)  # type: ignore[arg-type]
        config = ReplayFilesConfig(
            protocol="opcua",
            frequency_hz=1,
            loop_mode="loop_forever",
            timestamp_mode="wall_clock",
            max_rows=2,
            opcua_files=[
                ReplayFileSelection(
                    filename="sample_pipeline_normal.csv",
                    source="sample",
                    frequency_hz=2.5,
                    loop_mode="once",
                    timestamp_mode="csv_timestamp_ignore_rate",
                    start_row=1,
                    max_rows=3,
                ),
                ReplayFileSelection(
                    filename="sample_pipeline_small_leak.csv",
                    source="sample",
                    frequency_hz=0.5,
                    loop_mode="ping_pong",
                    timestamp_mode="wall_clock",
                    start_row=0,
                    max_rows=4,
                ),
            ],
        )

        result = await engine.configure_files(config)

        assert result["file_count"] == 2
        first, second = engine.configs
        assert first.csv_file == "sample_pipeline_normal.csv"
        assert first.frequency_hz == 2.5
        assert first.loop_mode == "once"
        assert first.timestamp_mode == "csv_timestamp_ignore_rate"
        assert first.start_row == 1
        assert first.max_rows == 3
        assert second.csv_file == "sample_pipeline_small_leak.csv"
        assert second.frequency_hz == 0.5
        assert second.loop_mode == "ping_pong"
        assert second.timestamp_mode == "wall_clock"
        assert second.start_row == 0
        assert second.max_rows == 4

    asyncio.run(run())


def test_multiple_csv_files_stream_concurrently_with_separate_engines() -> None:
    async def run() -> None:
        adapter = FakeDualAdapter()
        engine = MultiSimulatorEngine(adapter)  # type: ignore[arg-type]
        config = ReplayFilesConfig(
            protocol="opcua",
            opcua_files=[
                ReplayFileSelection(filename="sample_pipeline_normal.csv", source="sample", frequency_hz=20, max_rows=2),
                ReplayFileSelection(filename="sample_pipeline_small_leak.csv", source="sample", frequency_hz=20, max_rows=2),
            ],
        )

        await engine.configure_files(config)
        await engine.start()
        await asyncio.sleep(0.1)

        status = engine.get_status()
        current = engine.get_current_values()
        names = {value.tag_name for value in current.values}
        assert status["file_count"] == 2
        assert len(engine.engines) == 2
        assert all(item["state"] == "running" for item in status["files"])
        assert any(name.startswith("sample_pipeline_normal_") for name in names)
        assert any(name.startswith("sample_pipeline_small_leak_") for name in names)

        await engine.stop()

    asyncio.run(run())


def test_start_restarts_protocol_service_after_stop() -> None:
    async def run() -> None:
        adapter = FakeDualAdapter()
        engine = MultiSimulatorEngine(adapter)  # type: ignore[arg-type]
        config = ReplayFilesConfig(protocol="opcua", opcua_files=[sample_file("sample_pipeline_normal.csv")], max_rows=2)

        await engine.configure_files(config)
        assert adapter.opcua.running
        await engine.stop()
        assert not adapter.opcua.running

        await engine.start()

        assert engine.state == "running"
        assert adapter.opcua.running
        await engine.stop()

    asyncio.run(run())


def test_start_times_out_when_protocol_service_does_not_respond() -> None:
    async def run() -> None:
        adapter = SlowStartAdapter()
        engine = MultiSimulatorEngine(adapter)  # type: ignore[arg-type]
        engine.PROTOCOL_START_TIMEOUT_SECONDS = 0.01
        config = ReplayFilesConfig(protocol="opcua", opcua_files=[sample_file("sample_pipeline_normal.csv")], max_rows=2)

        await engine.configure_files(config)
        await engine.stop()

        try:
            await engine.start()
            raise AssertionError("Expected protocol start timeout")
        except RuntimeError as exc:
            assert "timed out" in str(exc)
            assert engine.state == "error"
            assert engine.last_error is not None

    asyncio.run(run())
