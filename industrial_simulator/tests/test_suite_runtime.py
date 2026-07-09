from __future__ import annotations

import sys
from pathlib import Path


def test_start_service_fails_when_process_exits_before_health_ready(tmp_path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import suite_runtime

    suite_runtime.processes.clear()
    monkeypatch.setattr(suite_runtime, "PIDS_JSON", tmp_path / "runtime_pids.json")

    ok = suite_runtime.start_service(
        "BrokenTestService",
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        Path.cwd(),
        {},
        health_url="http://127.0.0.1:9/health",
    )

    assert ok is False
