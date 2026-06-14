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
DEFAULT_PORTS = {"industrial_web_port":"8000","api_studio_port":"5050","portal_port":"8001","opcua_port":"4840","mqtt_broker_port":"1883"}

def run(cmd):
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=15)
    except Exception:
        pass

def stop_pid(pid):
    if os.name == "nt":
        run(["taskkill.exe", "/PID", str(pid), "/F"])

time.sleep(1.0)

def load_ports():
    p = dict(DEFAULT_PORTS)
    if PORTS_JSON.exists():
        try:
            p.update({k:str(v) for k,v in json.loads(PORTS_JSON.read_text(encoding="utf-8")).items() if k in p})
        except Exception:
            pass
    return p

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
        out = subprocess.check_output(["netstat.exe", "-ano"], text=True, creationflags=CREATE_NO_WINDOW, timeout=15)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper().startswith("TCP") and parts[-2].upper() == "LISTENING":
                local = parts[1]
                pid = parts[-1]
                if ":" in local and local.rsplit(":", 1)[-1] in targets:
                    stop_pid(pid)
    except Exception:
        pass
