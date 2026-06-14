from __future__ import annotations

import os
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from app.api import router, simulator
from app.csv_manager import ensure_dirs as ensure_csv_dirs
from app.config_store import ensure_dir as ensure_config_dir

def get_base_dir() -> Path:
    if os.environ.get("ITS_BASE_DIR"):
        return Path(os.environ["ITS_BASE_DIR"]).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

ROOT = get_base_dir()
FRONTEND = ROOT / "frontend"

app = FastAPI(title="Industrial Dual Protocol Tag Simulator", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


@app.on_event("startup")
async def startup() -> None:
    ensure_csv_dirs()
    ensure_config_dir()


@app.on_event("shutdown")
async def shutdown() -> None:
    await simulator.stop()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")
