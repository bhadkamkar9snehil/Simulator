from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
EVENT_LOG = LOG_DIR / "simulator-events.jsonl"
TEXT_LOG = LOG_DIR / "simulator.log"
LEGACY_LAUNCHER_LOG = ROOT / "launcher.log"
MAX_LOG_BYTES = 10 * 1024 * 1024
MAX_ARCHIVES = 5
_LOCK = threading.RLock()
_CONFIGURED = False

LEVELS = {"DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_text(value: Any, max_len: int = 1600) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def _sanitize_fields(fields: dict[str, Any] | None) -> dict[str, Any]:
    if not fields:
        return {}
    clean: dict[str, Any] = {}
    for key, value in fields.items():
        if value is None:
            continue
        key_text = str(key).strip()
        if not key_text:
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[key_text] = value
        elif isinstance(value, Path):
            clean[key_text] = str(value)
        else:
            clean[key_text] = _safe_text(value, 800)
    return clean


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _rotate(path: Path) -> None:
    if not path.exists() or path.stat().st_size < MAX_LOG_BYTES:
        return
    for index in range(MAX_ARCHIVES, 0, -1):
        src = path.with_name(f"{path.name}.{index}")
        dst = path.with_name(f"{path.name}.{index + 1}")
        if index == MAX_ARCHIVES and src.exists():
            src.unlink()
        elif src.exists():
            src.replace(dst)
    path.replace(path.with_name(f"{path.name}.1"))


def _format_text(record: dict[str, Any]) -> str:
    parts = [
        record["timestamp"],
        record["level"],
        record["service"],
        record["source"],
        record["event"],
        f"op={record['operation_id']}",
        record["message"],
    ]
    fields = record.get("fields") or {}
    if fields:
        parts.append("fields=" + json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return " | ".join(_safe_text(part, 2000) for part in parts)


def emit_event(
    event: str,
    message: str,
    *,
    level: str = "INFO",
    service: str = "Suite",
    source: str = "runtime",
    operation_id: str | None = None,
    duration_ms: int | None = None,
    fields: dict[str, Any] | None = None,
    exc: BaseException | None = None,
) -> dict[str, Any]:
    normalized_level = level.upper().replace("WARNING", "WARN")
    if normalized_level not in {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}:
        raise ValueError(f"Unsupported log level: {level}")
    operation = operation_id or uuid.uuid4().hex[:12]
    clean_fields = _sanitize_fields(fields)
    if duration_ms is not None:
        clean_fields["duration_ms"] = int(duration_ms)
    if exc is not None:
        clean_fields["exception_type"] = type(exc).__name__
        clean_fields["exception"] = _safe_text(exc, 1200)
        clean_fields["traceback"] = _safe_text("".join(traceback.format_exception(exc)), 6000)
    record = {
        "id": uuid.uuid4().hex,
        "timestamp": _utc_now(),
        "level": normalized_level,
        "service": _safe_text(service, 80),
        "source": _safe_text(source, 120),
        "event": _safe_text(event, 160),
        "operation_id": operation,
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
        "message": _safe_text(message),
        "fields": clean_fields,
    }
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    text_line = _format_text(record)
    with _LOCK:
        _ensure_log_dir()
        _rotate(EVENT_LOG)
        _rotate(TEXT_LOG)
        with EVENT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        with TEXT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(text_line + "\n")
        with LEGACY_LAUNCHER_LOG.open("a", encoding="utf-8") as handle:
            handle.write(text_line + "\n")
    return record


def infer_level(text: str) -> str:
    lower = text.lower()
    if any(token in lower for token in ["traceback", "exception", "error", "failed", "failure"]):
        return "ERROR"
    if any(token in lower for token in ["warn", "conflict", "waiting", "retry"]):
        return "WARN"
    return "INFO"


def log_text(message: str, *, service: str = "Suite", source: str = "runtime", level: str | None = None, event: str = "runtime.message", operation_id: str | None = None, fields: dict[str, Any] | None = None) -> dict[str, Any] | None:
    clean = _safe_text(message)
    if not clean:
        return None
    return emit_event(event, clean, level=level or infer_level(clean), service=service, source=source, operation_id=operation_id, fields=fields)


@contextmanager
def operation(event: str, message: str, *, service: str = "Suite", source: str = "runtime", fields: dict[str, Any] | None = None) -> Iterator[str]:
    op_id = uuid.uuid4().hex[:12]
    start = time.perf_counter()
    emit_event(f"{event}.start", message, service=service, source=source, operation_id=op_id, fields=fields)
    try:
        yield op_id
    except Exception as exc:
        duration = int((time.perf_counter() - start) * 1000)
        emit_event(f"{event}.failed", f"{message} failed", level="ERROR", service=service, source=source, operation_id=op_id, duration_ms=duration, fields=fields, exc=exc)
        raise
    else:
        duration = int((time.perf_counter() - start) * 1000)
        emit_event(f"{event}.completed", f"{message} completed", service=service, source=source, operation_id=op_id, duration_ms=duration, fields=fields)


def _read_jsonl(path: Path, max_lines: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    records: list[dict[str, Any]] = []
    start = max(0, len(lines) - max_lines)
    for idx, raw in enumerate(lines[start:], start=start):
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            record = {
                "id": f"corrupt-{idx}",
                "timestamp": "",
                "level": "ERROR",
                "service": "LogReader",
                "source": "simulator-events.jsonl",
                "event": "log.corrupt_record",
                "operation_id": "",
                "pid": 0,
                "thread": "",
                "message": "Corrupt JSONL log record",
                "fields": {"line": idx + 1, "raw": raw[:1000]},
            }
        record["_line"] = idx
        records.append(record)
    return records


def log_entries(limit: int = 300, level: str = "", source: str = "", query: str = "", service: str = "", event: str = "") -> list[dict[str, Any]]:
    rows = _read_jsonl(EVENT_LOG, max(limit * 5, 1000))
    level_filter = level.upper().replace("WARNING", "WARN").strip()
    source_filter = source.strip().lower()
    service_filter = service.strip().lower()
    event_filter = event.strip().lower()
    query_filter = query.strip().lower()
    if level_filter:
        rows = [row for row in rows if str(row.get("level", "")).upper() == level_filter]
    if source_filter:
        rows = [row for row in rows if source_filter in str(row.get("source", "")).lower()]
    if service_filter:
        rows = [row for row in rows if service_filter in str(row.get("service", "")).lower()]
    if event_filter:
        rows = [row for row in rows if event_filter in str(row.get("event", "")).lower()]
    if query_filter:
        rows = [
            row for row in rows
            if query_filter in json.dumps(row, ensure_ascii=False, sort_keys=True).lower()
        ]
    return rows[-limit:]


def logs_payload(limit: int = 300, level: str = "", source: str = "", query: str = "", service: str = "", event: str = "") -> dict[str, Any]:
    entries = log_entries(limit=limit, level=level, source=source, query=query, service=service, event=event)
    universe = log_entries(limit=1000)
    return {
        "entries": [
            {
                "id": entry.get("_line", index),
                "timestamp": entry.get("timestamp", ""),
                "level": entry.get("level", "INFO"),
                "service": entry.get("service", ""),
                "source": entry.get("source", ""),
                "event": entry.get("event", ""),
                "operation_id": entry.get("operation_id", ""),
                "message": entry.get("message", ""),
                "fields": entry.get("fields", {}),
                "raw": json.dumps({k: v for k, v in entry.items() if k != "_line"}, ensure_ascii=False, sort_keys=True),
            }
            for index, entry in enumerate(entries)
        ],
        "sources": sorted({str(entry.get("source", "")) for entry in universe if entry.get("source")}),
        "services": sorted({str(entry.get("service", "")) for entry in universe if entry.get("service")}),
        "events": sorted({str(entry.get("event", "")) for entry in universe if entry.get("event")}),
        "levels": ["ERROR", "WARN", "INFO", "DEBUG"],
        "count": len(entries),
        "log_file": str(EVENT_LOG),
        "text_log_file": str(TEXT_LOG),
    }


def clear_logs() -> None:
    with _LOCK:
        _ensure_log_dir()
        EVENT_LOG.write_text("", encoding="utf-8")
        TEXT_LOG.write_text("", encoding="utf-8")
        LEGACY_LAUNCHER_LOG.write_text("", encoding="utf-8")
    emit_event("logs.cleared", "Logs cleared from portal.", service="Portal", source="logs", level="WARN")


def tail_text(lines: int = 120) -> str:
    if not TEXT_LOG.exists():
        return ""
    data = TEXT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(data[-lines:])


class StructuredLogHandler(logging.Handler):
    def __init__(self, *, service: str, source: str):
        super().__init__()
        self.service = service
        self.source = source

    def emit(self, record: logging.LogRecord) -> None:
        exc = record.exc_info[1] if record.exc_info else None
        event = getattr(record, "event", record.name.replace(".", "_"))
        emit_event(
            str(event),
            record.getMessage(),
            level=record.levelname,
            service=getattr(record, "service", self.service),
            source=getattr(record, "source", self.source),
            operation_id=getattr(record, "operation_id", None),
            fields=getattr(record, "fields", None),
            exc=exc,
        )


def configure_python_logging(*, service: str, source: str, level: int = logging.INFO) -> None:
    global _CONFIGURED
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not any(isinstance(handler, StructuredLogHandler) and handler.service == service for handler in root_logger.handlers):
        root_logger.addHandler(StructuredLogHandler(service=service, source=source))
    if not any(isinstance(handler, logging.StreamHandler) and getattr(handler, "_industrial_console", False) for handler in root_logger.handlers):
        console = logging.StreamHandler(sys.stdout)
        console._industrial_console = True  # type: ignore[attr-defined]
        console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        root_logger.addHandler(console)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _CONFIGURED = True
