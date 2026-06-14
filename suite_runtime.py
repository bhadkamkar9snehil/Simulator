from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUNDLED_RUNTIME_DIR = ROOT / "runtime" / "python"
BUNDLED_RUNTIME_PY = BUNDLED_RUNTIME_DIR / "python.exe"
BUNDLED_RUNTIME_PYW = BUNDLED_RUNTIME_DIR / "pythonw.exe"
RUNTIME_MANIFEST = ROOT / "runtime" / "runtime_manifest.json"
VENV_DIR = ROOT / ".venv"
VENV_PY = VENV_DIR / "Scripts" / "python.exe"
VENV_PYW = VENV_DIR / "Scripts" / "pythonw.exe"
PORTS_JSON = ROOT / "simulator_ports.json"
PORTS_BAT = ROOT / "simulator_ports.bat"
PIDS_JSON = ROOT / "runtime_pids.json"
LOG_FILE = ROOT / "launcher.log"
WHEELS_DIR = ROOT / "wheels"
WHEELHOUSE_MANIFEST = WHEELS_DIR / "wheelhouse_manifest.json"
WHEELHOUSE_CONSTRAINTS = WHEELS_DIR / "wheelhouse_constraints.txt"
REQUIREMENTS_FILE = ROOT / "requirements.txt"
BOOTSTRAP_STATE = VENV_DIR / ".bootstrap_state.json"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
ACM_DIR = ROOT.parent / "ACM"
DEFAULT_PORTS = {
    "industrial_web_port": "8000",
    "api_studio_port": "5050",
    "portal_port": "8001",
    "opcua_port": "4840",
    "mqtt_broker_port": "1883",
    "acm_port": "8765",
}
ENV_PORT_MAP = {
    "industrial_web_port": "INDUSTRIAL_WEB_PORT",
    "api_studio_port": "API_STUDIO_PORT",
    "portal_port": "PORTAL_PORT",
    "opcua_port": "OPCUA_PORT",
    "mqtt_broker_port": "MQTT_BROKER_PORT",
    "acm_port": "ACM_PORT",
}

processes: dict[str, subprocess.Popen] = {}


def log_line(text: str) -> None:
    line = f"{time.strftime('%H:%M:%S')}  {text}"
    try:
        old = LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.exists() else ""
        LOG_FILE.write_text(old + line + "\n", encoding="utf-8")
    except Exception:
        pass


def tail_log(lines: int = 120) -> str:
    try:
        data = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(data[-lines:])
    except Exception:
        return ""


def run_hidden(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    wait: bool = False,
    timeout: int | None = None,
):
    kwargs = {
        "cwd": str(cwd or ROOT),
        "env": env or os.environ.copy(),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "creationflags": CREATE_NO_WINDOW,
    }
    if wait:
        completed = subprocess.run(cmd, timeout=timeout, **kwargs)
        return completed.returncode, completed.stdout or ""
    return subprocess.Popen(cmd, **kwargs)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_error_line(output: str) -> str:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("ERROR:"):
            return stripped
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return "Unknown bootstrap error."


def load_ports() -> dict[str, str]:
    ports = dict(DEFAULT_PORTS)
    if PORTS_JSON.exists():
        try:
            data = json.loads(PORTS_JSON.read_text(encoding="utf-8"))
            for key in ports:
                if str(data.get(key, "")).strip():
                    ports[key] = str(data[key]).strip()
        except Exception:
            pass
    elif PORTS_BAT.exists():
        try:
            env_names = {value: key for key, value in ENV_PORT_MAP.items()}
            for raw_line in PORTS_BAT.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line.lower().startswith("set "):
                    continue
                payload = line[4:].strip().strip('"')
                if "=" not in payload:
                    continue
                env_name, value = payload.split("=", 1)
                key = env_names.get(env_name.strip())
                if key and value.strip():
                    ports[key] = value.strip()
        except Exception:
            pass
    return ports


def ports_from_env(env: dict[str, str] | None = None) -> dict[str, str]:
    source = env or os.environ
    ports = dict(DEFAULT_PORTS)
    for key, env_name in ENV_PORT_MAP.items():
        value = str(source.get(env_name, "")).strip()
        if value:
            ports[key] = value
    return ports


def save_ports(ports: dict[str, str]) -> None:
    PORTS_JSON.write_text(json.dumps(ports, indent=2), encoding="utf-8")
    lines = ["@echo off"]
    lines.append(f'set "INDUSTRIAL_WEB_PORT={ports["industrial_web_port"]}"')
    lines.append(f'set "API_STUDIO_PORT={ports["api_studio_port"]}"')
    lines.append(f'set "PORTAL_PORT={ports["portal_port"]}"')
    lines.append(f'set "OPCUA_PORT={ports["opcua_port"]}"')
    lines.append(f'set "MQTT_BROKER_PORT={ports["mqtt_broker_port"]}"')
    lines.append(f'set "ACM_PORT={ports.get("acm_port", DEFAULT_PORTS["acm_port"])}"')
    PORTS_BAT.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def validate_ports(ports: dict[str, str]) -> list[str]:
    errors = []
    seen = set()
    for label, value in ports.items():
        try:
            port = int(value)
            if port < 1 or port > 65535:
                errors.append(f"{label} must be 1-65535")
            if port in seen:
                errors.append(f"Port {port} is used more than once")
            seen.add(port)
        except ValueError:
            errors.append(f"{label} must be a number")
    return errors


def is_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def port_conflicts(ports: dict[str, str]) -> list[str]:
    conflicts = []
    for label, value in ports.items():
        try:
            port = int(value)
        except ValueError:
            continue
        if is_port_listening(port):
            conflicts.append(f"{label}: port {port} is already listening")
    return conflicts


@lru_cache(maxsize=1)
def bundled_runtime_info() -> dict | None:
    if not BUNDLED_RUNTIME_PY.exists():
        return None
    code, out = run_hidden(
        [
            str(BUNDLED_RUNTIME_PY),
            "-c",
            (
                "import json, platform, sys; "
                "print(json.dumps({"
                "'version': sys.version.split()[0], "
                "'major': sys.version_info[0], "
                "'minor': sys.version_info[1], "
                "'micro': sys.version_info[2], "
                "'platform': 'win_amd64' if sys.maxsize > 2**32 else 'win32', "
                "'python_tag': f'cp{sys.version_info[0]}{sys.version_info[1]}'}))"
            ),
        ],
        wait=True,
        timeout=20,
    )
    if code != 0:
        return None
    try:
        return json.loads(out.strip())
    except Exception:
        return None


def load_runtime_manifest() -> dict:
    if not RUNTIME_MANIFEST.exists():
        return {}
    try:
        return json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def verify_bundled_runtime() -> tuple[bool, str]:
    if not BUNDLED_RUNTIME_PY.exists():
        return False, f"Bundled Python runtime missing: {BUNDLED_RUNTIME_PY}"
    if not BUNDLED_RUNTIME_PYW.exists():
        return False, f"Bundled Python runtime is incomplete: {BUNDLED_RUNTIME_PYW}"

    info = bundled_runtime_info()
    if info is None:
        return False, f"Bundled Python runtime is corrupt or cannot start: {BUNDLED_RUNTIME_PY}"

    manifest = load_runtime_manifest()
    expected_version = str(manifest.get("python_version", "")).strip()
    expected_platform = str(manifest.get("platform", "")).strip()
    expected_tag = str(manifest.get("python_tag", "")).strip()

    if expected_version and info["version"] != expected_version:
        return (
            False,
            f"Bundled runtime version mismatch. Expected {expected_version}, found {info['version']}.",
        )
    if expected_platform and info["platform"] != expected_platform:
        return (
            False,
            f"Bundled runtime platform mismatch. Expected {expected_platform}, found {info['platform']}.",
        )
    if expected_tag and info["python_tag"] != expected_tag:
        return (
            False,
            f"Bundled runtime tag mismatch. Expected {expected_tag}, found {info['python_tag']}.",
        )

    code, out = run_hidden(
        [str(BUNDLED_RUNTIME_PY), "-c", "import ensurepip, venv; print('runtime_ok')"],
        wait=True,
        timeout=20,
    )
    if code != 0:
        return False, extract_error_line(out)

    return True, f"Using bundled runtime {BUNDLED_RUNTIME_PY} ({info['version']})."


def load_wheelhouse_manifest() -> dict:
    if not WHEELHOUSE_MANIFEST.exists():
        return {}
    try:
        return json.loads(WHEELHOUSE_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def wheel_filename_parts(name: str) -> tuple[str, str, str] | None:
    if not name.endswith(".whl"):
        return None
    stem = name[:-4]
    parts = stem.rsplit("-", 3)
    if len(parts) != 4:
        return None
    return parts[1], parts[2], parts[3]


def wheel_is_compatible(name: str, python_tag: str, platform_tag: str) -> bool:
    parts = wheel_filename_parts(name)
    if parts is None:
        return False
    py_tags, abi_tags, plat_tags = parts
    py_values = py_tags.split(".")
    abi_values = abi_tags.split(".")
    plat_values = plat_tags.split(".")
    if "any" not in plat_values and platform_tag not in plat_values:
        return False

    current_minor = int(python_tag[3:])
    for py_tag in py_values:
        for abi_tag in abi_values:
            if py_tag in {"py3", "py2.py3"} and abi_tag == "none":
                return True
            if py_tag == python_tag and abi_tag in {python_tag, "abi3", "none"}:
                return True
            if py_tag.startswith("cp3") and abi_tag == "abi3":
                try:
                    wheel_minor = int(py_tag[3:])
                except ValueError:
                    continue
                if wheel_minor <= current_minor:
                    return True
    return False


def verify_wheelhouse(info: dict) -> tuple[bool, str]:
    if not WHEELHOUSE_MANIFEST.exists():
        return False, f"Wheelhouse manifest missing: {WHEELHOUSE_MANIFEST}"
    if not WHEELHOUSE_CONSTRAINTS.exists():
        return False, f"Wheelhouse constraints missing: {WHEELHOUSE_CONSTRAINTS}"

    manifest = load_wheelhouse_manifest()
    runtime = manifest.get("runtime") or {}
    expected_tag = str(runtime.get("python_tag", "")).strip() or info["python_tag"]
    expected_platform = str(runtime.get("platform", "")).strip() or info["platform"]
    manifest_version = str(runtime.get("python_version", "")).strip()

    if manifest_version and manifest_version != info["version"]:
        return (
            False,
            f"Wheelhouse targets Python {manifest_version}, but bundled runtime is {info['version']}.",
        )

    files = manifest.get("files") or []
    if not files:
        return False, f"Wheelhouse manifest is empty: {WHEELHOUSE_MANIFEST}"

    for entry in files:
        wheel_name = str(entry.get("name", "")).strip()
        if not wheel_name:
            return False, f"Wheelhouse manifest contains an invalid entry: {entry!r}"
        wheel_path = WHEELS_DIR / wheel_name
        if not wheel_path.exists():
            return False, f"Wheelhouse invalid: missing {wheel_path}"
        if not wheel_is_compatible(wheel_name, expected_tag, expected_platform):
            return (
                False,
                f"Wheelhouse invalid: {wheel_name} is not compatible with {expected_tag}/{expected_platform}.",
            )
        expected_size = int(entry.get("size", -1))
        if expected_size >= 0 and wheel_path.stat().st_size != expected_size:
            return False, f"Wheelhouse invalid: {wheel_name} size mismatch."
        expected_sha = str(entry.get("sha256", "")).strip().lower()
        if expected_sha and sha256_file(wheel_path).lower() != expected_sha:
            return False, f"Wheelhouse invalid: {wheel_name} hash mismatch."

    return True, f"Wheelhouse verified for {expected_tag}/{expected_platform}."


def current_venv_home() -> str:
    cfg = VENV_DIR / "pyvenv.cfg"
    if not cfg.exists():
        return ""
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("home = "):
                return line.split("=", 1)[1].strip()
    except Exception:
        return ""
    return ""


def load_bootstrap_state() -> dict:
    if not BOOTSTRAP_STATE.exists():
        return {}
    try:
        return json.loads(BOOTSTRAP_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def expected_bootstrap_state(info: dict) -> dict:
    requirements_sha = sha256_file(REQUIREMENTS_FILE)
    manifest_sha = sha256_file(WHEELHOUSE_MANIFEST)
    constraints_sha = sha256_file(WHEELHOUSE_CONSTRAINTS)
    payload = {
        "runtime_version": info["version"],
        "runtime_python_tag": info["python_tag"],
        "runtime_platform": info["platform"],
        "runtime_path": str(BUNDLED_RUNTIME_PY),
        "requirements_sha256": requirements_sha,
        "wheelhouse_manifest_sha256": manifest_sha,
        "wheelhouse_constraints_sha256": constraints_sha,
    }
    joined = "|".join(str(payload[key]) for key in sorted(payload))
    payload["fingerprint"] = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return payload


def bootstrap_mismatch_reason(expected_state: dict) -> str:
    if not VENV_PY.exists():
        return "Virtual environment missing."

    current_state = load_bootstrap_state()
    if current_state.get("fingerprint") != expected_state["fingerprint"]:
        return "Bundled runtime, requirements, or wheelhouse changed."

    venv_home = current_venv_home()
    if not venv_home:
        return "Virtual environment metadata missing."

    expected_home = str(BUNDLED_RUNTIME_DIR.resolve()).lower()
    actual_home = str(Path(venv_home).resolve()).lower()
    if actual_home != expected_home:
        return f"Virtual environment points at {venv_home} instead of {BUNDLED_RUNTIME_DIR}."

    return ""


def remove_existing_venv() -> None:
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR, ignore_errors=False)


def write_bootstrap_state(expected_state: dict) -> None:
    BOOTSTRAP_STATE.write_text(json.dumps(expected_state, indent=2) + "\n", encoding="utf-8")


def create_virtualenv() -> tuple[bool, str]:
    log_line(f"Creating local environment from bundled runtime: {BUNDLED_RUNTIME_PY}")
    code, out = run_hidden(
        [str(BUNDLED_RUNTIME_PY), "-m", "venv", str(VENV_DIR)],
        wait=True,
        timeout=300,
    )
    if out.strip():
        log_line(out.strip()[-2000:])
    if code != 0 or not VENV_PY.exists():
        return False, extract_error_line(out)
    return True, "Virtual environment created."


def install_requirements() -> tuple[bool, str]:
    log_line(f"Installing required packages from bundled offline wheels: {WHEELS_DIR}")
    code, out = run_hidden(
        [
            str(VENV_PY),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(WHEELS_DIR),
            "-c",
            str(WHEELHOUSE_CONSTRAINTS),
            "-r",
            str(REQUIREMENTS_FILE),
        ],
        wait=True,
        timeout=900,
    )
    if out.strip():
        log_line(out.strip()[-5000:])
    if code != 0:
        return False, extract_error_line(out)
    return True, "Dependencies installed successfully."


def setup_environment() -> tuple[bool, str]:
    runtime_ok, runtime_msg = verify_bundled_runtime()
    log_line(runtime_msg)
    if not runtime_ok:
        return False, runtime_msg

    info = bundled_runtime_info()
    assert info is not None
    wheelhouse_ok, wheelhouse_msg = verify_wheelhouse(info)
    log_line(f"Wheelhouse manifest: {WHEELHOUSE_MANIFEST}")
    log_line(wheelhouse_msg)
    if not wheelhouse_ok:
        return False, wheelhouse_msg

    expected_state = expected_bootstrap_state(info)
    mismatch_reason = bootstrap_mismatch_reason(expected_state)
    if mismatch_reason:
        log_line(f"Refreshing local environment: {mismatch_reason}")
        if VENV_DIR.exists():
            remove_existing_venv()
        ok, msg = create_virtualenv()
        if not ok:
            log_line(f"ERROR: {msg}")
            return False, msg
        ok, msg = install_requirements()
        if not ok:
            log_line(f"ERROR: {msg}")
            return False, msg
        write_bootstrap_state(expected_state)
        log_line("Bootstrap state written.")
        return True, "Environment ready."

    return True, "Environment ready."


def env_for(ports: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env["INDUSTRIAL_WEB_PORT"] = ports["industrial_web_port"]
    env["INDUSTRIAL_PORT"] = ports["industrial_web_port"]
    env["API_STUDIO_PORT"] = ports["api_studio_port"]
    env["PORT"] = ports["api_studio_port"]
    env["PORTAL_PORT"] = ports["portal_port"]
    env["OPCUA_PORT"] = ports["opcua_port"]
    env["MQTT_BROKER_PORT"] = ports["mqtt_broker_port"]
    env["MQTT_PORT"] = ports["mqtt_broker_port"]
    env["PYTHONUNBUFFERED"] = "1"
    return env


def save_pids() -> None:
    data = {name: proc.pid for name, proc in processes.items() if proc and proc.poll() is None}
    PIDS_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")


def reader_thread(name: str, proc: subprocess.Popen) -> None:
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            text = line.strip()
            if text:
                log_line(f"[{name}] {text}")
    except Exception as exc:
        log_line(f"[{name}] reader stopped: {exc}")


def start_service(name: str, cmd: list[str], cwd: Path, env: dict[str, str]) -> bool:
    existing = processes.get(name)
    if existing and existing.poll() is None:
        log_line(f"{name} is already running.")
        return True
    log_line(f"Starting {name}...")
    try:
        proc = run_hidden(cmd, cwd=cwd, env=env, wait=False)
        processes[name] = proc
        threading.Thread(target=reader_thread, args=(name, proc), daemon=True).start()
        save_pids()
        return True
    except Exception as exc:
        log_line(f"ERROR starting {name}: {exc}")
        return False


def open_app_window(url: str) -> bool:
    candidates = []
    if os.name == "nt":
        for base in [
            os.environ.get("LOCALAPPDATA"),
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
        ]:
            if not base:
                continue
            candidates.extend(
                [
                    Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                    Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
                ]
            )
        for exe_name in ["msedge.exe", "chrome.exe"]:
            try:
                code, out = run_hidden(["where.exe", exe_name], wait=True, timeout=8)
                if code == 0:
                    for line in out.splitlines():
                        if line.strip():
                            candidates.append(Path(line.strip()))
            except Exception:
                pass
    for exe in candidates:
        try:
            if exe.exists():
                profile = ROOT / "app_window_profile"
                profile.mkdir(exist_ok=True)
                subprocess.Popen(
                    [str(exe), f"--app={url}", "--new-window", f"--user-data-dir={profile}"],
                    cwd=str(ROOT),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                )
                log_line(f"Opened application window: {url}")
                return True
        except Exception as exc:
            log_line(f"Could not open app window with {exe}: {exc}")
    try:
        webbrowser.open(url)
        log_line(f"Opened portal in default browser: {url}")
        return False
    except Exception as exc:
        log_line(f"Could not open browser: {exc}")
        return False


def start_services(
    ports: dict[str, str],
    include_portal: bool = True,
    open_browser_flag: bool = False,
) -> tuple[bool, str]:
    errors = validate_ports(ports)
    if errors:
        return False, "; ".join(errors)
    save_ports(ports)
    ok, msg = setup_environment()
    if not ok:
        return False, msg
    env = env_for(ports)
    log_line("Writing frontend launcher configuration...")
    code, out = run_hidden(
        [str(VENV_PY), "write_launcher_config.py"],
        cwd=ROOT / "industrial_simulator",
        env=env,
        wait=True,
        timeout=60,
    )
    if out.strip():
        log_line(out.strip()[-1500:])
    if code != 0:
        return False, "Could not write launcher config."

    service_py = str(VENV_PY)
    ok1 = start_service(
        "Industrial",
        [service_py, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", ports["industrial_web_port"]],
        ROOT / "industrial_simulator",
        env,
    )
    ok2 = start_service("API Studio", [service_py, "app.py"], ROOT / "api_studio", env)
    ok3 = True
    if include_portal:
        ok3 = start_service("Portal", [service_py, "portal/portal_app.py"], ROOT, env)
    # ACM is optional: launch only when the sibling repo exists.
    if ACM_DIR.exists() and (ACM_DIR / "scripts" / "acm_service.py").exists():
        acm_env = dict(env)
        acm_env["ACM_PORT"] = str(ports.get("acm_port", DEFAULT_PORTS["acm_port"]))
        start_service(
            "ACM",
            [service_py, "scripts/acm_service.py", "--host", "0.0.0.0",
             "--port", ports.get("acm_port", DEFAULT_PORTS["acm_port"])],
            ACM_DIR,
            acm_env,
        )
    time.sleep(1.5)
    if open_browser_flag:
        open_app_window(f"http://localhost:{ports['portal_port']}")
    return bool(ok1 and ok2 and ok3), "Services started."


def terminate_process(proc: subprocess.Popen) -> None:
    if not proc or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=4)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def kill_pid(pid: str) -> None:
    if os.name != "nt":
        return
    try:
        run_hidden(["taskkill.exe", "/PID", str(pid), "/F"], wait=True, timeout=15)
    except Exception:
        pass


def stop_by_saved_pids(include_portal: bool = True) -> None:
    if not PIDS_JSON.exists():
        return
    try:
        data = json.loads(PIDS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return
    for name, pid in data.items():
        if not include_portal and name.lower() == "portal":
            continue
        kill_pid(str(pid))
    try:
        if include_portal:
            PIDS_JSON.unlink()
        else:
            data = {k: v for k, v in data.items() if k.lower() == "portal"}
            PIDS_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def stop_by_ports(ports: dict[str, str], include_portal: bool = True) -> None:
    if os.name != "nt":
        return
    target_keys = ["industrial_web_port", "api_studio_port", "opcua_port", "mqtt_broker_port", "acm_port"]
    if include_portal:
        target_keys.append("portal_port")
    targets = {str(ports[key]) for key in target_keys if key in ports}
    try:
        code, out = run_hidden(["netstat.exe", "-ano"], wait=True, timeout=20)
        if code != 0:
            return
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper().startswith("TCP") and parts[-2].upper() == "LISTENING":
                local = parts[1]
                pid = parts[-1]
                if ":" in local and local.rsplit(":", 1)[-1] in targets:
                    log_line(f"Stopping PID {pid} on {local}")
                    kill_pid(pid)
    except Exception:
        pass


def stop_services(ports: dict[str, str], include_portal: bool = True) -> tuple[bool, str]:
    log_line("Stopping services...")
    for name, proc in list(processes.items()):
        if not include_portal and name.lower() == "portal":
            continue
        terminate_process(proc)
        try:
            del processes[name]
        except Exception:
            pass
    stop_by_saved_pids(include_portal=include_portal)
    stop_by_ports(ports, include_portal=include_portal)
    log_line("Stop request complete.")
    return True, "Stop request sent."


def urls_for(ports: dict[str, str]) -> dict[str, str]:
    return {
        "portal": f"http://localhost:{ports['portal_port']}",
        "industrial": f"http://localhost:{ports['industrial_web_port']}",
        "api_studio": f"http://localhost:{ports['api_studio_port']}",
        "opcua": f"opc.tcp://localhost:{ports['opcua_port']}/simulator",
        "mqtt": f"localhost:{ports['mqtt_broker_port']}",
        "acm": f"http://localhost:{ports.get('acm_port', DEFAULT_PORTS['acm_port'])}",
    }


def status_payload(ports: dict[str, str]) -> dict:
    flags = {}
    for label, key in [
        ("industrial", "industrial_web_port"),
        ("api_studio", "api_studio_port"),
        ("portal", "portal_port"),
        ("opcua", "opcua_port"),
        ("mqtt", "mqtt_broker_port"),
        ("acm", "acm_port"),
    ]:
        try:
            flags[label] = is_port_listening(int(ports[key]))
        except Exception:
            flags[label] = False
    return {
        "ports": ports,
        "urls": urls_for(ports),
        "status": flags,
        "log": tail_log(),
    }


def start_hidden_suite() -> int:
    ports = load_ports()
    conflicts = port_conflicts(ports)
    if conflicts:
        log_line("Ports already listening: " + "; ".join(conflicts))
    ok, msg = start_services(ports, include_portal=True, open_browser_flag=False)
    log_line(msg)
    if ok:
        time.sleep(3)
        open_app_window(f"http://localhost:{ports['portal_port']}")
        return 0
    return 1


def save_ports_from_env() -> tuple[bool, str]:
    ports = ports_from_env()
    errors = validate_ports(ports)
    if errors:
        return False, "; ".join(errors)
    save_ports(ports)
    return True, "Selected ports saved to simulator_ports.bat and simulator_ports.json."


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulator suite runtime bootstrap")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ensure-env", help="Create or refresh the bundled-runtime virtual environment.")
    subparsers.add_parser("save-ports-from-env", help="Validate and persist port values from environment variables.")
    subparsers.add_parser("start-hidden", help="Start the hidden application-mode suite.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.command == "ensure-env":
        ok, msg = setup_environment()
        print(msg)
        return 0 if ok else 1
    if args.command == "save-ports-from-env":
        ok, msg = save_ports_from_env()
        print(msg)
        return 0 if ok else 1
    if args.command == "start-hidden":
        return start_hidden_suite()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
