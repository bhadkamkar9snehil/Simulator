from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from app import csv_manager, dataset_manager
from app import job_manager
from app.models import JobRecord
from app.models import ReplayConfig, VideoJobRequest, WorkloadReplayOptions, WorkloadRunRequest, WorkloadSourceJobOptions
from app.multi_simulator import MultiSimulatorEngine
from app.replay_jobs import pause_replay_job, resume_replay_job, start_replay_job, stop_replay_job
from app.source_simulators.jobs import pause_source_job, resume_source_job, start_source_job, stop_source_job
from app.type_inference import infer_types
from app.video_engine import start_video_job

ACTIVE_STATES = {"queued", "running", "paused"}
TERMINAL_STATES = {"completed", "failed", "cancelled"}


def _new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def _tags_for_csv_path(path: Path) -> list[Any]:
    columns, _preview, type_sample, _row_count = csv_manager.scan_rows(path, preview_rows=10)
    inferred = infer_types(type_sample, columns)
    return csv_manager.default_tag_mappings(columns, inferred)


def _csv_dataset_metadata(dataset_id: str) -> tuple[str, str, list[Any]]:
    manifest = dataset_manager.get_dataset(dataset_id)
    if manifest.storage_format != "csv" or not manifest.path:
        raise ValueError("Concurrent replay currently supports CSV datasets. Generate or register a CSV dataset for this run.")
    path = dataset_manager.dataset_path(manifest)
    source = manifest.source if manifest.source in {"uploaded", "generated", "sample"} else "generated"
    return path.name, source, _tags_for_csv_path(path)


def _replay_config(options: WorkloadReplayOptions) -> ReplayConfig:
    if options.dataset_id:
        filename, source, tags = _csv_dataset_metadata(options.dataset_id)
        dataset_id = options.dataset_id
    else:
        filename = options.csv_file
        source = options.csv_source
        tags = csv_manager.metadata(filename, source).default_tag_mappings
        dataset_id = None

    return ReplayConfig(
        dataset_id=dataset_id,
        csv_file=filename,
        csv_source=source,  # type: ignore[arg-type]
        protocol=options.protocol,
        frequency_hz=options.frequency_hz,
        loop_mode=options.loop_mode,
        timestamp_mode=options.timestamp_mode,
        max_rows=options.max_rows,
        tags=tags,
    )


def _start_source(connector_id: str, options: WorkloadSourceJobOptions, run_id: str, run_name: str) -> dict[str, Any] | None:
    if not options.enabled:
        return None
    job = start_source_job(
        connector_id,
        options.entity,
        interval_seconds=options.interval_seconds,
        max_cycles=options.max_cycles,
        mode=options.mode,
        filter_text=options.filter_text,
        top=options.top,
        watermark=options.watermark,
        cycle_parameters=options.cycle_parameters,
        run_id=run_id,
        run_name=run_name,
    )
    return job.model_dump()


def _start_video(request: VideoJobRequest, run_id: str, run_name: str) -> dict[str, Any]:
    job_id = start_video_job(request)
    job_manager.update_job(job_id, checkpoint={"run_id": run_id, "run_name": run_name, "connector_id": "video"})
    return job_manager.get_job(job_id).model_dump()


def start_workload_run(simulator: MultiSimulatorEngine, request: WorkloadRunRequest) -> dict[str, Any]:
    run_id = request.run_id or _new_run_id()
    run_name = request.name.strip() or "Concurrent simulator run"
    started: list[tuple[str, str]] = []
    jobs: list[dict[str, Any]] = []

    try:
        for replay_options in request.replays:
            if not replay_options.enabled:
                continue
            replay = _replay_config(replay_options)
            job = start_replay_job(
                simulator,
                replay,
                name=f"{run_name} - Replay {replay.protocol.upper()}",
                run_id=run_id,
                run_name=run_name,
            )
            started.append(("replay", job.job_id))
            jobs.append(job.model_dump())

        for connector_id, options_list in (("sap_pp", request.sap_pp_jobs), ("lims_odbc", request.lims_odbc_jobs)):
            for options in options_list:
                job_payload = _start_source(connector_id, options, run_id, run_name)
                if job_payload is not None:
                    started.append(("source", str(job_payload["job_id"])))
                    jobs.append(job_payload)

        for video_request in request.video_jobs:
            job_payload = _start_video(video_request, run_id, run_name)
            started.append(("video", str(job_payload["job_id"])))
            jobs.append(job_payload)

    except Exception:
        for kind, job_id in started:
            try:
                if kind == "replay":
                    stop_replay_job(job_id)
                elif kind == "source":
                    stop_source_job(job_id)
                else:
                    job_manager.cancel_job(job_id)
            except Exception:
                pass
        raise

    if not jobs:
        raise ValueError("Enable at least one child simulation for a concurrent run.")

    return {
        "run_id": run_id,
        "name": run_name,
        "job_count": len(jobs),
        "jobs": jobs,
        "streams": {
            "snapshot": "/api/streams/snapshot",
            "ndjson": "/api/streams/ndjson",
            "sse": "/api/streams/sse",
            "status": "/api/streams/status",
        },
    }


def _run_id_for_job(job: JobRecord) -> str | None:
    checkpoint = job.checkpoint or {}
    run_id = checkpoint.get("run_id")
    return str(run_id) if run_id else None


def _run_name_for_job(job: JobRecord, run_id: str) -> str:
    checkpoint = job.checkpoint or {}
    return str(checkpoint.get("run_name") or run_id)


def _run_state(children: list[JobRecord]) -> str:
    states = {job.state for job in children}
    if any(state in {"running", "queued"} for state in states):
        return "running"
    if "paused" in states:
        return "paused"
    if "failed" in states:
        return "failed"
    if states == {"completed"}:
        return "completed"
    if states == {"cancelled"}:
        return "cancelled"
    if states <= TERMINAL_STATES and "failed" not in states:
        return "completed" if "completed" in states else "cancelled"
    return "mixed"


def _protocols_for_run(children: list[JobRecord]) -> list[str]:
    protocols = set()
    for job in children:
        protocol = (job.checkpoint or {}).get("protocol")
        if protocol:
            protocols.add(str(protocol))
    return sorted(protocols)


def _connectors_for_run(children: list[JobRecord]) -> list[str]:
    connectors = set()
    for job in children:
        connector = (job.checkpoint or {}).get("connector_id")
        if connector:
            connectors.add(str(connector))
    return sorted(connectors)


def summarize_workload_run(run_id: str, children: list[JobRecord]) -> dict[str, Any]:
    if not children:
        raise KeyError(f"Workload run not found: {run_id}")
    sorted_children = sorted(children, key=lambda job: job.updated_at or "", reverse=True)
    active_jobs = [job for job in sorted_children if job.state in ACTIVE_STATES]
    progress_values = [float(job.progress_percent or 0.0) for job in sorted_children]
    return {
        "run_id": run_id,
        "name": _run_name_for_job(sorted_children[0], run_id),
        "state": _run_state(sorted_children),
        "job_count": len(sorted_children),
        "active_jobs": len(active_jobs),
        "completed_jobs": sum(1 for job in sorted_children if job.state == "completed"),
        "failed_jobs": sum(1 for job in sorted_children if job.state == "failed"),
        "cancelled_jobs": sum(1 for job in sorted_children if job.state == "cancelled"),
        "progress_percent": sum(progress_values) / len(progress_values) if progress_values else 0.0,
        "rows_done": sum(int(job.rows_done or 0) for job in sorted_children),
        "rows_per_sec": sum(float(job.rows_per_sec or 0.0) for job in sorted_children),
        "started_at": min((job.started_at for job in sorted_children if job.started_at), default=None),
        "updated_at": max((job.updated_at for job in sorted_children if job.updated_at), default=None),
        "protocols": _protocols_for_run(sorted_children),
        "connectors": _connectors_for_run(sorted_children),
        "children": [job.model_dump() for job in sorted_children],
    }


def list_workload_runs() -> list[dict[str, Any]]:
    grouped: dict[str, list[JobRecord]] = {}
    for job in job_manager.list_jobs():
        run_id = _run_id_for_job(job)
        if not run_id:
            continue
        grouped.setdefault(run_id, []).append(job)
    runs = [summarize_workload_run(run_id, children) for run_id, children in grouped.items()]
    return sorted(runs, key=lambda run: run.get("updated_at") or "", reverse=True)


def get_workload_run(run_id: str) -> dict[str, Any]:
    children = [job for job in job_manager.list_jobs() if _run_id_for_job(job) == run_id]
    return summarize_workload_run(run_id, children)


def _control_child_job(job: JobRecord, action: str) -> JobRecord:
    if action not in {"pause", "resume", "stop"}:
        raise ValueError(f"Unsupported run action: {action}")
    if action != "resume" and job.state in TERMINAL_STATES:
        return job
    if job.type == "replay_dataset":
        if action == "pause":
            return pause_replay_job(job.job_id)
        if action == "resume":
            return resume_replay_job(job.job_id)
        return stop_replay_job(job.job_id)
    if job.type == "source_simulation":
        if action == "pause":
            return pause_source_job(job.job_id)
        if action == "resume":
            return resume_source_job(job.job_id)
        return stop_source_job(job.job_id)
    if action == "pause":
        return job_manager.pause_job(job.job_id)
    if action == "resume":
        return job_manager.resume_job(job.job_id)
    return job_manager.cancel_job(job.job_id)


def control_workload_run(run_id: str, action: str) -> dict[str, Any]:
    children = [job for job in job_manager.list_jobs() if _run_id_for_job(job) == run_id]
    if not children:
        raise KeyError(f"Workload run not found: {run_id}")
    for job in children:
        _control_child_job(job, action)
    return get_workload_run(run_id)
