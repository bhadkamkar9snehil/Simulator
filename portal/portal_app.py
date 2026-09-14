from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
INDUSTRIAL_ROOT = ROOT / "industrial_simulator"
PORTAL_ROOT = ROOT / "portal"
UI_ROOT = PORTAL_ROOT / "ui"
for path in (ROOT, INDUSTRIAL_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.sql_server import run_sql_action as run_mssql  # noqa: E402
from suite_runtime import (  # noqa: E402
    VENV_PY as SUITE_VENV_PY,
    VENV_PYW as SUITE_VENV_PYW,
    clear_log as suite_clear_log,
    load_ports as suite_load_ports,
    logs_payload as suite_logs_payload,
    open_app_window as suite_open_app_window,
    save_ports as suite_save_ports,
    start_services as suite_start_services,
    status_payload as suite_status_payload,
    stop_services as suite_stop_services,
    validate_ports as suite_validate_ports,
)


def env_port(name: str, default: int, fallback_name: str | None = None) -> int:
    for key in (name, fallback_name):
        if not key:
            continue
        raw = str(os.environ.get(key, "")).strip()
        if not raw:
            continue
        try:
            return int(raw)
        except ValueError:
            continue
    return default


PORT = env_port("PORTAL_PORT", 8001)
INDUSTRIAL_PORT = env_port("INDUSTRIAL_PORT", 8000, "INDUSTRIAL_WEB_PORT")
OPCUA_PORT = env_port("OPCUA_PORT", 4840)
MQTT_BROKER_PORT = env_port("MQTT_BROKER_PORT", 1883, "MQTT_PORT")
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
DATA_DIR = PORTAL_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONNECTIONS_JSON = DATA_DIR / "connections.json"
MAPPINGS_JSON = DATA_DIR / "api_source_mappings.json"

app = FastAPI(title="Simulator Portal", version="3.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.mount("/ui", StaticFiles(directory=str(UI_ROOT)), name="ui")


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def read_store(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_store(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_service(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return {"ok": True, "status": response.status}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def current_industrial_rows() -> list[dict[str, Any]]:
    url = f"http://127.0.0.1:{INDUSTRIAL_PORT}/api/replay/current-values"
    with urllib.request.urlopen(url, timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))
    return [
        {
            "ts": item.get("last_updated") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "tag_name": item.get("tag_name") or item.get("node_id") or "tag",
            "value": str(item.get("value", "")),
            "unit": item.get("data_type", ""),
            "quality": "Good",
            "description": item.get("node_id", ""),
        }
        for item in data.get("values", [])
    ]


def launcher_config() -> dict[str, Any]:
    return {
        "industrial_web_port": INDUSTRIAL_PORT,
        "portal_port": PORT,
        "opcua_port": OPCUA_PORT,
        "mqtt_port": MQTT_BROKER_PORT,
        "mqtt_host": "localhost",
        "lan_ip": local_ip(),
    }


def inject_launcher_config(template: str, config: dict[str, Any]) -> str:
    assignment = f"window.SIMULATOR_LAUNCHER_CONFIG = {json.dumps(config)};"
    placeholder = "window.SIMULATOR_LAUNCHER_CONFIG = window.SIMULATOR_LAUNCHER_CONFIG || {};"
    if placeholder in template:
        return template.replace(placeholder, assignment, 1)
    return template.replace("<body>", f"<body>\n<script>{assignment}</script>", 1)


def page() -> str:
    template = (UI_ROOT / "index.html").read_text(encoding="utf-8")
    return inject_launcher_config(template, launcher_config())


def legacy_page() -> str:
    template = (PORTAL_ROOT / "simulator_ui.html").read_text(encoding="utf-8")
    template = inject_launcher_config(template, launcher_config())
    replacements = {
        'id="lpPortal" value="8001"': f'id="lpPortal" value="{PORT}"',
        'id="lpIndustrial" value="8000"': f'id="lpIndustrial" value="{INDUSTRIAL_PORT}"',
        'id="lpOpcua" value="4840"': f'id="lpOpcua" value="{OPCUA_PORT}"',
        'id="lpMqtt" value="1883"': f'id="lpMqtt" value="{MQTT_BROKER_PORT}"',
        'id="mqttPort" type="number" value="1883"': f'id="mqttPort" type="number" value="{MQTT_BROKER_PORT}"',
        'id="opcuaEndpoint" value="opc.tcp://localhost:4840/simulator"': f'id="opcuaEndpoint" value="opc.tcp://localhost:{OPCUA_PORT}/simulator"',
    }
    for old, new in replacements.items():
        template = template.replace(old, new)
    return template


@app.exception_handler(Exception)
async def unhandled_exception(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
def index() -> str:
    return page()


@app.get("/legacy", response_class=HTMLResponse)
def legacy() -> str:
    return legacy_page()


@app.get("/suite/status")
def suite_status() -> dict[str, Any]:
    return {
        "portal": {"ok": True, "port": PORT},
        "industrial": get_service(f"http://127.0.0.1:{INDUSTRIAL_PORT}/api/health"),
    }


@app.get("/launcher/config")
def launcher_status() -> dict[str, Any]:
    return suite_status_payload(suite_load_ports())


@app.get("/logs")
def logs(
    limit: int = Query(default=300),
    level: str = Query(default=""),
    source: str = Query(default=""),
    service: str = Query(default=""),
    event: str = Query(default=""),
    q: str = Query(default=""),
) -> dict[str, Any]:
    bounded_limit = max(50, min(limit, 1000))
    return suite_logs_payload(
        limit=bounded_limit,
        level=level,
        source=source,
        service=service,
        event=event,
        query=q,
    )


@app.get("/connections")
def connections() -> dict[str, Any]:
    return {"connections": read_store(CONNECTIONS_JSON, {})}


@app.get("/api-mappings")
def api_mappings() -> dict[str, Any]:
    return {"mappings": read_store(MAPPINGS_JSON, [])}


def _body(value: dict[str, Any] | None) -> dict[str, Any]:
    return value or {}


@app.post("/launcher/save")
def launcher_save(body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    payload = _body(body)
    ports = payload.get("ports") or suite_load_ports()
    errors = suite_validate_ports(ports)
    if errors:
        result = suite_status_payload(suite_load_ports())
        result.update({"ok": False, "message": "; ".join(errors)})
        return result
    suite_save_ports(ports)
    result = suite_status_payload(ports)
    result.update({"ok": True, "message": "Ports saved."})
    return result


@app.post("/launcher/start")
def launcher_start(body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    payload = _body(body)
    ports = payload.get("ports") or suite_load_ports()
    include_portal = bool(payload.get("include_portal", False))
    previous_ports = suite_load_ports()
    suite_stop_services(previous_ports, include_portal=False)
    if ports != previous_ports:
        suite_stop_services(ports, include_portal=False)
    ok, message = suite_start_services(ports, include_portal=include_portal, open_browser_flag=False)
    result = suite_status_payload(ports)
    result.update({"ok": ok, "message": f"Old simulator services closed. {message}"})
    return result


@app.post("/launcher/open-app")
def launcher_open_app(body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    payload = _body(body)
    ports = payload.get("ports") or suite_load_ports()
    suite_save_ports(ports)
    opened_app_mode = suite_open_app_window(f"http://localhost:{ports['portal_port']}")
    result = suite_status_payload(ports)
    result.update({
        "ok": True,
        "message": "Application window requested." if opened_app_mode else "Default browser opened because Edge/Chrome app mode was not found.",
    })
    return result


@app.post("/logs/clear")
def logs_clear() -> dict[str, Any]:
    suite_clear_log()
    return suite_logs_payload()


@app.post("/launcher/stop")
def launcher_stop(body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    payload = _body(body)
    ports = payload.get("ports") or suite_load_ports()
    include_portal = bool(payload.get("include_portal", False))
    if include_portal:
        helper_python = str(SUITE_VENV_PYW if SUITE_VENV_PYW.exists() else SUITE_VENV_PY)
        subprocess.Popen(
            [helper_python, str(ROOT / "stop_hidden.py")],
            cwd=str(ROOT),
            creationflags=CREATE_NO_WINDOW,
        )
        result = suite_status_payload(ports)
        result.update({"ok": True, "message": "Full stop requested. Portal may close."})
        return result
    ok, message = suite_stop_services(ports, include_portal=False)
    result = suite_status_payload(ports)
    result.update({"ok": ok, "message": message})
    return result


@app.post("/mssql/test")
def mssql_test(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return run_mssql("test", body)


@app.post("/mssql/write-current")
def mssql_write_current(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    rows = current_industrial_rows()
    if not rows:
        return {"ok": False, "error": "No current values. Configure and start replay first."}
    return run_mssql("write", body, rows)


@app.post("/mssql/list-databases")
def mssql_list_databases(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return run_mssql("list_databases", body)


@app.post("/mssql/list-tables")
def mssql_list_tables(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return run_mssql("list_tables", body)


@app.post("/connections/save")
def connections_save(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    write_store(CONNECTIONS_JSON, body)
    return {"ok": True, "connections": body}


@app.post("/api-mappings/save")
def api_mappings_save(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    mappings = read_store(MAPPINGS_JSON, [])
    mappings = [item for item in mappings if item.get("endpoint_id") != body.get("endpoint_id")]
    mappings.append(body)
    write_store(MAPPINGS_JSON, mappings)
    return {"ok": True, "mappings": mappings}


def main() -> None:
    import uvicorn

    print(f"Portal: http://127.0.0.1:{PORT}")
    print(f"Industrial simulator: http://127.0.0.1:{INDUSTRIAL_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
