import json
from pathlib import Path

import pytest

from app import csv_manager, dataset_manager, job_manager, video_engine
from app.models import DatasetManifest, DatasetSchemaField, RegisterDatasetRequest, VideoJobRequest


def _patch_roots(monkeypatch, tmp_path: Path) -> dict[str, Path]:
    roots = {
        "uploads": tmp_path / "uploads",
        "generated": tmp_path / "generated",
        "sample": tmp_path / "sample",
        "lakehouse": tmp_path / "lakehouse",
        "datasets": tmp_path / "generated" / "datasets",
        "runtime": tmp_path / "runtime_state",
        "video": tmp_path / "generated" / "video",
    }
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(csv_manager, "UPLOAD_DIR", roots["uploads"])
    monkeypatch.setattr(csv_manager, "GENERATED_DIR", roots["generated"])
    monkeypatch.setattr(csv_manager, "SAMPLE_DIR", roots["sample"])
    monkeypatch.setitem(csv_manager.SOURCE_DIRS, "uploaded", roots["uploads"])
    monkeypatch.setitem(csv_manager.SOURCE_DIRS, "generated", roots["generated"])
    monkeypatch.setitem(csv_manager.SOURCE_DIRS, "sample", roots["sample"])
    monkeypatch.setattr(dataset_manager, "DATASET_DIR", roots["datasets"])
    monkeypatch.setattr(dataset_manager, "LAKEHOUSE_DIR", roots["lakehouse"])
    monkeypatch.setattr(job_manager, "STATE_DIR", roots["runtime"])
    monkeypatch.setattr(job_manager, "JOBS_PATH", roots["runtime"] / "jobs.json")
    monkeypatch.setattr(job_manager, "_jobs", {})
    monkeypatch.setattr(video_engine, "VIDEO_ROOT", roots["video"])
    return roots


def test_register_scan_and_preview_local_csv_dataset(tmp_path, monkeypatch):
    roots = _patch_roots(monkeypatch, tmp_path)
    csv_path = roots["generated"] / "events.csv"
    csv_path.write_text("timestamp,value,status\n2026-01-01T00:00:00Z,1.5,ok\n2026-01-01T00:00:01Z,2.0,warn\n", encoding="utf-8")

    manifest = dataset_manager.register_local(RegisterDatasetRequest(path=str(csv_path), name="events"))
    assert manifest.state == "registered"
    assert manifest.ready_for_replay is True
    assert manifest.storage_format == "csv"

    scanned = dataset_manager.scan_dataset(manifest.dataset_id, job_id="job_scan")
    assert scanned.state == "ready"
    assert scanned.row_count == 2
    assert [field.name for field in scanned.schema] == ["timestamp", "value", "status"]
    assert scanned.scan_job_id == "job_scan"

    preview = dataset_manager.preview(manifest.dataset_id, limit=1)
    assert preview["columns"] == ["timestamp", "value", "status"]
    assert preview["rows"][0]["value"] == "1.5"


def test_generated_csv_manifest_is_preferred_over_auto_discovered_file(tmp_path, monkeypatch):
    roots = _patch_roots(monkeypatch, tmp_path)
    csv_path = roots["generated"] / "run_collision.csv"
    csv_path.write_text("timestamp,value\n2026-01-01T00:00:00Z,42\n", encoding="utf-8")
    dataset_id = "csv_generated_run_collision_csv"
    dataset_manager.write_manifest(
        DatasetManifest(
            dataset_id=dataset_id,
            name="Generated friendly name",
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

    datasets = dataset_manager.list_datasets()
    matches = [item for item in datasets if item.dataset_id == dataset_id]

    assert len(matches) == 1
    assert matches[0].name == "Generated friendly name"
    assert dataset_manager.get_dataset(dataset_id).name == "Generated friendly name"
    preview = dataset_manager.preview(dataset_id, limit=1)
    assert preview["filename"] == "run_collision.csv"
    assert preview["rows"][0]["value"] == "42"


def test_register_local_rejects_paths_outside_allowed_roots(tmp_path, monkeypatch):
    _patch_roots(monkeypatch, tmp_path)
    outside = tmp_path / "outside.csv"
    outside.write_text("x\n1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Registered paths must be under"):
        dataset_manager.register_local(RegisterDatasetRequest(path=str(outside)))


def test_job_manager_persists_lifecycle_state(tmp_path, monkeypatch):
    _patch_roots(monkeypatch, tmp_path)

    job = job_manager.create_job("Generate dataset", "generate_dataset", dataset_id="ds_1")
    job_manager.update_job(job.job_id, progress_percent=50.0, rows_done=10)
    completed = job_manager.mark_completed(job.job_id, "done", output_paths=["x"])

    assert completed.state == "completed"
    assert completed.progress_percent == 100.0
    assert completed.dataset_id == "ds_1"
    saved = json.loads(job_manager.JOBS_PATH.read_text(encoding="utf-8"))
    assert saved[0]["job_id"] == job.job_id
    assert saved[0]["output_paths"] == ["x"]


def test_video_job_writes_segment_manifest(tmp_path, monkeypatch):
    _patch_roots(monkeypatch, tmp_path)
    job = job_manager.create_job("video", "video_generation")
    request = VideoJobRequest(
        name="video",
        run_id="run_video_test",
        camera_count=1,
        fps=1,
        width=64,
        height=64,
        duration_seconds=2,
        segment_seconds=1,
    )

    video_engine.run_video_job(job.job_id, request)

    manifest_path = video_engine.VIDEO_ROOT / "run_video_test" / "video_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["segments"]) == 2
    assert job_manager.get_job(job.job_id).state == "completed"
