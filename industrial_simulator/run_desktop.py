import os
import sys
import time
import socket
import threading
import webbrowser
from pathlib import Path

import uvicorn


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def wait_for_port(host: str, port: int, timeout_seconds: int = 20) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def open_browser():
    if wait_for_port("127.0.0.1", 8000):
        webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    os.environ["ITS_BASE_DIR"] = str(app_base_dir())

    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )