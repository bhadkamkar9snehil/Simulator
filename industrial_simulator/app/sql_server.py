from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
HELPER = Path(__file__).with_name("sql_server_helper.ps1")


def run_sql_action(
    action: str,
    config: dict[str, Any],
    rows: list[dict[str, Any]] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    payload = dict(config or {})
    payload["action"] = action
    if rows is not None:
        payload["rows"] = rows

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as handle:
        json.dump(payload, handle)
        payload_path = handle.name

    try:
        powershell = "powershell.exe" if os.name == "nt" else "pwsh"
        completed = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HELPER), payload_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        try:
            result = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            result = {"raw": stdout}
        result["returncode"] = completed.returncode
        if stderr:
            result["stderr"] = stderr
        if completed.returncode != 0:
            result.setdefault("ok", False)
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            os.unlink(payload_path)
        except OSError:
            pass
