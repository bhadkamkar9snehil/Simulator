from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any

try:
    from asyncua.common.callback import CallbackType  # type: ignore
except Exception:  # pragma: no cover
    CallbackType = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _status_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        return value.name
    except Exception:
        return str(value)


class OpcUaDiagnostics:
    """Small observability layer for asyncua callbacks and external sessions.

    All access to asyncua private session/subscription fields is intentionally
    isolated here. The snapshot reports capability availability so a future
    asyncua change degrades diagnostics explicitly rather than looking like
    "zero connected clients".
    """

    def __init__(self, recent_limit: int = 100) -> None:
        self._lock = Lock()
        self._recent = deque(maxlen=recent_limit)
        self.reset()

    def reset(self) -> None:
        with getattr(self, "_lock", Lock()):
            self.started_at = _utc_now()
            self.read_requests = 0
            self.read_nodes = 0
            self.write_requests = 0
            self.write_nodes = 0
            self.failed_writes = 0
            self.last_read_at: str | None = None
            self.last_write_at: str | None = None
            if hasattr(self, "_recent"):
                self._recent.clear()

    async def on_post_read(self, event: Any, _service: Any = None) -> None:
        if not getattr(event, "is_external", False):
            return
        params = getattr(event, "request_params", None)
        nodes = list(getattr(params, "NodesToRead", []) or [])
        now = _utc_now()
        with self._lock:
            self.read_requests += 1
            self.read_nodes += len(nodes)
            self.last_read_at = now
            self._recent.appendleft({
                "at": now,
                "kind": "read",
                "node_count": len(nodes),
                "nodes": [str(getattr(node, "NodeId", "")) for node in nodes[:12]],
            })

    async def on_post_write(self, event: Any, _service: Any = None) -> None:
        if not getattr(event, "is_external", False):
            return
        params = getattr(event, "request_params", None)
        nodes = list(getattr(params, "NodesToWrite", []) or [])
        results = list(getattr(event, "response_params", []) or [])
        failures = sum(1 for result in results if getattr(result, "is_bad", lambda: False)())
        now = _utc_now()
        entries = []
        for index, node in enumerate(nodes[:12]):
            result = results[index] if index < len(results) else None
            entries.append({
                "node_id": str(getattr(node, "NodeId", "")),
                "attribute": str(getattr(node, "AttributeId", "")),
                "status": _status_text(result),
            })
        with self._lock:
            self.write_requests += 1
            self.write_nodes += len(nodes)
            self.failed_writes += failures
            self.last_write_at = now
            self._recent.appendleft({
                "at": now,
                "kind": "write",
                "node_count": len(nodes),
                "failed": failures,
                "nodes": entries,
            })

    def attach(self, server: Any) -> bool:
        if CallbackType is None or server is None:
            return False
        iserver = getattr(server, "iserver", None)
        if iserver is None or not hasattr(iserver, "subscribe_server_callback"):
            return False
        iserver.subscribe_server_callback(CallbackType.PostRead, self.on_post_read)
        iserver.subscribe_server_callback(CallbackType.PostWrite, self.on_post_write)
        return True

    def _sessions(self, server: Any) -> tuple[list[dict[str, Any]], bool, bool]:
        iserver = getattr(server, "iserver", None)
        if iserver is None or not hasattr(iserver, "_external_sessions"):
            return [], False, False

        sessions = getattr(iserver, "_external_sessions", {})
        values = list(sessions.values()) if isinstance(sessions, dict) else []
        now = time.monotonic()
        result = []
        subscription_service = getattr(iserver, "subscription_service", None)
        subscriptions_available = bool(subscription_service is not None and hasattr(subscription_service, "subscriptions"))
        subscriptions = getattr(subscription_service, "subscriptions", {}) if subscriptions_available else {}
        for session in values:
            state = getattr(getattr(session, "state", None), "name", str(getattr(session, "state", "unknown")))
            last_activity = getattr(session, "_last_activity", None)
            sub_count: int | None = None
            if subscriptions_available and isinstance(subscriptions, dict):
                sid = getattr(session, "session_id", None)
                sub_count = sum(1 for sub in subscriptions.values() if getattr(sub, "session_id", None) == sid)
            result.append({
                "name": str(getattr(session, "name", "client")),
                "session_id": str(getattr(session, "session_id", "")),
                "state": state,
                "user": str(getattr(session, "user", "")),
                "timeout_ms": getattr(session, "session_timeout", None),
                "last_activity_age_seconds": round(max(0.0, now - last_activity), 3) if isinstance(last_activity, (int, float)) else None,
                "subscriptions": sub_count,
            })
        return result, True, subscriptions_available

    def snapshot(self, server: Any) -> dict[str, Any]:
        sessions, session_introspection_available, subscription_introspection_available = self._sessions(server)
        with self._lock:
            return {
                "started_at": self.started_at,
                "session_introspection_available": session_introspection_available,
                "subscription_introspection_available": subscription_introspection_available,
                "connected_clients": (
                    sum(1 for session in sessions if session["state"] == "Activated")
                    if session_introspection_available else None
                ),
                "session_count": len(sessions) if session_introspection_available else None,
                "sessions": sessions,
                "read_requests": self.read_requests,
                "read_nodes": self.read_nodes,
                "write_requests": self.write_requests,
                "write_nodes": self.write_nodes,
                "failed_writes": self.failed_writes,
                "last_read_at": self.last_read_at,
                "last_write_at": self.last_write_at,
                "recent_activity": list(self._recent),
            }
