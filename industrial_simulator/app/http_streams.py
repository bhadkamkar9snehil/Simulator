from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app import job_manager
from app.source_simulators.jobs import source_jobs_snapshot

SnapshotFactory = Callable[[], dict[str, Any]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _websocket_runtime_available() -> tuple[bool, str]:
    try:
        import websockets  # noqa: F401

        return True, "websockets"
    except Exception:
        pass
    try:
        import wsproto  # noqa: F401

        return True, "wsproto"
    except Exception:
        return False, "Install websockets or wsproto in the bundled runtime to enable live WebSocket transport."


class HttpStreamHub:
    def __init__(self) -> None:
        self.active_clients = 0
        self.total_connections = 0
        self.messages_sent = 0
        self.bytes_sent = 0
        self.last_event_at: str | None = None
        self.last_client_kind: str | None = None
        self.started_at = _now_iso()

    def metrics(self) -> dict[str, Any]:
        websocket_available, websocket_detail = _websocket_runtime_available()
        transports = ["snapshot", "ndjson", "sse"]
        if websocket_available:
            transports.append("websocket")
        return {
            "enabled": True,
            "transports": transports,
            "websocket_available": websocket_available,
            "websocket_detail": websocket_detail,
            "active_clients": self.active_clients,
            "total_connections": self.total_connections,
            "messages_sent": self.messages_sent,
            "bytes_sent": self.bytes_sent,
            "last_event_at": self.last_event_at,
            "last_client_kind": self.last_client_kind,
            "started_at": self.started_at,
            "backpressure": {
                "mode": "per-client interval pull",
                "bounded_queue_size": 1,
            },
        }

    def connect(self, kind: str) -> None:
        self.active_clients += 1
        self.total_connections += 1
        self.last_client_kind = kind

    def disconnect(self) -> None:
        self.active_clients = max(0, self.active_clients - 1)

    def record(self, payload: bytes) -> None:
        self.messages_sent += 1
        self.bytes_sent += len(payload)
        self.last_event_at = _now_iso()


stream_hub = HttpStreamHub()


def stream_snapshot(simulator: Any, protocol_adapter: Any, value_limit: int = 100) -> dict[str, Any]:
    current = simulator.get_current_values().model_dump()
    values = current.get("values") or []
    jobs = [job.model_dump() for job in job_manager.list_jobs()]
    active_jobs = [job for job in jobs if job.get("state") in {"queued", "running", "paused"}]
    return {
        "timestamp": _now_iso(),
        "simulator": simulator.get_status(),
        "protocol": protocol_adapter.get_status(),
        "jobs": {
            "total": len(jobs),
            "active": len(active_jobs),
            "items": jobs[:50],
        },
        "current_values": {
            "updated_at": current.get("updated_at"),
            "count": len(values),
            "items": values[: max(0, value_limit)],
        },
        "source_outputs": source_jobs_snapshot(limit=50, row_limit=max(0, min(value_limit, 20))),
    }


async def ndjson_generator(
    snapshot_factory: SnapshotFactory,
    interval_ms: int,
    limit: int | None,
) -> Any:
    stream_hub.connect("ndjson")
    sent = 0
    try:
        while limit is None or sent < limit:
            payload = json.dumps(snapshot_factory(), default=str, separators=(",", ":")).encode("utf-8") + b"\n"
            stream_hub.record(payload)
            sent += 1
            yield payload
            if limit is not None and sent >= limit:
                break
            await asyncio.sleep(max(interval_ms, 50) / 1000)
    finally:
        stream_hub.disconnect()


async def sse_generator(
    snapshot_factory: SnapshotFactory,
    interval_ms: int,
    limit: int | None,
) -> Any:
    stream_hub.connect("sse")
    sent = 0
    try:
        while limit is None or sent < limit:
            event_id = stream_hub.messages_sent + 1
            data = json.dumps(snapshot_factory(), default=str, separators=(",", ":"))
            payload = f"id: {event_id}\nevent: simulator.snapshot\ndata: {data}\n\n".encode("utf-8")
            stream_hub.record(payload)
            sent += 1
            yield payload
            if limit is not None and sent >= limit:
                break
            await asyncio.sleep(max(interval_ms, 50) / 1000)
    finally:
        stream_hub.disconnect()


async def websocket_loop(
    send_json: Callable[[dict[str, Any]], Awaitable[None]],
    snapshot_factory: SnapshotFactory,
    interval_ms: int,
    limit: int | None,
) -> None:
    stream_hub.connect("websocket")
    sent = 0
    try:
        while limit is None or sent < limit:
            payload = snapshot_factory()
            encoded = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
            await send_json(payload)
            stream_hub.record(encoded)
            sent += 1
            if limit is not None and sent >= limit:
                break
            await asyncio.sleep(max(interval_ms, 50) / 1000)
    finally:
        stream_hub.disconnect()
