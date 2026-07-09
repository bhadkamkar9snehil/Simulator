from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app import csv_manager
from app.models import JobRecord, JobType, utc_now_iso

STATE_DIR = csv_manager.ROOT / "runtime_state"
JOBS_PATH = STATE_DIR / "jobs.json"

_lock = threading.RLock()
_jobs: dict[str, JobRecord] = {}


def _load() -> None:
    if _jobs or not JOBS_PATH.exists():
        return
    try:
        data = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
        for item in data:
            record = JobRecord(**item)
            _jobs[record.job_id] = record
    except Exception:
        _jobs.clear()


def _save() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_PATH.write_text(json.dumps([j.model_dump() for j in _jobs.values()], indent=2), encoding="utf-8")


def create_job(name: str, job_type: JobType, dataset_id: str | None = None) -> JobRecord:
    with _lock:
        _load()
        job = JobRecord(
            job_id=f"job_{uuid.uuid4().hex[:12]}",
            name=name,
            type=job_type,
            state="queued",
            dataset_id=dataset_id,
            updated_at=utc_now_iso(),
        )
        _jobs[job.job_id] = job
        _save()
        return job


def get_job(job_id: str) -> JobRecord:
    with _lock:
        _load()
        if job_id not in _jobs:
            raise KeyError(f"Job not found: {job_id}")
        return _jobs[job_id]


def list_jobs() -> list[JobRecord]:
    with _lock:
        _load()
        return sorted(_jobs.values(), key=lambda j: j.updated_at or "", reverse=True)


def update_job(job_id: str, **fields: Any) -> JobRecord:
    with _lock:
        job = get_job(job_id)
        data = job.model_dump()
        data.update(fields)
        data["updated_at"] = utc_now_iso()
        updated = JobRecord(**data)
        _jobs[job_id] = updated
        _save()
        return updated


def mark_running(job_id: str) -> JobRecord:
    return update_job(job_id, state="running", started_at=utc_now_iso(), message="Job started.")


def mark_completed(job_id: str, message: str = "Job completed.", **fields: Any) -> JobRecord:
    payload = {"state": "completed", "completed_at": utc_now_iso(), "progress_percent": 100.0, "message": message}
    payload.update(fields)
    return update_job(job_id, **payload)


def mark_failed(job_id: str, error: str, **fields: Any) -> JobRecord:
    payload = {"state": "failed", "completed_at": utc_now_iso(), "message": error, "error": error}
    payload.update(fields)
    return update_job(job_id, **payload)


def cancel_job(job_id: str) -> JobRecord:
    return update_job(job_id, state="cancelled", completed_at=utc_now_iso(), message="Cancellation requested.")


def pause_job(job_id: str) -> JobRecord:
    return update_job(job_id, state="paused", message="Pause requested.")


def resume_job(job_id: str) -> JobRecord:
    return update_job(job_id, state="queued", message="Resume requested.")


def cleanup_job(job_id: str) -> JobRecord:
    return update_job(job_id, state="cleanup_required", message="Cleanup requested.")


def run_background(job_id: str, target: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    def runner() -> None:
        try:
            mark_running(job_id)
            target(job_id, *args, **kwargs)
        except Exception as exc:
            mark_failed(job_id, str(exc))

    thread = threading.Thread(target=runner, name=f"sim-job-{job_id}", daemon=True)
    thread.start()


class Throughput:
    def __init__(self) -> None:
        self.started = time.perf_counter()

    def rates(self, rows: int, bytes_done: int) -> tuple[float, float]:
        elapsed = max(time.perf_counter() - self.started, 0.001)
        return rows / elapsed, (bytes_done / 1024 / 1024) / elapsed
