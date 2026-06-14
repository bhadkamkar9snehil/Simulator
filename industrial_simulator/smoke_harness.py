import os
import sys
import time
import subprocess
import requests
import json
from pathlib import Path

# Configuration
APP_DIR = Path(__file__).resolve().parent
VENV_PYTHON = "/c/Users/Admin/Documents/Office/Simulator/.venv/Scripts/python.exe"

def run_simulator():
    print("Starting simulator...")
    cmd = [VENV_PYTHON, str(APP_DIR / "run_desktop.py")]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False
    )
    return proc

def wait_for_health(port=8000, timeout=30):
    print(f"Waiting for health check on port {port}...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"http://127.0.0.1:{port}/api/health")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok":
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False

def main():
    proc = run_simulator()
    
    if not wait_for_health():
        print("FAIL: Simulator health check timed out.")
        proc.kill()
        sys.exit(1)
    print("OK: Simulator health check passed.")

    try:
        print("Checking generators...")
        resp = requests.get("http://127.0.0.1:8000/api/generators")
        expect_ok(resp.status_code == 200 and "generators" in resp.json(), "generators list")

        print("Generating petroleum_pipeline CSV...")
        gen_id = "petroleum_pipeline"
        payload = {
            "scenario": "normal",
            "output_filename": "smoke_test_petroleum.csv",
            "parameters": {
                "duration_minutes": 1,
                "sample_rate_hz": 1,
                "seed": 12345,
                "product": "crude"
            },
            "load_into_replay": True
        }
        resp = requests.post(f"http://127.0.0.1:8000/api/generators/{gen_id}/generate", json=payload)
        expect_ok(resp.status_code == 200 and resp.json().get("status") == "generated", "CSV generation")
        
        filename = resp.json().get("filename")
        found = False
        for p in APP_DIR.glob(f"**/{filename}"):
            print(f"OK: Found generated file at {p}")
            found = True
            break
        
        if not found:
            print(f"FAIL: Could not find generated file {filename}")
            sys.exit(1)

        print("Checking replay status...")
        resp = requests.get("http://127.0.0.1:8000/api/replay/status")
        expect_ok(resp.status_code == 200 and resp.json().get("backend") == "ok", "replay status")

        print("All smoke tests passed.")
    except Exception as e:
        print(f"FAIL: Unexpected error: {e}")
        sys.exit(1)
    finally:
        print("Stopping simulator...")
        proc.terminate()
        proc.wait()

def expect_ok(condition, message):
    if not condition:
        print(f"FAIL: {message}")
        sys.exit(1)
    print(f"OK: {message}")

if __name__ == "__main__":
    main()
