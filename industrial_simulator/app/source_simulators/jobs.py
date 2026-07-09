from __future__ import annotations

import logging
import threading
import time
from typing import Any

from app import job_manager
from app.models import JobRecord
from app.source_simulators.registry import get_source_simulator

logger = logging.getLogger("industrial.source_simulation")
_controls_lock = threading.RLock()
_controls: dict[str, dict[str, threading.Event]] = {}
SOURCE_ROW_SAMPLE_LIMIT = 5


def _event(level: int, event: str, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"event": event, "fields": fields, "service": "Industrial", "source": "source_simulation"})


def _control(job_id: str) -> dict[str, threading.Event]:
    with _controls_lock:
        if job_id not in _controls:
            _controls[job_id] = {"stop": threading.Event(), "pause": threading.Event()}
        return _controls[job_id]


def _remove_control(job_id: str) -> None:
    with _controls_lock:
        _controls.pop(job_id, None)


def _active_control_job_ids() -> list[str]:
    with _controls_lock:
        return [job_id for job_id, control in _controls.items() if not control["stop"].is_set()]


def list_source_jobs() -> list[JobRecord]:
    return [job for job in job_manager.list_jobs() if job.type == "source_simulation"]


def source_jobs_snapshot(limit: int = 20, row_limit: int = SOURCE_ROW_SAMPLE_LIMIT) -> dict[str, Any]:
    jobs = list_source_jobs()
    active = [job for job in jobs if job.state in {"queued", "running", "paused"}]
    items: list[dict[str, Any]] = []
    for job in jobs[: max(0, limit)]:
        checkpoint = job.checkpoint or {}
        rows = list(checkpoint.get("last_rows_sample") or [])
        items.append(
            {
                "job_id": job.job_id,
                "name": job.name,
                "state": job.state,
                "connector_id": checkpoint.get("connector_id"),
                "entity": checkpoint.get("entity"),
                "mode": checkpoint.get("mode"),
                "cycles": checkpoint.get("cycles", 0),
                "rows_done": job.rows_done,
                "last_rows": checkpoint.get("last_rows", 0),
                "last_watermark": checkpoint.get("last_watermark"),
                "updated_at": job.updated_at,
                "sample": rows[: max(0, row_limit)],
            }
        )
    return {"total": len(jobs), "active": len(active), "items": items}


def _ensure_source_job(job_id: str) -> JobRecord:
    job = job_manager.get_job(job_id)
    if job.type != "source_simulation":
        raise ValueError(f"Job is not a source simulation job: {job_id}")
    return job


def start_source_job(
    connector_id: str,
    entity: str,
    interval_seconds: float = 15.0,
    max_cycles: int | None = None,
    mode: str = "query",
    filter_text: str = "",
    top: int | None = None,
    watermark: str | None = None,
    cycle_parameters: dict[str, Any] | None = None,
    run_id: str | None = None,
    run_name: str | None = None,
) -> JobRecord:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than 0.")
    if max_cycles is not None and max_cycles < 1:
        raise ValueError("max_cycles must be at least 1 when provided.")
    mode = mode.lower()
    if mode not in {"query", "cycle"}:
        raise ValueError("mode must be query or cycle.")
    source = get_source_simulator(connector_id)
    valid_entities = {str(item.get("entity")) for item in source.entities()}
    if entity not in valid_entities:
        raise KeyError(f"Unknown {source.display_name} entity: {entity}")
    job = job_manager.create_job(f"{source.display_name} - {entity}", "source_simulation")
    initial_checkpoint = {"connector_id": connector_id, "entity": entity, "mode": mode, "interval_seconds": interval_seconds}
    if run_id:
        initial_checkpoint["run_id"] = run_id
    if run_name:
        initial_checkpoint["run_name"] = run_name
    job_manager.update_job(job.job_id, checkpoint=initial_checkpoint, active_bottleneck=f"{connector_id}:{entity}")
    control = _control(job.job_id)
    control["stop"].clear()
    control["pause"].clear()

    def runner(job_id: str) -> None:
        cycles = 0
        rows_done = 0
        current_watermark = watermark
        job_started_at = time.perf_counter()
        _event(logging.INFO, "source_job.started", "Source simulation job started.", job_id=job_id, connector=connector_id, entity=entity, mode=mode)
        try:
            while not control["stop"].is_set():
                if control["pause"].is_set():
                    job_manager.update_job(job_id, state="paused", message="Source simulation paused.", current_step="paused")
                    while control["pause"].is_set() and not control["stop"].is_set():
                        time.sleep(0.2)
                    if control["stop"].is_set():
                        break
                    job_manager.update_job(job_id, state="running", message="Source simulation resumed.", current_step="running")

                cycle_result: dict[str, Any] | None = None
                if mode == "cycle":
                    cycle_result = source.run_cycle(**(cycle_parameters or {}))

                rows = source.query(entity, filter_text=filter_text, top=top, watermark=current_watermark)
                rows_done += len(rows)
                if rows:
                    current_watermark = max(str(row.get("ModifiedUTC", current_watermark or "")) for row in rows)
                row_sample = rows[:SOURCE_ROW_SAMPLE_LIMIT]
                cycles += 1
                elapsed = max(time.perf_counter() - job_started_at, 0.001)
                checkpoint = {
                    "connector_id": connector_id,
                    "entity": entity,
                    "mode": mode,
                    "cycles": cycles,
                    "last_rows": len(rows),
                    "last_rows_sample": row_sample,
                    "last_watermark": current_watermark,
                    "last_cycle_result": cycle_result,
                    "interval_seconds": interval_seconds,
                }
                if run_id:
                    checkpoint["run_id"] = run_id
                if run_name:
                    checkpoint["run_name"] = run_name
                job_manager.update_job(
                    job_id,
                    state="running",
                    progress_percent=100.0 if max_cycles and cycles >= max_cycles else 0.0,
                    current_step=f"cycle {cycles}",
                    message=f"{mode} cycle {cycles} completed.",
                    rows_done=rows_done,
                    rows_per_sec=rows_done / elapsed,
                    queue_depth=0,
                    active_bottleneck=f"{connector_id}:{entity}",
                    checkpoint=checkpoint,
                )
                _event(logging.INFO, "source_job.cycle_completed", "Source simulation cycle completed.", job_id=job_id, connector=connector_id, entity=entity, rows=len(rows), cycles=cycles)
                if max_cycles and cycles >= max_cycles:
                    job_manager.mark_completed(job_id, "Source simulation completed.", rows_done=rows_done, checkpoint=job_manager.get_job(job_id).checkpoint)
                    return
                control["stop"].wait(interval_seconds)
            job_manager.update_job(job_id, state="cancelled", completed_at=None, message="Source simulation stopped.", current_step="stopped", checkpoint={**job_manager.get_job(job_id).checkpoint, "stopped": True})
        except Exception as exc:
            _event(logging.ERROR, "source_job.failed", "Source simulation job failed.", job_id=job_id, connector=connector_id, entity=entity, error=str(exc))
            job_manager.mark_failed(job_id, str(exc))
        finally:
            _remove_control(job_id)

    job_manager.run_background(job.job_id, runner)
    return job_manager.get_job(job.job_id)


def stop_source_job(job_id: str) -> JobRecord:
    job = _ensure_source_job(job_id)
    if job.state in {"completed", "failed", "cancelled"}:
        return job
    if job_id not in _active_control_job_ids():
        return job_manager.update_job(
            job_id,
            state="cancelled",
            completed_at=None,
            message="Source simulation stopped. No active worker was attached to this persisted job.",
            current_step="stopped",
            checkpoint={**(job.checkpoint or {}), "stopped": True, "stale_worker": True},
        )
    _control(job_id)["stop"].set()
    return job_manager.update_job(job_id, message="Stop requested.", current_step="stopping")


def pause_source_job(job_id: str) -> JobRecord:
    _ensure_source_job(job_id)
    _control(job_id)["pause"].set()
    return job_manager.pause_job(job_id)


def resume_source_job(job_id: str) -> JobRecord:
    _ensure_source_job(job_id)
    _control(job_id)["pause"].clear()
    return job_manager.update_job(job_id, state="running", message="Resume requested.", current_step="resuming")
