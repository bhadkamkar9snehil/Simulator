from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from typing import Any

from app import job_manager
from app.models import JobRecord, ReplayConfig, TagMapping, utc_now_iso
from app.multi_simulator import MultiSimulatorEngine

logger = logging.getLogger("industrial.replay_jobs")

_controls_lock = threading.RLock()
_controls: dict[str, dict[str, threading.Event]] = {}


def _event(level: int, event: str, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"event": event, "fields": fields, "service": "Industrial", "source": "replay_jobs"})


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


def list_replay_jobs() -> list[JobRecord]:
    return [job for job in job_manager.list_jobs() if job.type == "replay_dataset"]


def _ensure_replay_job(job_id: str) -> JobRecord:
    job = job_manager.get_job(job_id)
    if job.type != "replay_dataset":
        raise ValueError(f"Job is not a replay job: {job_id}")
    return job


def _rows_done(status: dict[str, Any]) -> int:
    total = 0
    for item in status.get("files") or []:
        emitted_count = item.get("emitted_count")
        if emitted_count is not None:
            total += max(0, int(emitted_count or 0))
            continue
        row_count = int(item.get("row_count") or 0)
        cursor = int(item.get("cursor") or 0)
        if item.get("state") == "completed":
            total += row_count
        else:
            total += max(0, min(cursor, row_count))
    return total


def _row_count(status: dict[str, Any]) -> int:
    return sum(int(item.get("row_count") or 0) for item in status.get("files") or [])


def _checkpoint(
    config: ReplayConfig,
    status: dict[str, Any] | None = None,
    run_id: str | None = None,
    run_name: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "protocol": config.protocol,
        "dataset_id": config.dataset_id,
        "csv_file": config.csv_file,
        "csv_source": config.csv_source,
        "frequency_hz": config.frequency_hz,
        "loop_mode": config.loop_mode,
        "timestamp_mode": config.timestamp_mode,
    }
    if run_id:
        data["run_id"] = run_id
    if run_name:
        data["run_name"] = run_name
    if status is not None:
        data.update(
            {
                "state": status.get("state"),
                "file_count": status.get("file_count"),
                "tag_count": status.get("tag_count"),
                "row_count": status.get("row_count"),
                "cursor": status.get("cursor"),
                "files": status.get("files") or [],
            }
        )
    return data


def _safe_job_prefix(job_id: str) -> str:
    suffix = job_id.removeprefix("job_")
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", suffix).strip("_")
    return f"job_{cleaned[:8] or 'replay'}"


def _namespace_tag(tag: TagMapping, prefix: str, node_id_prefix: str) -> TagMapping:
    cloned = tag.model_copy(deep=True)
    tag_leaf = re.sub(r"[^A-Za-z0-9_]+", "_", cloned.tag_name or cloned.csv_column).strip("_") or "tag"
    node_leaf = str(cloned.node_id or tag_leaf).split(".")[-1]
    cloned.tag_name = f"{prefix}_{tag_leaf}"
    cloned.node_id = f"{node_id_prefix}.{prefix}.{node_leaf}"
    return cloned


def _managed_config(job_id: str, config: ReplayConfig) -> ReplayConfig:
    cloned = config.model_copy(deep=True)
    prefix = _safe_job_prefix(job_id)
    cloned.tags = [_namespace_tag(tag, prefix, cloned.node_id_prefix) for tag in cloned.tags]
    if cloned.mqtt_client_id:
        cloned.mqtt_client_id = f"{cloned.mqtt_client_id}-{prefix}"
    return cloned


def start_replay_job(
    simulator: MultiSimulatorEngine,
    config: ReplayConfig,
    name: str | None = None,
    run_id: str | None = None,
    run_name: str | None = None,
) -> JobRecord:
    job_name = name or f"Replay {config.dataset_id or config.csv_file or config.protocol}"
    job = job_manager.create_job(job_name, "replay_dataset", dataset_id=config.dataset_id)
    managed_config = _managed_config(job.job_id, config)
    job_manager.update_job(job.job_id, checkpoint=_checkpoint(managed_config, run_id=run_id, run_name=run_name), active_bottleneck=managed_config.protocol)
    control = _control(job.job_id)
    control["stop"].clear()
    control["pause"].clear()

    def runner(job_id: str) -> None:
        asyncio.run(_run_replay_job(job_id, simulator, managed_config, control, run_id=run_id, run_name=run_name))

    job_manager.run_background(job.job_id, runner)
    return job_manager.get_job(job.job_id)


async def _run_replay_job(
    job_id: str,
    simulator: MultiSimulatorEngine,
    config: ReplayConfig,
    control: dict[str, threading.Event],
    run_id: str | None = None,
    run_name: str | None = None,
) -> None:
    started = time.perf_counter()
    _event(logging.INFO, "replay_job.started", "Replay job started.", job_id=job_id, protocol=config.protocol, dataset_id=config.dataset_id, file=config.csv_file)
    try:
        await simulator.add_job_config(job_id, config)
        await simulator.start_job(job_id)
        while not control["stop"].is_set():
            if control["pause"].is_set():
                await simulator.stop_job(job_id)
                status = simulator.get_job_status(job_id)
                job_manager.update_job(
                    job_id,
                    state="paused",
                    message="Replay paused.",
                    current_step="paused",
                    checkpoint=_checkpoint(config, status, run_id=run_id, run_name=run_name),
                )
                while control["pause"].is_set() and not control["stop"].is_set():
                    await asyncio.sleep(0.2)
                if control["stop"].is_set():
                    break
                await simulator.start_job(job_id)
                job_manager.update_job(job_id, state="running", message="Replay resumed.", current_step="running")

            status = simulator.get_job_status(job_id)
            rows_done = _rows_done(status)
            total_rows = _row_count(status)
            elapsed = max(time.perf_counter() - started, 0.001)
            completed = status.get("state") == "completed" or all(
                item.get("state") == "completed" for item in status.get("files") or []
            )
            progress = 100.0 if completed else (rows_done / total_rows * 100.0 if total_rows and config.loop_mode != "loop_forever" else 0.0)
            job_manager.update_job(
                job_id,
                state="running",
                progress_percent=max(0.0, min(100.0, progress)),
                current_step=f"{status.get('state') or 'running'}:{status.get('protocol') or config.protocol}",
                message="Replay running.",
                rows_done=rows_done,
                rows_per_sec=rows_done / elapsed,
                queue_depth=int(status.get("file_count") or 0),
                active_bottleneck=status.get("protocol") or config.protocol,
                checkpoint=_checkpoint(config, status, run_id=run_id, run_name=run_name),
            )
            if status.get("state") == "error":
                raise RuntimeError(str(status.get("last_error") or "Replay failed."))
            if completed:
                completed_status = {**status, "state": "completed"}
                job_manager.mark_completed(
                    job_id,
                    "Replay completed.",
                    rows_done=rows_done,
                    current_step="completed",
                    checkpoint=_checkpoint(config, completed_status, run_id=run_id, run_name=run_name),
                )
                await simulator.remove_job(job_id)
                _event(logging.INFO, "replay_job.completed", "Replay job completed.", job_id=job_id, rows_done=rows_done)
                return
            await asyncio.sleep(0.5)

        status = simulator.get_job_status(job_id)
        await simulator.stop_job(job_id, remove=True)
        job_manager.update_job(
            job_id,
            state="cancelled",
            completed_at=utc_now_iso(),
            message="Replay stopped.",
            current_step="stopped",
            checkpoint={**_checkpoint(config, status, run_id=run_id, run_name=run_name), "stopped": True},
        )
        _event(logging.INFO, "replay_job.stopped", "Replay job stopped.", job_id=job_id)
    except Exception as exc:
        try:
            await simulator.stop_job(job_id, remove=True)
        except Exception:
            pass
        _event(logging.ERROR, "replay_job.failed", "Replay job failed.", job_id=job_id, error=str(exc))
        job_manager.mark_failed(job_id, str(exc))
    finally:
        _remove_control(job_id)


def stop_replay_job(job_id: str) -> JobRecord:
    job = _ensure_replay_job(job_id)
    if job.state in {"completed", "failed", "cancelled"}:
        return job
    if job_id not in _active_control_job_ids():
        return job_manager.update_job(
            job_id,
            state="cancelled",
            completed_at=utc_now_iso(),
            message="Replay stopped. No active worker was attached to this persisted job.",
            current_step="stopped",
            checkpoint={**(job.checkpoint or {}), "stopped": True, "stale_worker": True},
        )
    _control(job_id)["stop"].set()
    return job_manager.update_job(job_id, message="Stop requested.", current_step="stopping")


def pause_replay_job(job_id: str) -> JobRecord:
    _ensure_replay_job(job_id)
    _control(job_id)["pause"].set()
    return job_manager.pause_job(job_id)


def resume_replay_job(job_id: str) -> JobRecord:
    _ensure_replay_job(job_id)
    _control(job_id)["pause"].clear()
    return job_manager.update_job(job_id, state="running", message="Resume requested.", current_step="resuming")
