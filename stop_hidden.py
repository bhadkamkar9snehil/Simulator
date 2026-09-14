from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
ROOT = Path(__file__).resolve().parent
PIDS_JSON = ROOT / "runtime_pids.json"
PORTS_JSON = ROOT / "simulator_ports.json"
DEFAULT_PORTS = {
    "industrial_web_port": "8000",
    "portal_port": "8001",
    "opcua_port": "4840",
    "mqtt_broker_port": "1883",
}


def run(cmd: list[str]) -> None:
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=15,
        )
    except Exception:
        pass


def stop_pid(pid: str | int) -> None:
    if os.name == "nt":
        run(["taskkill.exe", "/PID", str(pid), "/F"])


def load_ports() -> dict[str, str]:
    ports = dict(DEFAULT_PORTS)
    if not PORTS_JSON.exists():
        return ports
    try:
        saved = json.loads(PORTS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return ports
    for key in ports:
        value = str(saved.get(key, "")).strip()
        if value:
            ports[key] = value
    return ports


time.sleep(1.0)

if PIDS_JSON.exists():
    try:
        for pid in json.loads(PIDS_JSON.read_text(encoding="utf-8")).values():
            stop_pid(pid)
    except Exception:
        pass
    try:
        PIDS_JSON.unlink()
    except Exception:
        pass

if os.name == "nt":
    targets = set(load_ports().values())
    try:
        out = subprocess.check_output(
            ["netstat.exe", "-ano"],
            text=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=15,
        )
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 5 or not parts[0].upper().startswith("TCP") or parts[-2].upper() != "LISTENING":
                continue
            local = parts[1]
            if ":" in local and local.rsplit(":", 1)[-1] in targets:
                stop_pid(parts[-1])
    except Exception:
        pass
