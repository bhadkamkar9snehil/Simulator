from __future__ import annotations

import time
from typing import Any

from app import csv_manager, job_manager
from app.models import ReplayConfig
from app.multi_simulator import MultiSimulatorEngine
from app.http_streams import stream_snapshot
from app.replay_jobs import start_replay_job, stop_replay_job


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

    async def update_values(
        self,
        values: Any,
        timestamp: str | None = None,
        current_values: Any = None,
        mqtt_metadata: Any = None,
    ) -> None:
        self.updates.append((values, timestamp, current_values, mqtt_metadata))

    def get_endpoint(self) -> str:
        return f"fake://{self.name}"

    def get_status(self) -> dict[str, Any]:
        return {"running": self.running, "endpoint": self.get_endpoint(), "mock_mode": True}


class FakeDualAdapter:
    def __init__(self) -> None:
        self.opcua = FakeProtocolService("opcua")
        self.mqtt = FakeProtocolService("mqtt")
        self.protocol = "opcua"

    async def stop(self) -> None:
        await self.mqtt.stop()
        await self.opcua.stop()

    async def start(self) -> None:
        await self.start_channels(self.protocol)

    async def configure_tags(self, config: Any) -> None:
        self.protocol = config.protocol
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

    async def update_values(
        self,
        values: Any,
        timestamp: str | None = None,
        current_values: Any = None,
        mqtt_metadata: Any = None,
    ) -> None:
        await self.update_channel_values(self.protocol, values, timestamp, current_values, mqtt_metadata)

    async def update_channel_values(
        self,
        protocol: str,
        values: Any,
        timestamp: str | None = None,
        current_values: Any = None,
        mqtt_metadata: Any = None,
    ) -> None:
        if protocol in ("opcua", "both"):
            await self.opcua.update_values(values, timestamp, current_values, mqtt_metadata)
        if protocol in ("mqtt", "both"):
            await self.mqtt.update_values(values, timestamp, current_values, mqtt_metadata)

    def get_endpoint(self) -> str:
        return "fake://both"

    def get_status(self) -> dict[str, Any]:
        return {"active_protocol": self.protocol, "opcua": self.opcua.get_status(), "mqtt": self.mqtt.get_status()}


def _config(loop_mode: str = "once") -> ReplayConfig:
    meta = csv_manager.metadata("sample_pipeline_normal.csv", "sample")
    tags = [meta.default_tag_mappings[0]]
    return ReplayConfig(
        protocol="opcua",
        csv_file="sample_pipeline_normal.csv",
        csv_source="sample",
        frequency_hz=50,
        loop_mode=loop_mode,  # type: ignore[arg-type]
        max_rows=2,
        tags=tags,
    )


def _wait_for(job_id: str, states: set[str]) -> Any:
    deadline = time.time() + 5
    while time.time() < deadline:
        job = job_manager.get_job(job_id)
        if job.state in states:
            return job
        time.sleep(0.05)
    return job_manager.get_job(job_id)


def _wait_for_engine_jobs(engine: MultiSimulatorEngine, job_ids: set[str]) -> dict[str, Any]:
    deadline = time.time() + 5
    while time.time() < deadline:
        status = engine.get_status()
        active_ids = {item.get("job_id") for item in status["files"]}
        if job_ids.issubset(active_ids):
            return status
        time.sleep(0.05)
    return engine.get_status()


def _wait_for_current_values(engine: MultiSimulatorEngine) -> Any:
    deadline = time.time() + 5
    while time.time() < deadline:
        current = engine.get_current_values()
        if current.values:
            return current
        time.sleep(0.05)
    return engine.get_current_values()


def _wait_for_rows_done(job_id: str, minimum: int) -> Any:
    deadline = time.time() + 5
    while time.time() < deadline:
        job = job_manager.get_job(job_id)
        if job.rows_done >= minimum:
            return job
        time.sleep(0.05)
    return job_manager.get_job(job_id)


def _wait_for_no_engine_jobs(engine: MultiSimulatorEngine) -> dict[str, Any]:
    deadline = time.time() + 5
    while time.time() < deadline:
        status = engine.get_status()
        if not status["files"]:
            return status
        time.sleep(0.05)
    return engine.get_status()


def test_replay_job_runs_to_completion() -> None:
    engine = MultiSimulatorEngine(FakeDualAdapter())  # type: ignore[arg-type]

    job = start_replay_job(engine, _config())
    completed = _wait_for(job.job_id, {"completed", "failed"})

    assert completed.state == "completed"
    assert completed.type == "replay_dataset"
    assert completed.rows_done == 2
    assert completed.current_step == "completed"
    assert completed.checkpoint["protocol"] == "opcua"
    assert completed.checkpoint["state"] == "completed"
    assert completed.checkpoint["csv_file"] == "sample_pipeline_normal.csv"
    assert _wait_for_no_engine_jobs(engine)["state"] == "stopped"

    stopped_after_complete = stop_replay_job(job.job_id)
    assert stopped_after_complete.state == "completed"
    assert stopped_after_complete.current_step == "completed"


def test_replay_job_stop_uses_runner_control() -> None:
    engine = MultiSimulatorEngine(FakeDualAdapter())  # type: ignore[arg-type]

    job = start_replay_job(engine, _config(loop_mode="loop_forever"))
    running = _wait_for(job.job_id, {"running", "failed"})
    assert running.state == "running"

    stop_replay_job(job.job_id)
    stopped = _wait_for(job.job_id, {"cancelled", "failed"})

    assert stopped.state == "cancelled"
    assert stopped.current_step == "stopped"
    assert engine.get_status()["state"] == "stopped"


def test_replay_jobs_run_concurrently_with_job_scoped_tags() -> None:
    engine = MultiSimulatorEngine(FakeDualAdapter())  # type: ignore[arg-type]

    first = start_replay_job(engine, _config(loop_mode="loop_forever"))
    second = start_replay_job(engine, _config(loop_mode="loop_forever"))

    first_running = _wait_for(first.job_id, {"running", "failed"})
    second_running = _wait_for(second.job_id, {"running", "failed"})

    assert first_running.state == "running"
    assert second_running.state == "running"

    status = _wait_for_engine_jobs(engine, {first.job_id, second.job_id})
    running_job_ids = {item.get("job_id") for item in status["files"] if item.get("state") == "running"}
    assert {first.job_id, second.job_id}.issubset(running_job_ids)

    node_ids = [tag.node_id for config in engine.configs for tag in config.tags]
    assert len(node_ids) == len(set(node_ids))

    stop_replay_job(first.job_id)
    stop_replay_job(second.job_id)
    assert _wait_for(first.job_id, {"cancelled", "failed"}).state == "cancelled"
    assert _wait_for(second.job_id, {"cancelled", "failed"}).state == "cancelled"


def test_managed_replay_job_values_are_visible_in_stream_snapshot() -> None:
    adapter = FakeDualAdapter()
    engine = MultiSimulatorEngine(adapter)  # type: ignore[arg-type]

    job = start_replay_job(engine, _config(loop_mode="loop_forever"))
    running = _wait_for(job.job_id, {"running", "failed"})
    assert running.state == "running"
    current = _wait_for_current_values(engine)

    snapshot = stream_snapshot(engine, adapter, value_limit=5)

    assert current.values
    assert snapshot["simulator"]["assignment_mode"] == "managed_jobs"
    assert snapshot["current_values"]["count"] >= 1
    assert snapshot["current_values"]["items"][0]["node_id"].startswith("TagSimulator.job_")
    updated = _wait_for_rows_done(job.job_id, 1)
    assert updated.rows_done >= 1

    stop_replay_job(job.job_id)
    assert _wait_for(job.job_id, {"cancelled", "failed"}).state == "cancelled"
