from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suite_runtime import (
    CREATE_NO_WINDOW as SUITE_CREATE_NO_WINDOW,
    load_ports as suite_load_ports,
    save_ports as suite_save_ports,
    validate_ports as suite_validate_ports,
    start_services as suite_start_services,
    stop_services as suite_stop_services,
    status_payload as suite_status_payload,
    open_app_window as suite_open_app_window,
    VENV_PYW as SUITE_VENV_PYW,
    VENV_PY as SUITE_VENV_PY,
)


def env_port(name: str, default: int, fallback_name: str | None = None) -> int:
    values = [name]
    if fallback_name:
        values.append(fallback_name)
    for key in values:
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
API_STUDIO_PORT = env_port("API_STUDIO_PORT", 5050, "PORT")
OPCUA_PORT = env_port("OPCUA_PORT", 4840)
MQTT_BROKER_PORT = env_port("MQTT_BROKER_PORT", 1883, "MQTT_PORT")
ACM_PORT = env_port("ACM_PORT", 8765)
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
DATA_DIR = ROOT / "portal" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONNECTIONS_JSON = DATA_DIR / "connections.json"
MAPPINGS_JSON = DATA_DIR / "api_source_mappings.json"


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def json_response(handler: BaseHTTPRequestHandler, code: int, data: dict) -> None:
    raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def html_response(handler: BaseHTTPRequestHandler, html: str) -> None:
    raw = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length).decode("utf-8") if length else "{}"
    return json.loads(raw or "{}")


def read_store(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write_store(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_service(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return {"ok": True, "status": r.status}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def mssql_payload(cfg: dict, rows: list[dict] | None = None) -> dict:
    payload = dict(cfg or {})
    if rows is not None:
        payload["rows"] = rows
    return payload


def run_mssql(action: str, cfg: dict, rows: list[dict] | None = None) -> dict:
    payload = mssql_payload(cfg, rows)
    payload["action"] = action
    helper = ROOT / "portal" / "mssql_helper.ps1"
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as f:
        json.dump(payload, f)
        payload_path = f.name
    try:
        ps = "powershell.exe" if os.name == "nt" else "pwsh"
        cmd = [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper), payload_path]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=CREATE_NO_WINDOW)
        out = (completed.stdout or "").strip()
        err = (completed.stderr or "").strip()
        try:
            parsed = json.loads(out) if out else {}
        except Exception:
            parsed = {"raw": out}
        parsed["returncode"] = completed.returncode
        if err:
            parsed["stderr"] = err
        if completed.returncode != 0:
            parsed.setdefault("ok", False)
        return parsed
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            os.unlink(payload_path)
        except Exception:
            pass


def current_industrial_rows() -> list[dict]:
    url = f"http://127.0.0.1:{INDUSTRIAL_PORT}/api/replay/current-values"
    with urllib.request.urlopen(url, timeout=5) as r:
        data = json.loads(r.read().decode("utf-8"))
    rows = []
    for item in data.get("values", []):
        rows.append({
            "ts": item.get("last_updated") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "tag_name": item.get("tag_name") or item.get("node_id") or "tag",
            "value": str(item.get("value", "")),
            "unit": item.get("data_type", ""),
            "quality": "Good",
            "description": item.get("node_id", ""),
        })
    return rows

def page() -> str:
        template_path = ROOT / "portal" / "simulator_proto.html"
        template = template_path.read_text(encoding="utf-8")

        config = {
            "industrial_web_port": INDUSTRIAL_PORT,
            "api_studio_port": API_STUDIO_PORT,
            "portal_port": PORT,
            "opcua_port": OPCUA_PORT,
            "mqtt_port": MQTT_BROKER_PORT,
            "mqtt_host": "localhost",
            "acm_port": ACM_PORT,
            "lan_ip": local_ip(),
        }
        config_script = (
            "<script>"
            f"window.SIMULATOR_LAUNCHER_CONFIG = {json.dumps(config)};"
            "</script>"
        )
        template = template.replace("<script>", config_script + "\n<script>", 1)

        replacements = {
            'href="http://127.0.0.1:5050"': f'href="http://127.0.0.1:{API_STUDIO_PORT}"',
            'src="http://127.0.0.1:5050"': f'src="http://127.0.0.1:{API_STUDIO_PORT}"',
            'id="lpApi" value="5050"': f'id="lpApi" value="{API_STUDIO_PORT}"',
            'id="lpPortal" value="8001"': f'id="lpPortal" value="{PORT}"',
            'id="lpIndustrial" value="8000"': f'id="lpIndustrial" value="{INDUSTRIAL_PORT}"',
            'id="lpOpcua" value="4840"': f'id="lpOpcua" value="{OPCUA_PORT}"',
            'id="lpMqtt" value="1883"': f'id="lpMqtt" value="{MQTT_BROKER_PORT}"',
            'id="lpAcm" value="8765"': f'id="lpAcm" value="{ACM_PORT}"',
            'id="mqttPort" type="number" value="1883"': f'id="mqttPort" type="number" value="{MQTT_BROKER_PORT}"',
            'id="opcuaEndpoint" value="opc.tcp://localhost:4840/simulator"': f'id="opcuaEndpoint" value="opc.tcp://localhost:{OPCUA_PORT}/simulator"',
        }
        for old, new in replacements.items():
            template = template.replace(old, new)

        boot_patch = r"""
const __ipsOrigRefreshStatus = refreshStatus;
const __ipsOrigLoadGenerators = loadGenerators;
const __ipsOrigRefreshFiles = refreshFiles;
const __ipsOrigLoadApiEndpoints = loadApiEndpoints;
const __ipsOrigRefreshConfigs = refreshConfigs;
const __ipsOrigRefreshCurrentValues = refreshCurrentValues;
let __ipsIndustrialReady = false;
let __ipsApiReady = false;
let __ipsIndustrialLoaded = false;
let __ipsApiLoaded = false;
let __ipsConfigLoaded = false;

function __ipsSetText(id, text) {
  const el = $(id);
  if (el) el.textContent = text;
}

function __ipsSetHtml(id, html) {
  const el = $(id);
  if (el) el.innerHTML = html;
}

function __ipsApplyIndustrialWaiting(text) {
  __ipsSetText('genSummary', text);
  __ipsSetHtml('genPreview', '<div class="hint" style="padding:8px">Waiting for Industrial backend.</div>');
  __ipsSetHtml('filesTable', '<div class="hint" style="padding:8px">Waiting for Industrial backend. Bundled sample files will appear automatically.</div>');
  __ipsSetText('filePreviewMeta', 'Waiting for Industrial backend.');
  __ipsSetHtml('filePreview', '<div class="hint" style="padding:8px">Preview will load automatically when Industrial is ready.</div>');
  __ipsSetHtml('fileMetaKv', '');
  __ipsSetHtml('mappingTable', '<div class="hint" style="padding:8px">No file loaded. Use Load Manual in Files when Industrial is ready.</div>');
  __ipsSetHtml('configsTable', '<div class="hint" style="padding:8px">Waiting for Industrial backend configs.</div>');
  __ipsSetHtml('currentValues', '<div class="hint" style="padding:8px">Waiting for Industrial backend current values.</div>');
  __ipsSetText('rawStatus', JSON.stringify({ state: text }, null, 2));
}

function __ipsApplyApiWaiting(text) {
  __ipsSetText('apiResult', text);
  __ipsSetHtml('mappingsTable', '<div class="hint" style="padding:8px">Waiting for API Studio backend.</div>');
  const apiEndpoint = $('apiEndpoint');
  if (apiEndpoint) apiEndpoint.innerHTML = '';
}

loadGenerators = async function() {
  if (!__ipsIndustrialReady) {
    __ipsApplyIndustrialWaiting('Industrial backend starting. Generator catalog will load automatically.');
    return;
  }
  return __ipsOrigLoadGenerators();
};

refreshFiles = async function() {
  if (!__ipsIndustrialReady) {
    __ipsApplyIndustrialWaiting('Industrial backend starting. Built-in files will appear automatically.');
    return;
  }
  return __ipsOrigRefreshFiles();
};

refreshConfigs = async function() {
  if (!__ipsIndustrialReady) {
    __ipsSetHtml('configsTable', '<div class="hint" style="padding:8px">Waiting for Industrial backend configs.</div>');
    return;
  }
  return __ipsOrigRefreshConfigs();
};

refreshCurrentValues = async function() {
  if (!__ipsIndustrialReady) return;
  return __ipsOrigRefreshCurrentValues();
};

loadApiEndpoints = async function() {
  if (!__ipsApiReady) {
    __ipsApplyApiWaiting('API Studio backend starting. Endpoint catalog will load automatically.');
    return;
  }
  return __ipsOrigLoadApiEndpoints();
};

refreshStatus = async function() {
  const suiteResp = await fetch('/suite/status');
  let suite = {};
  try { suite = await suiteResp.json(); } catch (_) {}
  if (!suiteResp.ok) throw new Error('Could not load suite status.');

  const industrialOk = !!(suite.industrial && suite.industrial.ok);
  const apiOk = !!(suite.api_studio && suite.api_studio.ok);
  const acmOk = !!(suite.acm && suite.acm.ok);
  const acmPort = window.SIMULATOR_LAUNCHER_CONFIG && window.SIMULATOR_LAUNCHER_CONFIG.acm_port || 8765;
  const scAcm = $('sc-acm');
  if (scAcm) {
    scAcm.querySelector('.val').textContent = acmOk ? 'online' : 'offline';
    scAcm.className = 'sc-item' + (acmOk ? ' ok' : ' warn');
  }

  if (!industrialOk) {
    __ipsIndustrialReady = false;
    __ipsIndustrialLoaded = false;
    __ipsConfigLoaded = false;
    sc('sc-backend', 'starting', 'warn');
    sc('sc-state', 'waiting', 'warn');
    sc('sc-opcua', 'waiting');
    sc('sc-mqtt', 'waiting');
    sc('sc-hz', '-');
    sc('sc-cursor', '0/0');
    sc('sc-tags', '0');
    const ep = $('sc-endpoint');
    if (ep) ep.querySelector('.val').textContent = `http://127.0.0.1:${CFG.industrial_web_port || 8000}`;
    __ipsApplyIndustrialWaiting('Industrial backend starting. Built-in files will appear automatically.');
  } else {
    __ipsIndustrialReady = true;
    if (!__ipsIndustrialLoaded) {
      await __ipsOrigLoadGenerators();
      await __ipsOrigRefreshFiles();
      __ipsIndustrialLoaded = true;
    }
    if (!__ipsConfigLoaded) {
      await __ipsOrigRefreshConfigs();
      __ipsConfigLoaded = true;
    }
    await __ipsOrigRefreshStatus();
  }

  if (!apiOk) {
    __ipsApiReady = false;
    __ipsApiLoaded = false;
    __ipsApplyApiWaiting('API Studio backend starting.');
  } else {
    __ipsApiReady = true;
    if (!__ipsApiLoaded) {
      await __ipsOrigLoadApiEndpoints();
      __ipsApiLoaded = true;
    }
  }
};

async function init() {
  applyLauncherDefaults();
  renderTagPlan();
  renderMappingTable([]);
  __ipsApplyIndustrialWaiting('Industrial backend starting. Built-in files will appear automatically.');
  __ipsApplyApiWaiting('API Studio backend starting.');
  await safeStep(loadLaunchStatus, 'Launcher');
  await safeStep(refreshStatus, 'Status');
  setInterval(() => refreshStatus().catch(() => {}), 4000);
  setInterval(() => refreshCurrentValues().catch(() => {}), 1000);
  setInterval(() => loadLaunchStatus().catch(() => {}), 5000);
}

init().catch(e => msg(e.message,'error'));
"""
        template = template.replace(
            "init().catch(e => msg(e.message,'error'));",
            boot_patch,
            1,
        )
        return template

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return html_response(self, page())
        if path == "/suite/status":
            return json_response(self, 200, {
                "portal": {"ok": True, "port": PORT},
                "industrial": get_service(f"http://127.0.0.1:{INDUSTRIAL_PORT}/api/health"),
                "api_studio": get_service(f"http://127.0.0.1:{API_STUDIO_PORT}/api/studio/health"),
                "acm": get_service(f"http://127.0.0.1:{ACM_PORT}/health"),
            })
        if path == "/launcher/config":
            return json_response(self, 200, suite_status_payload(suite_load_ports()))
        if path == "/connections":
            return json_response(self, 200, {"connections": read_store(CONNECTIONS_JSON, {})})
        if path == "/api-mappings":
            return json_response(self, 200, {"mappings": read_store(MAPPINGS_JSON, [])})
        return json_response(self, 404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = read_json(self)
            if path == "/launcher/save":
                ports = body.get("ports") or suite_load_ports()
                errors = suite_validate_ports(ports)
                if errors:
                    payload = suite_status_payload(suite_load_ports())
                    payload.update({"ok": False, "message": "; ".join(errors)})
                    return json_response(self, 200, payload)
                suite_save_ports(ports)
                payload = suite_status_payload(ports)
                payload.update({"ok": True, "message": "Ports saved."})
                return json_response(self, 200, payload)
            if path == "/launcher/start":
                ports = body.get("ports") or suite_load_ports()
                include_portal = bool(body.get("include_portal", False))
                ok, msg = suite_start_services(ports, include_portal=include_portal, open_browser_flag=False)
                payload = suite_status_payload(ports)
                payload.update({"ok": ok, "message": msg})
                return json_response(self, 200, payload)
            if path == "/launcher/open-app":
                ports = body.get("ports") or suite_load_ports()
                suite_save_ports(ports)
                ok = suite_open_app_window(f"http://localhost:{ports['portal_port']}")
                payload = suite_status_payload(ports)
                payload.update({"ok": True, "message": "Application window requested." if ok else "Default browser opened because Edge/Chrome app mode was not found."})
                return json_response(self, 200, payload)
            if path == "/launcher/stop":
                ports = body.get("ports") or suite_load_ports()
                include_portal = bool(body.get("include_portal", False))
                if include_portal:
                    helper_py = str(SUITE_VENV_PYW if SUITE_VENV_PYW.exists() else SUITE_VENV_PY)
                    subprocess.Popen([helper_py, str(ROOT / "stop_hidden.py")], cwd=str(ROOT), creationflags=CREATE_NO_WINDOW)
                    payload = suite_status_payload(ports)
                    payload.update({"ok": True, "message": "Full stop requested. Portal may close."})
                    return json_response(self, 200, payload)
                ok, msg = suite_stop_services(ports, include_portal=False)
                payload = suite_status_payload(ports)
                payload.update({"ok": ok, "message": msg})
                return json_response(self, 200, payload)
            if path == "/mssql/test":
                return json_response(self, 200, run_mssql("test", body))
            if path == "/mssql/write-current":
                rows = current_industrial_rows()
                if not rows:
                    return json_response(self, 200, {"ok": False, "error": "No current values. Configure and start replay first."})
                return json_response(self, 200, run_mssql("write", body, rows))
            if path == "/mssql/list-databases":
                return json_response(self, 200, run_mssql("list_databases", body))
            if path == "/mssql/list-tables":
                return json_response(self, 200, run_mssql("list_tables", body))
            if path == "/connections/save":
                write_store(CONNECTIONS_JSON, body)
                return json_response(self, 200, {"ok": True, "connections": body})
            if path == "/api-mappings/save":
                mappings = read_store(MAPPINGS_JSON, [])
                mappings = [m for m in mappings if m.get("endpoint_id") != body.get("endpoint_id")]
                mappings.append(body)
                write_store(MAPPINGS_JSON, mappings)
                return json_response(self, 200, {"ok": True, "mappings": mappings})
            return json_response(self, 404, {"ok": False, "error": "Not found"})
        except Exception as exc:
            return json_response(self, 500, {"ok": False, "error": str(exc)})


def main() -> None:
    print(f"Portal: http://127.0.0.1:{PORT}")
    print(f"Industrial simulator: http://127.0.0.1:{INDUSTRIAL_PORT}")
    print(f"API Studio: http://127.0.0.1:{API_STUDIO_PORT}")
    print(f"ACM: http://127.0.0.1:{ACM_PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
