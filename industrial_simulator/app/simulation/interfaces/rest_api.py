from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..models import SignalDefinition, SimulationFrame, TargetBinding, TargetRuntimeStatus

router = APIRouter(prefix="/sim-api", tags=["Simulated APIs"])

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_RESPONSE_MODES = {"values", "frame", "record", "history", "template"}
_SELECTION_MODES = {"current", "history_match"}
_TOKEN_RE = re.compile(r"\$\{([A-Za-z0-9_.-]+)\}")
_SEGMENT_PARAM_RE = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_path(value: str) -> str:
    return "/" + value.strip().strip("/")


def _parse_fields(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _parse_headers(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    headers: dict[str, str] = {}
    for line in str(value or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"API header must use 'Name: value': {line}")
        name, item = line.split(":", 1)
        name = name.strip()
        if not name:
            raise ValueError("API header name cannot be empty.")
        headers[name] = item.strip()
    return headers


def _parse_template(value: Any) -> Any:
    if value in (None, ""):
        return {}
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"API response template is not valid JSON: {exc.msg}") from exc


def _path_parts(path: str) -> list[str]:
    cleaned = _clean_path(path).strip("/")
    return [] if not cleaned else cleaned.split("/")


def _path_pattern(path: str) -> re.Pattern[str]:
    names: list[str] = []
    parts: list[str] = []
    for segment in _path_parts(path):
        match = _SEGMENT_PARAM_RE.fullmatch(segment)
        if match:
            name = match.group(1)
            if name in names:
                raise ValueError(f"Duplicate API path parameter: {name}")
            names.append(name)
            parts.append(fr"(?P<{name}>[^/]+)")
        elif "{" in segment or "}" in segment:
            raise ValueError(f"Invalid API path segment: {segment}")
        else:
            parts.append(re.escape(segment))
    suffix = "/".join(parts)
    return re.compile(r"^/" + suffix + r"/?$")


def _route_shape(path: str) -> tuple[str, ...]:
    return tuple("{}" if _SEGMENT_PARAM_RE.fullmatch(segment) else segment for segment in _path_parts(path))


def _specificity(path: str) -> tuple[int, int]:
    parts = _path_parts(path)
    static_count = sum(1 for segment in parts if not _SEGMENT_PARAM_RE.fullmatch(segment))
    return static_count, len(parts)


def validate_api_config(config: dict[str, Any]) -> dict[str, Any]:
    method = str(config.get("method", "GET")).strip().upper()
    if method not in _ALLOWED_METHODS:
        raise ValueError(f"Unsupported API method: {method}")

    path = _clean_path(str(config.get("path", "/")))
    _path_pattern(path)

    response_mode = str(config.get("response_mode", "values")).strip().lower()
    if response_mode not in _RESPONSE_MODES:
        raise ValueError(f"Unsupported API response mode: {response_mode}")

    selection_mode = str(config.get("selection_mode", "current")).strip().lower()
    if selection_mode not in _SELECTION_MODES:
        raise ValueError(f"Unsupported API selection mode: {selection_mode}")

    status_code = int(config.get("status_code", 200))
    empty_status_code = int(config.get("empty_status_code", 503))
    not_found_status = int(config.get("not_found_status", 404))
    if any(not 100 <= code <= 599 for code in (status_code, empty_status_code, not_found_status)):
        raise ValueError("API status codes must be between 100 and 599.")

    delay_ms = int(config.get("delay_ms", 0))
    history_size = int(config.get("history_size", 100))
    if not 0 <= delay_ms <= 300_000:
        raise ValueError("API delay_ms must be between 0 and 300000.")
    if not 1 <= history_size <= 100_000:
        raise ValueError("API history_size must be between 1 and 100000.")

    match_frame = str(config.get("match_frame", "")).strip()
    match_request = str(config.get("match_request", "")).strip()
    if selection_mode == "history_match" and (not match_frame or not match_request):
        raise ValueError("History-match API selection requires match_frame and match_request paths.")

    return {
        "method": method,
        "path": path,
        "response_mode": response_mode,
        "selection_mode": selection_mode,
        "status_code": status_code,
        "empty_status_code": empty_status_code,
        "not_found_status": not_found_status,
        "delay_ms": delay_ms,
        "history_size": history_size,
        "fields": _parse_fields(config.get("fields")),
        "envelope": str(config.get("envelope", "")).strip(),
        "include_context": bool(config.get("include_context", False)),
        "include_system_fields": bool(config.get("include_system_fields", True)),
        "response_headers": _parse_headers(config.get("response_headers")),
        "required_headers": _parse_headers(config.get("required_headers")),
        "response_template": _parse_template(config.get("response_template")),
        "match_frame": match_frame,
        "match_request": match_request,
    }


@dataclass
class ApiProjection:
    simulation_id: str
    target_id: str
    method: str
    path: str
    response_mode: str
    selection_mode: str
    status_code: int
    empty_status_code: int
    not_found_status: int
    delay_ms: int
    fields: list[str]
    envelope: str
    include_context: bool
    include_system_fields: bool
    response_headers: dict[str, str]
    required_headers: dict[str, str]
    response_template: Any
    history_size: int
    match_frame: str
    match_request: str
    pattern: re.Pattern[str]
    current: SimulationFrame | None = None
    history: deque[SimulationFrame] = field(init=False)
    request_count: int = 0
    last_request_at: str | None = None

    def __post_init__(self) -> None:
        self.history = deque(maxlen=self.history_size)

    def publish(self, frame: SimulationFrame) -> None:
        self.current = frame
        self.history.append(frame)


class ApiRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ApiProjection] = {}

    def register(self, simulation_id: str, target_id: str, config: dict[str, Any]) -> ApiProjection:
        validated = validate_api_config(config)
        method = validated["method"]
        path = validated["path"]
        shape = _route_shape(path)
        for existing in self._items.values():
            if existing.method == method and _route_shape(existing.path) == shape:
                raise ValueError(f"API route conflicts with {existing.method} /sim-api{existing.path}")

        projection = ApiProjection(
            simulation_id=simulation_id,
            target_id=target_id,
            pattern=_path_pattern(path),
            **validated,
        )
        self._items[(simulation_id, target_id)] = projection
        return projection

    def remove(self, simulation_id: str, target_id: str) -> None:
        self._items.pop((simulation_id, target_id), None)

    def match(self, method: str, path: str) -> tuple[ApiProjection, dict[str, str]]:
        clean = _clean_path(path)
        matches: list[tuple[ApiProjection, re.Match[str]]] = []
        for item in self._items.values():
            match = item.pattern.fullmatch(clean)
            if match:
                matches.append((item, match))

        method_matches = [(item, match) for item, match in matches if item.method == method]
        if method_matches:
            item, match = max(method_matches, key=lambda pair: _specificity(pair[0].path))
            return item, match.groupdict()
        if matches:
            allowed = ", ".join(sorted({item.method for item, _ in matches}))
            raise HTTPException(status_code=405, detail="Method not allowed.", headers={"Allow": allowed})
        raise HTTPException(status_code=404, detail=f"Simulated API route not found: {clean}")

    def endpoints(self) -> list[dict[str, Any]]:
        return [
            {
                "simulation_id": item.simulation_id,
                "target_id": item.target_id,
                "method": item.method,
                "path": f"/sim-api{item.path}",
                "response_mode": item.response_mode,
                "selection_mode": item.selection_mode,
                "request_count": item.request_count,
                "last_request_at": item.last_request_at,
            }
            for item in self._items.values()
        ]


api_registry = ApiRegistry()


class RestApiTarget:
    def __init__(self, binding: TargetBinding):
        self.target_id = binding.target_id
        self.binding = binding
        self._simulation_id = ""
        self._projection: ApiProjection | None = None
        self._endpoint: str | None = None
        self._state = "created"
        self._last_details: dict[str, Any] = {}

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None:
        if self.binding.hosting_mode != "shared":
            raise ValueError("API target uses the shared Industrial HTTP host.")
        self._simulation_id = simulation_id
        self._projection = api_registry.register(simulation_id, self.target_id, self.binding.config)
        self._endpoint = f"{self._projection.method} /sim-api{self._projection.path}"
        self._state = "running"
        self._last_details = self._details(self._projection)

    async def publish(self, frame: SimulationFrame) -> None:
        if self._projection is None:
            raise RuntimeError("API target is not started.")
        self._projection.publish(frame)
        self._last_details = self._details(self._projection)

    async def stop(self) -> None:
        if self._projection is not None:
            self._last_details = self._details(self._projection)
        if self._simulation_id:
            api_registry.remove(self._simulation_id, self.target_id)
        self._projection = None
        self._state = "stopped"

    def status(self) -> TargetRuntimeStatus:
        details = self._details(self._projection) if self._projection else dict(self._last_details)
        return TargetRuntimeStatus(
            target_id=self.target_id,
            kind="api",
            state=self._state,  # type: ignore[arg-type]
            endpoint=self._endpoint,
            details=details,
        )

    @staticmethod
    def _details(projection: ApiProjection | None) -> dict[str, Any]:
        if projection is None:
            return {}
        return {
            "request_count": projection.request_count,
            "last_request_at": projection.last_request_at,
            "history_count": len(projection.history),
            "method": projection.method,
            "path": f"/sim-api{projection.path}",
            "response_mode": projection.response_mode,
            "selection_mode": projection.selection_mode,
        }


def _signal_values(frame: SimulationFrame) -> dict[str, Any]:
    return {name: signal.value for name, signal in frame.values.items()}


def _frame_scope(frame: SimulationFrame | None) -> dict[str, Any]:
    return {
        "values": _signal_values(frame) if frame else {},
        "context": dict(frame.context) if frame else {},
        "meta": {
            "sequence": frame.sequence if frame else None,
            "timestamp": frame.timestamp if frame else None,
            "source_timestamp": frame.source_timestamp if frame else None,
            "simulation_id": frame.simulation_id if frame else None,
        },
    }


def _record(frame: SimulationFrame, projection: ApiProjection) -> dict[str, Any]:
    values = _signal_values(frame)
    if projection.fields:
        values = {key: values.get(key) for key in projection.fields if key in values}
    record: dict[str, Any] = dict(values)
    if projection.include_context:
        record.update(frame.context)
    if projection.include_system_fields:
        record = {**_frame_scope(frame)["meta"], **record}
    return record


def _lookup(scope: dict[str, Any], key: str) -> Any:
    current: Any = scope
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _render_template(value: Any, scope: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render_template(item, scope) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_template(item, scope) for item in value]
    if not isinstance(value, str):
        return value
    full = _TOKEN_RE.fullmatch(value)
    if full:
        return _lookup(scope, full.group(1))

    def replace(match: re.Match[str]) -> str:
        item = _lookup(scope, match.group(1))
        return "" if item is None else str(item)

    return _TOKEN_RE.sub(replace, value)


def _request_scope(frame: SimulationFrame | None, path_params: dict[str, str], query: dict[str, str], body: Any) -> dict[str, Any]:
    return {
        **_frame_scope(frame),
        "path": path_params,
        "query": query,
        "body": body if isinstance(body, dict) else {"value": body},
    }


def _selected_frame(projection: ApiProjection, path_params: dict[str, str], query: dict[str, str], body: Any) -> SimulationFrame | None:
    if projection.selection_mode == "current" or projection.response_mode == "history":
        return projection.current
    request_value = _lookup(_request_scope(None, path_params, query, body), projection.match_request)
    if request_value is None:
        raise HTTPException(status_code=400, detail=f"Request value not found: {projection.match_request}")
    for frame in reversed(projection.history):
        frame_value = _lookup(_frame_scope(frame), projection.match_frame)
        if frame_value == request_value or (frame_value is not None and str(frame_value) == str(request_value)):
            return frame
    raise HTTPException(status_code=projection.not_found_status, detail="No simulated record matched the request.")


def _response_payload(projection: ApiProjection, path_params: dict[str, str], query: dict[str, str], body: Any) -> Any:
    frame = _selected_frame(projection, path_params, query, body)
    if projection.response_mode == "template":
        payload = _render_template(projection.response_template, _request_scope(frame, path_params, query, body))
    else:
        if frame is None:
            raise HTTPException(status_code=projection.empty_status_code, detail="Simulation has not published data yet.")
        if projection.response_mode == "values":
            payload = _signal_values(frame)
            if projection.fields:
                payload = {key: payload.get(key) for key in projection.fields if key in payload}
        elif projection.response_mode == "frame":
            payload = frame.model_dump(mode="json")
        elif projection.response_mode == "record":
            payload = _record(frame, projection)
        else:
            payload = [_record(item, projection) for item in projection.history]

    return {projection.envelope: payload} if projection.envelope else payload


async def _dispatch(request: Request, request_path: str) -> JSONResponse:
    projection, path_params = api_registry.match(request.method.upper(), request_path)
    for name, expected in projection.required_headers.items():
        if request.headers.get(name) != expected:
            raise HTTPException(status_code=401, detail=f"Required request header missing or invalid: {name}")
    if projection.delay_ms:
        await asyncio.sleep(projection.delay_ms / 1000.0)
    body: Any = None
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        raw = await request.body()
        if raw:
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = raw.decode("utf-8", errors="replace")
    projection.request_count += 1
    projection.last_request_at = _utc_now_iso()
    payload = _response_payload(projection, path_params, dict(request.query_params), body)
    return JSONResponse(content=payload, status_code=projection.status_code, headers=projection.response_headers)


@router.api_route("", methods=sorted(_ALLOWED_METHODS))
async def simulated_api_root(request: Request) -> JSONResponse:
    return await _dispatch(request, "/")


@router.api_route("/{request_path:path}", methods=sorted(_ALLOWED_METHODS))
async def simulated_api(request: Request, request_path: str) -> JSONResponse:
    return await _dispatch(request, "/" + request_path)
