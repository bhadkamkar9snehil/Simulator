from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app import csv_manager, dataset_manager, job_manager
import app.api as api_module
from app.models import DatasetManifest, DatasetSchemaField, WorkloadReplayOptions
from app.multi_simulator import MultiSimulatorEngine
from app.workloads import _replay_config
from main import app


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
        await self.stop_channels("both")

    async def start(self) -> None:
        await self.start_channels(self.protocol)

    async def configure_tags(self, config: Any) -> None:
        self.protocol = config.protocol
        await self.configure_channel_tags(config.protocol, config)

    async def configure_channel_tags(self, protocol: str, config: Any) -> None:
        if protocol in ("opcua", "both"):
            await self.opcua.start()
            await self.opcua.configure_tags(config)
        if protocol in ("mqtt", "both"):
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

    async def update_values(self, values: Any, timestamp: str | None = None, current_values: Any = None, mqtt_metadata: Any = None) -> None:
        await self.update_channel_values(self.protocol, values, timestamp, current_values, mqtt_metadata)

    async def update_channel_values(self, protocol: str, values: Any, timestamp: str | None = None, current_values: Any = None, mqtt_metadata: Any = None) -> None:
        if protocol in ("opcua", "both"):
            await self.opcua.update_values(values, timestamp, current_values, mqtt_metadata)
        if protocol in ("mqtt", "both"):
            await self.mqtt.update_values(values, timestamp, current_values, mqtt_metadata)

    def get_endpoint(self) -> str:
        return "fake://both"

    def get_status(self) -> dict[str, Any]:
        return {"active_protocol": self.protocol, "opcua": self.opcua.get_status(), "mqtt": self.mqtt.get_status()}

    def _running_protocol(self) -> str:
        if self.opcua.running and self.mqtt.running:
            return "both"
        if self.mqtt.running:
            return "mqtt"
        return "opcua"


def _wait_for_jobs(job_ids: list[str], states: set[str]) -> dict[str, str]:
    deadline = time.time() + 8
    latest: dict[str, str] = {}
    while time.time() < deadline:
        latest = {job_id: job_manager.get_job(job_id).state for job_id in job_ids}
        if latest and all(state in states for state in latest.values()):
            return latest
        time.sleep(0.05)
    return latest


def test_concurrent_workload_api_starts_replay_sap_and_lims_jobs(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "simulator", MultiSimulatorEngine(FakeDualAdapter()))  # type: ignore[arg-type]
    client = TestClient(app)

    response = client.post(
        "/api/workloads/concurrent-run",
        json={
            "name": "Test concurrent run",
            "replay": {
                "enabled": True,
                "csv_file": "sample_pipeline_normal.csv",
                "csv_source": "sample",
                "protocol": "opcua",
                "frequency_hz": 50,
                "loop_mode": "once",
                "max_rows": 2,
            },
            "sap_pp": {
                "enabled": True,
                "entity": "A_ProductionOrder",
                "interval_seconds": 0.01,
                "max_cycles": 1,
                "top": 1,
            },
            "lims_odbc": {
                "enabled": True,
                "entity": "dbo.vw_LatestQualityResults",
                "mode": "cycle",
                "interval_seconds": 0.01,
                "max_cycles": 1,
                "top": 2,
                "cycle_parameters": {"excursion_probability": 0.1},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_count"] == 3
    assert payload["run_id"].startswith("run_")
    assert payload["streams"]["snapshot"] == "/api/streams/snapshot"

    job_ids = [job["job_id"] for job in payload["jobs"]]
    assert len(set(job_ids)) == 3
    assert {job["type"] for job in payload["jobs"]} == {"replay_dataset", "source_simulation"}
    assert all(job["checkpoint"]["run_id"] == payload["run_id"] for job in payload["jobs"])

    states = _wait_for_jobs(job_ids, {"completed", "failed"})
    assert states
    assert all(state == "completed" for state in states.values())

    completed = [job_manager.get_job(job_id) for job_id in job_ids]
    assert all(job.checkpoint["run_id"] == payload["run_id"] for job in completed)
    assert any(job.type == "replay_dataset" and job.rows_done == 2 for job in completed)
    assert any(job.checkpoint.get("connector_id") == "sap_pp" and job.rows_done == 1 for job in completed)
    assert any(job.checkpoint.get("connector_id") == "lims_odbc" and job.rows_done >= 2 for job in completed)

    run_detail = client.get(f"/api/workloads/runs/{payload['run_id']}")
    assert run_detail.status_code == 200
    run = run_detail.json()
    assert run["run_id"] == payload["run_id"]
    assert run["name"] == "Test concurrent run"
    assert run["job_count"] == 3
    assert run["state"] == "completed"
    assert run["protocols"] == ["opcua"]
    assert set(run["connectors"]) == {"sap_pp", "lims_odbc"}
    assert {child["job_id"] for child in run["children"]} == set(job_ids)

    runs = client.get("/api/workloads/runs")
    assert runs.status_code == 200
    assert any(item["run_id"] == payload["run_id"] for item in runs.json()["runs"])


def test_concurrent_workload_api_starts_heterogeneous_exports(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "simulator", MultiSimulatorEngine(FakeDualAdapter()))  # type: ignore[arg-type]
    client = TestClient(app)

    response = client.post(
        "/api/workloads/concurrent-run",
        json={
            "name": "Heterogeneous export run",
            "replays": [
                {
                    "enabled": True,
                    "csv_file": "sample_pipeline_normal.csv",
                    "csv_source": "sample",
                    "protocol": "opcua",
                    "frequency_hz": 50,
                    "loop_mode": "once",
                    "max_rows": 1,
                },
                {
                    "enabled": True,
                    "csv_file": "sample_pipeline_normal.csv",
                    "csv_source": "sample",
                    "protocol": "mqtt",
                    "frequency_hz": 50,
                    "loop_mode": "once",
                    "max_rows": 1,
                },
            ],
            "video_jobs": [
                {
                    "name": "Test video export",
                    "camera_count": 1,
                    "fps": 1,
                    "width": 64,
                    "height": 64,
                    "duration_seconds": 1,
                    "segment_seconds": 1,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_count"] == 3
    job_ids = [job["job_id"] for job in payload["jobs"]]
    assert len(set(job_ids)) == 3
    assert {job["type"] for job in payload["jobs"]} == {"replay_dataset", "video_generation"}
    assert all(job["checkpoint"]["run_id"] == payload["run_id"] for job in payload["jobs"])

    states = _wait_for_jobs(job_ids, {"completed", "failed"})
    assert states
    assert all(state == "completed" for state in states.values())

    run_detail = client.get(f"/api/workloads/runs/{payload['run_id']}")
    assert run_detail.status_code == 200
    run = run_detail.json()
    assert run["job_count"] == 3
    assert set(run["protocols"]) == {"opcua", "mqtt"}


def test_workload_run_api_controls_child_jobs() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/workloads/concurrent-run",
        json={
            "name": "Test controlled run",
            "replay": {"enabled": False},
            "sap_pp": {"enabled": False, "entity": "A_ProductionOrder"},
            "lims_odbc": {
                "enabled": True,
                "entity": "dbo.vw_LatestQualityResults",
                "mode": "cycle",
                "interval_seconds": 5.0,
                "top": 1,
                "cycle_parameters": {"excursion_probability": 0.0},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_count"] == 1
    run_id = payload["run_id"]
    job_id = payload["jobs"][0]["job_id"]
    assert _wait_for_jobs([job_id], {"running"})[job_id] == "running"

    paused = client.post(f"/api/workloads/runs/{run_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["state"] == "paused"
    assert job_manager.get_job(job_id).state == "paused"

    resumed = client.post(f"/api/workloads/runs/{run_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["state"] == "running"
    assert job_manager.get_job(job_id).state == "running"

    stopped = client.post(f"/api/workloads/runs/{run_id}/stop")
    assert stopped.status_code == 200
    states = _wait_for_jobs([job_id], {"cancelled"})
    assert states[job_id] == "cancelled"


def test_workload_run_api_starts_sap_only_job() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/workloads/concurrent-run",
        json={
            "name": "SAP only run",
            "replay": {"enabled": False},
            "sap_pp": {
                "enabled": True,
                "entity": "A_ProductionOrder",
                "mode": "query",
                "filter_text": "Product eq 'FG-UREA'",
                "interval_seconds": 0.01,
                "max_cycles": 1,
                "top": 1,
            },
            "lims_odbc": {"enabled": False, "entity": "dbo.vw_LatestQualityResults"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_count"] == 1
    assert payload["jobs"][0]["checkpoint"]["connector_id"] == "sap_pp"
    assert payload["jobs"][0]["checkpoint"]["entity"] == "A_ProductionOrder"
    assert _wait_for_jobs([payload["jobs"][0]["job_id"]], {"completed", "failed"})
    completed = job_manager.get_job(payload["jobs"][0]["job_id"])
    assert completed.state == "completed"
    assert completed.rows_done == 1


def test_workload_run_api_rejects_empty_child_selection() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/workloads/concurrent-run",
        json={
            "name": "Empty run",
            "replay": {"enabled": False},
            "sap_pp": {"enabled": False, "entity": "A_ProductionOrder"},
            "lims_odbc": {"enabled": False, "entity": "dbo.vw_LatestQualityResults"},
        },
    )

    assert response.status_code == 400
    assert "Enable at least one child simulation" in response.json()["detail"]["error"]


def test_workload_run_stop_closes_persisted_replay_without_worker() -> None:
    client = TestClient(app)
    run_id = "run_pytest_stale_worker"
    job = job_manager.create_job("Stale replay worker", "replay_dataset")
    job_manager.update_job(
        job.job_id,
        state="running",
        current_step="running",
        message="Persisted running job from an older process.",
        checkpoint={"run_id": run_id, "run_name": "Stale worker run", "protocol": "both"},
    )

    stopped = client.post(f"/api/workloads/runs/{run_id}/stop")
    assert stopped.status_code == 200
    payload = stopped.json()
    assert payload["state"] == "cancelled"
    assert payload["active_jobs"] == 0
    updated = job_manager.get_job(job.job_id)
    assert updated.state == "cancelled"
    assert updated.current_step == "stopped"
    assert updated.checkpoint["stale_worker"] is True


def test_workload_replay_config_uses_managed_manifest_for_colliding_generated_csv(tmp_path: Path, monkeypatch) -> None:
    generated = tmp_path / "generated"
    datasets = generated / "datasets"
    generated.mkdir()
    datasets.mkdir()
    monkeypatch.setitem(csv_manager.SOURCE_DIRS, "generated", generated)
    monkeypatch.setattr(dataset_manager, "DATASET_DIR", datasets)
    csv_path = generated / "run_collision.csv"
    csv_path.write_text("timestamp,value\n2026-01-01T00:00:00Z,13\n", encoding="utf-8")
    dataset_manager.write_manifest(
        DatasetManifest(
            dataset_id="csv_generated_run_collision_csv",
            name="Friendly generated CSV",
            source="generated",
            storage_format="csv",
            state="ready",
            schema=[
                DatasetSchemaField(name="timestamp", data_type="String"),
                DatasetSchemaField(name="value", data_type="Int64"),
            ],
            row_count=1,
            column_count=2,
            ready_for_replay=True,
            path=str(csv_path),
        )
    )

    config = _replay_config(
        WorkloadReplayOptions(
            enabled=True,
            dataset_id="csv_generated_run_collision_csv",
            protocol="both",
            max_rows=1,
        )
    )

    assert config.dataset_id == "csv_generated_run_collision_csv"
    assert config.csv_file == "run_collision.csv"
    assert any(tag.csv_column == "value" for tag in config.tags)
