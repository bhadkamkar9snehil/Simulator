from __future__ import annotations

import logging
import time
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from app.models import GenerateJobRequest, GenerateRequest, RegisterDatasetRequest, ReplayConfig, ReplayFilesConfig, SavedConfig, VideoJobRequest, WorkloadRunRequest
from app import csv_manager, config_store, dataset_manager, job_manager
from app.enterprise_generation import start_generate_job
from app.video_engine import start_video_job
from app.generator_registry import list_generators, get_generator
from app.generator_engine import generate_csv
from app.http_streams import ndjson_generator, sse_generator, stream_hub, stream_snapshot, websocket_loop
from app.protocol_adapter import DualProtocolAdapter
from app.multi_simulator import MultiSimulatorEngine
from app.replay_jobs import (
    list_replay_jobs,
    pause_replay_job,
    resume_replay_job,
    start_replay_job,
    stop_replay_job,
)
from app.workloads import control_workload_run, get_workload_run, list_workload_runs, start_workload_run

router = APIRouter(prefix="/api")
protocol_adapter = DualProtocolAdapter()
simulator = MultiSimulatorEngine(protocol_adapter)
logger = logging.getLogger("uvicorn.error")


def _event(level: int, event: str, message: str, **fields) -> None:
    logger.log(level, message, extra={"event": event, "fields": fields, "service": "Industrial", "source": "api"})


def error_response(exc: Exception) -> HTTPException:
    _event(logging.ERROR, "api.request.failed", "API request failed.", error=str(exc), error_type=type(exc).__name__)
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail={"error": str(exc)})
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail={"error": str(exc)})
    return HTTPException(status_code=400, detail={"error": str(exc)})


@router.get("/health")
def health() -> dict:
    parquet_available = True
    parquet_error = ""
    try:
        import pyarrow  # noqa: F401
    except Exception as exc:
        parquet_available = False
        parquet_error = str(exc)
    return {"status": "ok", "parquet_available": parquet_available, "parquet_error": parquet_error}


@router.get("/status")
def status() -> dict:
    return {"backend": "ok", "protocol": protocol_adapter.get_status(), "simulator": simulator.get_status(), "streams": stream_hub.metrics()}


@router.get("/generators")
def generators() -> dict:
    return {"generators": [g.model_dump() for g in list_generators()]}


@router.get("/generators/{domain_id}/spec")
def generator_spec(domain_id: str) -> dict:
    try:
        return get_generator(domain_id).get_spec().model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/generators/{domain_id}/generate")
def generator_generate(domain_id: str, request: GenerateRequest) -> dict:
    try:
        start = time.perf_counter()
        _event(logging.INFO, "generator.generate.requested", "CSV generation requested.", domain=domain_id, scenario=request.scenario, output=request.output_filename, load_into_replay=request.load_into_replay)
        response = generate_csv(domain_id, request)
        _event(logging.INFO, "generator.generate.completed", "CSV generation completed.", domain=domain_id, scenario=request.scenario, file=response.filename, rows=response.row_count, columns=response.column_count, load_into_replay=response.loaded_into_replay, duration_ms=int((time.perf_counter() - start) * 1000))
        return response.model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/generators/{domain_id}/generate-job")
def generator_generate_job(domain_id: str, request: GenerateJobRequest) -> dict:
    try:
        job_id = start_generate_job(domain_id, request)
        _event(logging.INFO, "generator.generate_job.created", "Generation job created.", domain=domain_id, job_id=job_id, output_format=request.output_format)
        return job_manager.get_job(job_id).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.get("/jobs")
def jobs() -> dict:
    return {"jobs": [job.model_dump() for job in job_manager.list_jobs()]}


@router.get("/jobs/{job_id}")
def job_detail(job_id: str) -> dict:
    try:
        return job_manager.get_job(job_id).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/workloads/concurrent-run")
def workload_concurrent_run(request: WorkloadRunRequest) -> dict:
    try:
        result = start_workload_run(simulator, request)
        _event(logging.INFO, "workload.concurrent_run.created", "Concurrent workload run created.", run_id=result.get("run_id"), jobs=result.get("job_count"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.get("/workloads/runs")
def workload_runs() -> dict:
    try:
        return {"runs": list_workload_runs()}
    except Exception as exc:
        raise error_response(exc)


@router.get("/workloads/runs/{run_id}")
def workload_run_detail(run_id: str) -> dict:
    try:
        return get_workload_run(run_id)
    except Exception as exc:
        raise error_response(exc)


@router.post("/workloads/runs/{run_id}/pause")
def workload_run_pause(run_id: str) -> dict:
    try:
        result = control_workload_run(run_id, "pause")
        _event(logging.INFO, "workload.run.paused", "Workload run pause requested.", run_id=run_id, jobs=result.get("job_count"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/workloads/runs/{run_id}/resume")
def workload_run_resume(run_id: str) -> dict:
    try:
        result = control_workload_run(run_id, "resume")
        _event(logging.INFO, "workload.run.resumed", "Workload run resume requested.", run_id=run_id, jobs=result.get("job_count"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/workloads/runs/{run_id}/stop")
def workload_run_stop(run_id: str) -> dict:
    try:
        result = control_workload_run(run_id, "stop")
        _event(logging.INFO, "workload.run.stopped", "Workload run stop requested.", run_id=run_id, jobs=result.get("job_count"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/jobs/{job_id}/pause")
def job_pause(job_id: str) -> dict:
    try:
        return job_manager.pause_job(job_id).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/jobs/{job_id}/resume")
def job_resume(job_id: str) -> dict:
    try:
        return job_manager.resume_job(job_id).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/jobs/{job_id}/cancel")
def job_cancel(job_id: str) -> dict:
    try:
        return job_manager.cancel_job(job_id).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.get("/datasets")
def datasets() -> dict:
    try:
        return {"datasets": [item.model_dump() for item in dataset_manager.list_datasets()]}
    except Exception as exc:
        raise error_response(exc)


@router.get("/datasets/{dataset_id}/metadata")
def dataset_metadata(dataset_id: str) -> dict:
    try:
        return dataset_manager.get_dataset(dataset_id).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.get("/datasets/{dataset_id}/preview")
def dataset_preview(dataset_id: str, limit: int = Query(10, ge=1, le=100)) -> dict:
    try:
        return dataset_manager.preview(dataset_id, limit)
    except Exception as exc:
        raise error_response(exc)


@router.post("/datasets/register-local")
def dataset_register_local(request: RegisterDatasetRequest) -> dict:
    try:
        manifest = dataset_manager.register_local(request)
        _event(logging.INFO, "dataset.register.completed", "Dataset registered.", dataset_id=manifest.dataset_id, path=manifest.path)
        return manifest.model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/datasets/{dataset_id}/scan")
def dataset_scan(dataset_id: str) -> dict:
    try:
        job = job_manager.create_job(f"Scan {dataset_id}", "scan_dataset", dataset_id=dataset_id)

        def run_scan(job_id: str) -> None:
            dataset_manager.scan_dataset(dataset_id, job_id=job_id)
            job_manager.mark_completed(job_id, "Dataset scan completed.")

        job_manager.run_background(job.job_id, run_scan)
        return job.model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.delete("/datasets/{dataset_id}")
def dataset_delete(dataset_id: str, delete_files: bool = Query(False)) -> dict:
    try:
        return dataset_manager.delete_dataset(dataset_id, delete_files=delete_files)
    except Exception as exc:
        raise error_response(exc)


@router.post("/video/generate-job")
def video_generate_job(request: VideoJobRequest) -> dict:
    try:
        job_id = start_video_job(request)
        return job_manager.get_job(job_id).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/csv/upload")
def csv_upload(file: UploadFile = File(...)) -> dict:
    try:
        start = time.perf_counter()
        result = csv_manager.save_upload(file)
        _event(logging.INFO, "csv.upload.completed", "CSV upload completed.", file=result.filename, source=result.source, rows=result.row_count, columns=result.column_count, duration_ms=int((time.perf_counter() - start) * 1000))
        return result.model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.get("/csv/files")
def csv_files() -> dict:
    try:
        return {"files": [r.model_dump() for r in csv_manager.list_files()]}
    except Exception as exc:
        raise error_response(exc)


@router.get("/csv/files/{filename}/metadata")
def csv_metadata(filename: str, source: str = Query("generated")) -> dict:
    try:
        return csv_manager.metadata(filename, source).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.get("/csv/files/{filename}/preview")
def csv_preview(filename: str, source: str = Query("generated"), limit: int = Query(10, ge=1, le=100)) -> dict:
    try:
        return csv_manager.preview(filename, source, limit).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/csv/files/{filename}/load")
def csv_load(filename: str, source: str = Query("generated")) -> dict:
    try:
        result = csv_manager.metadata(filename, source)
        _event(logging.INFO, "csv.metadata.loaded", "CSV metadata loaded.", file=result.filename, source=result.source, rows=result.row_count, columns=result.column_count)
        return result.model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.delete("/csv/files/{filename}")
def csv_delete(filename: str, source: str = Query("generated")) -> dict:
    try:
        result = csv_manager.delete_file(filename, source)
        _event(logging.WARN, "csv.delete.completed", "CSV file deleted.", file=filename, source=source)
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/configure")
async def replay_configure(config: ReplayConfig) -> dict:
    try:
        start = time.perf_counter()
        result = await simulator.configure(config)
        _event(logging.INFO, "replay.configure.completed", "Replay configured.", protocol=config.protocol, file=config.csv_file, source=config.csv_source, tags=result.get("tag_count"), duration_ms=int((time.perf_counter() - start) * 1000))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/configure-files")
async def replay_configure_files(config: ReplayFilesConfig) -> dict:
    try:
        start = time.perf_counter()
        result = await simulator.configure_files(config)
        _event(logging.INFO, "replay.configure_files.completed", "Replay file plan configured.", protocol=config.protocol, files=result.get("file_count"), tags=result.get("tag_count"), assignment=result.get("assignment_mode"), duration_ms=int((time.perf_counter() - start) * 1000))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.get("/replay/jobs")
def replay_jobs() -> dict:
    return {"jobs": [job.model_dump() for job in list_replay_jobs()]}


@router.post("/replay/jobs")
def replay_job_start(config: ReplayConfig) -> dict:
    try:
        job = start_replay_job(simulator, config)
        _event(logging.INFO, "replay.job.created", "Replay job created.", job_id=job.job_id, protocol=config.protocol, dataset_id=config.dataset_id, file=config.csv_file)
        return job.model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/jobs/{job_id}/stop")
def replay_job_stop(job_id: str) -> dict:
    try:
        return stop_replay_job(job_id).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/jobs/{job_id}/pause")
def replay_job_pause(job_id: str) -> dict:
    try:
        return pause_replay_job(job_id).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/jobs/{job_id}/resume")
def replay_job_resume(job_id: str) -> dict:
    try:
        return resume_replay_job(job_id).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/start")
async def replay_start() -> dict:
    try:
        result = await simulator.start()
        _event(logging.INFO, "replay.start.completed", "Replay started.", status=result.get("status"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/stop")
async def replay_stop() -> dict:
    try:
        result = await simulator.stop()
        _event(logging.INFO, "replay.stop.completed", "Replay stopped.", status=result.get("status"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/start-opcua")
async def replay_start_opcua() -> dict:
    try:
        result = await simulator.start_protocol("opcua")
        _event(logging.INFO, "replay.protocol_start.completed", "Replay protocol started.", protocol="opcua", status=result.get("status"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/stop-opcua")
async def replay_stop_opcua() -> dict:
    try:
        result = await simulator.stop_protocol("opcua")
        _event(logging.INFO, "replay.protocol_stop.completed", "Replay protocol stopped.", protocol="opcua", status=result.get("status"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/start-mqtt")
async def replay_start_mqtt() -> dict:
    try:
        result = await simulator.start_protocol("mqtt")
        _event(logging.INFO, "replay.protocol_start.completed", "Replay protocol started.", protocol="mqtt", status=result.get("status"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/stop-mqtt")
async def replay_stop_mqtt() -> dict:
    try:
        result = await simulator.stop_protocol("mqtt")
        _event(logging.INFO, "replay.protocol_stop.completed", "Replay protocol stopped.", protocol="mqtt", status=result.get("status"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/start-both")
async def replay_start_both() -> dict:
    try:
        result = await simulator.start_protocol("both")
        _event(logging.INFO, "replay.protocol_start.completed", "Replay protocols started.", protocol="both", status=result.get("status"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/stop-both")
async def replay_stop_both() -> dict:
    try:
        result = await simulator.stop_protocol("both")
        _event(logging.INFO, "replay.protocol_stop.completed", "Replay protocols stopped.", protocol="both", status=result.get("status"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/restart")
async def replay_restart() -> dict:
    try:
        result = await simulator.restart()
        _event(logging.INFO, "replay.restart.completed", "Replay restarted.", status=result.get("status"), cursor=result.get("cursor"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/reset-cursor")
async def replay_reset_cursor() -> dict:
    try:
        result = await simulator.reset_cursor()
        _event(logging.INFO, "replay.cursor_reset.completed", "Replay cursor reset.", status=result.get("status"), cursor=result.get("cursor"))
        return result
    except Exception as exc:
        raise error_response(exc)


@router.get("/replay/status")
def replay_status() -> dict:
    return simulator.get_status()


@router.get("/replay/current-values")
def replay_current_values() -> dict:
    return simulator.get_current_values().model_dump()


@router.get("/streams/status")
def streams_status() -> dict:
    return {"streams": stream_hub.metrics()}


@router.get("/streams/snapshot")
def streams_snapshot(value_limit: int = Query(100, ge=0, le=1000)) -> dict:
    return stream_snapshot(simulator, protocol_adapter, value_limit=value_limit)


@router.get("/streams/ndjson")
def streams_ndjson(
    interval_ms: int = Query(1000, ge=50, le=60000),
    limit: int | None = Query(None, ge=1, le=10000),
    value_limit: int = Query(100, ge=0, le=1000),
) -> StreamingResponse:
    return StreamingResponse(
        ndjson_generator(lambda: stream_snapshot(simulator, protocol_adapter, value_limit=value_limit), interval_ms, limit),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/streams/sse")
def streams_sse(
    interval_ms: int = Query(1000, ge=50, le=60000),
    limit: int | None = Query(None, ge=1, le=10000),
    value_limit: int = Query(100, ge=0, le=1000),
) -> StreamingResponse:
    return StreamingResponse(
        sse_generator(lambda: stream_snapshot(simulator, protocol_adapter, value_limit=value_limit), interval_ms, limit),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.websocket("/streams/ws")
async def streams_websocket(
    websocket: WebSocket,
    interval_ms: int = Query(1000, ge=50, le=60000),
    limit: int | None = Query(None, ge=1, le=10000),
    value_limit: int = Query(100, ge=0, le=1000),
) -> None:
    await websocket.accept()
    try:
        await websocket_loop(
            websocket.send_json,
            lambda: stream_snapshot(simulator, protocol_adapter, value_limit=value_limit),
            interval_ms,
            limit,
        )
    except WebSocketDisconnect:
        return


@router.get("/configs")
def configs() -> dict:
    try:
        return {"configs": [c.model_dump() for c in config_store.list_configs()]}
    except Exception as exc:
        raise error_response(exc)


@router.post("/configs")
def create_config(config: SavedConfig) -> dict:
    try:
        result = config_store.save_config(config)
        _event(logging.INFO, "config.save.completed", "Configuration saved.", name=result.name)
        return result.model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.get("/configs/{name}")
def get_config(name: str) -> dict:
    try:
        return config_store.load_config(name).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.put("/configs/{name}")
def update_config(name: str, config: SavedConfig) -> dict:
    try:
        config.name = name
        result = config_store.save_config(config)
        _event(logging.INFO, "config.update.completed", "Configuration updated.", name=result.name)
        return result.model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.delete("/configs/{name}")
def remove_config(name: str) -> dict:
    try:
        result = config_store.delete_config(name)
        _event(logging.WARN, "config.delete.completed", "Configuration deleted.", name=name)
        return result
    except Exception as exc:
        raise error_response(exc)
