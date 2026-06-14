from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from app.models import GenerateRequest, ReplayConfig, ReplayFilesConfig, SavedConfig
from app import csv_manager, config_store
from app.generator_registry import list_generators, get_generator
from app.generator_engine import generate_csv
from app.protocol_adapter import DualProtocolAdapter
from app.multi_simulator import MultiSimulatorEngine

router = APIRouter(prefix="/api")
protocol_adapter = DualProtocolAdapter()
simulator = MultiSimulatorEngine(protocol_adapter)


def error_response(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail={"error": str(exc)})
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail={"error": str(exc)})
    return HTTPException(status_code=400, detail={"error": str(exc)})


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status")
def status() -> dict:
    return {"backend": "ok", "protocol": protocol_adapter.get_status(), "simulator": simulator.get_status()}


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
        response = generate_csv(domain_id, request)
        return response.model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.post("/csv/upload")
def csv_upload(file: UploadFile = File(...)) -> dict:
    try:
        return csv_manager.save_upload(file).model_dump()
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
        return csv_manager.metadata(filename, source).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.delete("/csv/files/{filename}")
def csv_delete(filename: str, source: str = Query("generated")) -> dict:
    try:
        return csv_manager.delete_file(filename, source)
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/configure")
async def replay_configure(config: ReplayConfig) -> dict:
    try:
        return await simulator.configure(config)
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/configure-files")
async def replay_configure_files(config: ReplayFilesConfig) -> dict:
    try:
        return await simulator.configure_files(config)
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/start")
async def replay_start() -> dict:
    try:
        return await simulator.start()
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/stop")
async def replay_stop() -> dict:
    try:
        return await simulator.stop()
    except Exception as exc:
        raise error_response(exc)




@router.post("/replay/start-opcua")
async def replay_start_opcua() -> dict:
    try:
        return await simulator.start_protocol("opcua")
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/stop-opcua")
async def replay_stop_opcua() -> dict:
    try:
        return await simulator.stop_protocol("opcua")
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/start-mqtt")
async def replay_start_mqtt() -> dict:
    try:
        return await simulator.start_protocol("mqtt")
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/stop-mqtt")
async def replay_stop_mqtt() -> dict:
    try:
        return await simulator.stop_protocol("mqtt")
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/start-both")
async def replay_start_both() -> dict:
    try:
        return await simulator.start_protocol("both")
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/stop-both")
async def replay_stop_both() -> dict:
    try:
        return await simulator.stop_protocol("both")
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/restart")
async def replay_restart() -> dict:
    try:
        return await simulator.restart()
    except Exception as exc:
        raise error_response(exc)


@router.post("/replay/reset-cursor")
async def replay_reset_cursor() -> dict:
    try:
        return await simulator.reset_cursor()
    except Exception as exc:
        raise error_response(exc)


@router.get("/replay/status")
def replay_status() -> dict:
    return simulator.get_status()


@router.get("/replay/current-values")
def replay_current_values() -> dict:
    return simulator.get_current_values().model_dump()


@router.get("/configs")
def configs() -> dict:
    try:
        return {"configs": [c.model_dump() for c in config_store.list_configs()]}
    except Exception as exc:
        raise error_response(exc)


@router.post("/configs")
def create_config(config: SavedConfig) -> dict:
    try:
        return config_store.save_config(config).model_dump()
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
        return config_store.save_config(config).model_dump()
    except Exception as exc:
        raise error_response(exc)


@router.delete("/configs/{name}")
def remove_config(name: str) -> dict:
    try:
        return config_store.delete_config(name)
    except Exception as exc:
        raise error_response(exc)
