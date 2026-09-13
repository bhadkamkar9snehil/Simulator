from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config_store import ensure_dir as ensure_config_dir
from app.csv_manager import ensure_dirs as ensure_csv_dirs


def get_base_dir() -> Path:
    if os.environ.get("ITS_BASE_DIR"):
        return Path(os.environ["ITS_BASE_DIR"]).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = get_base_dir()
FRONTEND = ROOT / "frontend"
SUITE_ROOT = ROOT.parent
if str(SUITE_ROOT) not in sys.path:
    sys.path.insert(0, str(SUITE_ROOT))

from industrial_logging import configure_python_logging, emit_event  # noqa: E402
from app.api import router, simulator  # noqa: E402
from app.simulation.api import router as simulation_router  # noqa: E402
from app.simulation.odata import router as odata_router  # noqa: E402
from app.simulation.runtime import simulation_manager  # noqa: E402
from app.source_simulators.router import sap_odata_router, source_api_router  # noqa: E402

configure_python_logging(service="Industrial", source="python")
logger = logging.getLogger("industrial.api")

app = FastAPI(title="Unified Industrial Simulator", version="3.0.0-alpha.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(simulation_router)
app.include_router(odata_router)
app.include_router(source_api_router)
app.include_router(sap_odata_router)
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


@app.middleware("http")
async def log_http_request(request: Request, call_next):
    operation_id = request.headers.get("X-Operation-ID") or os.urandom(6).hex()
    start = time.perf_counter()
    fields = {
        "method": request.method,
        "path": request.url.path,
        "query": request.url.query,
        "client": request.client.host if request.client else "",
    }
    emit_event("http.request.start", "HTTP request started.", service="Industrial", source="http", operation_id=operation_id, fields=fields)
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        emit_event("http.request.failed", "HTTP request failed.", level="ERROR", service="Industrial", source="http", operation_id=operation_id, duration_ms=duration_ms, fields=fields, exc=exc)
        raise
    duration_ms = int((time.perf_counter() - start) * 1000)
    level = "ERROR" if response.status_code >= 500 else "WARN" if response.status_code >= 400 else "INFO"
    done_fields = {**fields, "status_code": response.status_code}
    emit_event("http.request.completed", "HTTP request completed.", level=level, service="Industrial", source="http", operation_id=operation_id, duration_ms=duration_ms, fields=done_fields)
    response.headers["X-Operation-ID"] = operation_id
    return response


@app.on_event("startup")
async def startup() -> None:
    emit_event("industrial.startup", "Industrial backend startup.", service="Industrial", source="lifecycle", fields={"root": ROOT, "frontend": FRONTEND})
    ensure_csv_dirs()
    ensure_config_dir()


@app.on_event("shutdown")
async def shutdown() -> None:
    emit_event("industrial.shutdown", "Industrial backend shutdown.", service="Industrial", source="lifecycle")
    await simulation_manager.shutdown()
    await simulator.stop()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")
