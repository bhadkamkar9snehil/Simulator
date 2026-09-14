from __future__ import annotations

import asyncio
import json
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from ..models import SignalDefinition, SimulationFrame, TargetBinding, TargetRuntimeStatus

router = APIRouter(prefix="/sim-api", tags=["Simulated APIs"])

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_RESPONSE_MODES = {"values", "frame", "record", "history", "template"}
_SELECTION_MODES = {"current", "history_match"}
_BODY_MODES = {"json", "text", "empty"}
_ERROR_MODES = {"default", "json", "text", "empty"}
_HISTORY_ORDERS = {"oldest_first", "newest_first"}
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


def _parse_required_values(value: Any) -> list[tuple[str, str | None]]:
    items: list[tuple[str, str | None]] = []
    for line in str(value or "").splitlines():
        line = line.strip()
        if not line:
            continue
        path, separator, expected = line.partition("=")
        path = path.strip()
        if not path.startswith(("path.", "query.", "body.")):
            raise ValueError(f"Required request value must start with path., query., or body.: {path}")
        items.append((path, expected.strip() if separator else None))
    return items


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


def _choice(config: dict[str, Any], key: str, default: str, allowed: set[str], label: str) -> str:
    value = str(config.get(key, default)).strip().lower()
    if value not in allowed:
        raise ValueError(f"Unsupported API {label}: {value}")
    return value


def _status_codes(config: dict[str, Any]) -> tuple[int, int, int, int]:
    codes = (
        int(config.get("status_code", 200)),
        int(config.get("empty_status_code", 503)),
        int(config.get("not_found_status", 404)),
        int(config.get("request_error_status", 400)),
    )
    if any(not 100 <= code <= 599 for code in codes):
        raise ValueError("API status codes must be between 100 and 599.")
    return codes


def _bounded_int(config: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    value = int(config.get(key, default))
    if not minimum <= value <= maximum:
        raise ValueError(f"API {key} must be between {minimum} and {maximum}.")
    return value


def validate_api_config(config: dict[str, Any]) -> dict[str, Any]:
    method = str(config.get("method", "GET")).strip().upper()
    if method not in _ALLOWED_METHODS:
        raise ValueError(f"Unsupported API method: {method}")

    path = _clean_path(str(config.get("path", "/")))
    _path_pattern(path)
    response_mode = _choice(config, "response_mode", "values", _RESPONSE_MODES, "response mode")
    selection_mode = _choice(config, "selection_mode", "current", _SELECTION_MODES, "selection mode")
    body_mode = _choice(config, "body_mode", "json", _BODY_MODES, "body mode")
    error_mode = _choice(config, "error_mode", "default", _ERROR_MODES, "error mode")
    history_order = _choice(config, "history_order", "oldest_first", _HISTORY_ORDERS, "history order")
    status_code, empty_status_code, not_found_status, request_error_status = _status_codes(config)
    delay_ms = _bounded_int(config, "delay_ms", 0, 0, 300_000)
    delay_jitter_ms = _bounded_int(config, "delay_jitter_ms", 0, 0, 300_000)
    history_size = _bounded_int(config, "history_size", 100, 1, 100_000)
    default_page_size = _bounded_int(config, "default_page_size", history_size, 1, 100_000)
    max_page_size = _bounded_int(config, "max_page_size", max(history_size, default_page_size), 1, 100_000)
    if default_page_size > max_page_size:
        raise ValueError("API default_page_size cannot exceed max_page_size.")

    match_frame = str(config.get("match_frame", "")).strip()
    match_request = str(config.get("match_request", "")).strip()
    if selection_mode == "history_match" and (not match_frame or not match_request):
        raise ValueError("History-match API selection requires match_frame and match_request paths.")

    return {
        "method": method,
        "path": path,
        "response_mode": response_mode,
        "selection_mode": selection_mode,
        "body_mode": body_mode,
        "media_type": str(config.get("media_type", "")).strip() or None,
        "error_mode": error_mode,
        "error_media_type": str(config.get("error_media_type", "")).strip() or None,
        "status_code": status_code,
        "empty_status_code": empty_status_code,
        "not_found_status": not_found_status,
        "request_error_status": request_error_status,
        "delay_ms": delay_ms,
        "delay_jitter_ms": delay_jitter_ms,
        "history_size": history_size,
        "history_order": history_order,
        "default_page_size": default_page_size,
        "max_page_size": max_page_size,
        "fields": _parse_fields(config.get("fields")),
        "envelope": str(config.get("envelope", "")).strip(),
        "include_context": bool(config.get("include_context", False)),
        "include_system_fields": bool(config.get("include_system_fields", True)),
        "response_headers": _parse_headers(config.get("response_headers")),
        "required_headers": _parse_headers(config.get("required_headers")),
        "required_request_values": _parse_required_values(config.get("required_request_values")),
        "response_template": _parse_template(config.get("response_template")),
        "text_template": str(config.get("text_template", "")),
        "error_template": _parse_template(config.get("error_template", '{"error":"${error.message}","status":"${error.status}"}')),
        "error_text_template": str(config.get("error_text_template", "${error.status} ${error.message}")),
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
    body_mode: str
    media_type: str | None
    error_mode: str
    error_media_type: str | None
    status_code: int
    empty_status_code: int
    not_found_status: int
    request_error_status: int
    delay_ms: int
    delay_jitter_ms: int
    fields: list[str]
    envelope: str
    include_context: bool
    include_system_fields: bool
    response_headers: dict[str, str]
    required_headers: dict[str, str]
    required_request_values: list[tuple[str, str | None]]
    response_template: Any
    text_template: str
    error_template: Any
    error_text_template: str
    history_size: int
    history_order: str
    default_page_size: int
    max_page_size: int
    match_frame: str
    match_request: str
    pattern: re.Pattern[str]
    current: SimulationFrame | None = None
    history: deque[SimulationFrame] = field(init=False)
    request_count: int = 0
    success_count: int = 0
    client_error_count: int = 0
    server_error_count: int = 0
    last_request_at: str | None = None
    last_status_code: int | None = None
    last_latency_ms: float | None = None

    def __post_init__(self) -> None:
        self.history = deque(maxlen=self.history_size)

    def publish(self, frame: SimulationFrame) -> None:
        self.current = frame
        self.history.append(frame)

    def record_request(self, status_code: int, latency_ms: float) -> None:
        self.last_status_code = status_code
        self.last_latency_ms = round(latency_ms, 2)
        if 200 <= status_code < 400:
            self.success_count += 1
        elif 400 <= status_code < 500:
            self.client_error_count += 1
        elif status_code >= 500:
            self.server_error_count += 1


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
                "body_mode": item.body_mode,
                "selection_mode": item.selection_mode,
                "request_count": item.request_count,
                "success_count": item.success_count,
                "client_error_count": item.client_error_count,
                "server_error_count": item.server_error_count,
                "last_request_at": item.last_request_at,
                "last_status_code": item.last_status_code,
                "last_latency_ms": item.last_latency_ms,
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
            "success_count": projection.success_count,
            "client_error_count": projection.client_error_count,
            "server_error_count": projection.server_error_count,
            "last_request_at": projection.last_request_at,
            "last_status_code": projection.last_status_code,
            "last_latency_ms": projection.last_latency_ms,
            "history_count": len(projection.history),
            "method": projection.method,
            "path": f"/sim-api{projection.path}",
            "response_mode": projection.response_mode,
            "body_mode": projection.body_mode,
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


def _error_scope(
    projection: ApiProjection,
    path_params: dict[str, str],
    query: dict[str, str],
    body: Any,
    exc: HTTPException,
) -> dict[str, Any]:
    return {
        **_request_scope(projection.current, path_params, query, body),
        "error": {"status": exc.status_code, "message": str(exc.detail)},
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


def _history_payload(projection: ApiProjection, query: dict[str, str]) -> list[dict[str, Any]]:
    frames = list(projection.history)
    if projection.history_order == "newest_first":
        frames.reverse()
    offset = _query_int(query, "offset", 0, 0, len(frames))
    limit = _query_int(query, "limit", projection.default_page_size, 1, projection.max_page_size)
    return [_record(item, projection) for item in frames[offset:offset + limit]]


def _query_int(query: dict[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = query.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Query parameter {name} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise HTTPException(status_code=400, detail=f"Query parameter {name} must be between {minimum} and {maximum}.")
    return value


def _json_payload(
    projection: ApiProjection,
    frame: SimulationFrame | None,
    path_params: dict[str, str],
    query: dict[str, str],
    body: Any,
) -> Any:
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
            payload = _history_payload(projection, query)
    return {projection.envelope: payload} if projection.envelope else payload


def _template_uses_frame(value: str) -> bool:
    return any(f"${{{scope}." in value for scope in ("values", "context", "meta"))


def _text_payload(
    projection: ApiProjection,
    frame: SimulationFrame | None,
    path_params: dict[str, str],
    query: dict[str, str],
    body: Any,
) -> str:
    if frame is None and _template_uses_frame(projection.text_template):
        raise HTTPException(status_code=projection.empty_status_code, detail="Simulation has not published data yet.")
    rendered = _render_template(projection.text_template, _request_scope(frame, path_params, query, body))
    return "" if rendered is None else str(rendered)


def _response_headers(
    projection: ApiProjection,
    frame: SimulationFrame | None,
    path_params: dict[str, str],
    query: dict[str, str],
    body: Any,
) -> dict[str, str]:
    scope = _request_scope(frame, path_params, query, body)
    headers: dict[str, str] = {}
    for name, value in projection.response_headers.items():
        rendered = _render_template(value, scope)
        headers[name] = "" if rendered is None else str(rendered)
    return headers


def _bodyless_status(status_code: int) -> bool:
    return status_code < 200 or status_code in {204, 205, 304}


def _response(projection: ApiProjection, request_method: str, path_params: dict[str, str], query: dict[str, str], body: Any) -> Response:
    frame = _selected_frame(projection, path_params, query, body)
    headers = _response_headers(projection, frame, path_params, query, body)
    if request_method == "HEAD" or projection.body_mode == "empty" or _bodyless_status(projection.status_code):
        return Response(status_code=projection.status_code, headers=headers)
    if projection.body_mode == "text":
        return Response(
            content=_text_payload(projection, frame, path_params, query, body),
            status_code=projection.status_code,
            headers=headers,
            media_type=projection.media_type or "text/plain",
        )
    return JSONResponse(
        content=_json_payload(projection, frame, path_params, query, body),
        status_code=projection.status_code,
        headers=headers,
        media_type=projection.media_type or "application/json",
    )


def _error_response(
    projection: ApiProjection,
    path_params: dict[str, str],
    query: dict[str, str],
    body: Any,
    exc: HTTPException,
) -> Response:
    scope = _error_scope(projection, path_params, query, body, exc)
    headers = dict(exc.headers or {})
    for name, value in projection.response_headers.items():
        rendered = _render_template(value, scope)
        headers[name] = "" if rendered is None else str(rendered)
    if projection.error_mode == "empty" or _bodyless_status(exc.status_code):
        return Response(status_code=exc.status_code, headers=headers)
    if projection.error_mode == "text":
        rendered = _render_template(projection.error_text_template, scope)
        return Response(
            content="" if rendered is None else str(rendered),
            status_code=exc.status_code,
            headers=headers,
            media_type=projection.error_media_type or "text/plain",
        )
    payload = _render_template(projection.error_template, scope)
    return JSONResponse(
        content=payload,
        status_code=exc.status_code,
        headers=headers,
        media_type=projection.error_media_type or "application/json",
    )


def _request_delay_seconds(projection: ApiProjection) -> float:
    jitter = random.uniform(0, projection.delay_jitter_ms) if projection.delay_jitter_ms else 0.0
    return (projection.delay_ms + jitter) / 1000.0


def _require_request_values(projection: ApiProjection, path_params: dict[str, str], query: dict[str, str], body: Any) -> None:
    scope = _request_scope(None, path_params, query, body)
    for path, expected in projection.required_request_values:
        actual = _lookup(scope, path)
        if actual is None:
            raise HTTPException(status_code=projection.request_error_status, detail=f"Required request value missing: {path}")
        if expected is not None and str(actual) != expected:
            raise HTTPException(status_code=projection.request_error_status, detail=f"Required request value invalid: {path}")


async def _dispatch(request: Request, request_path: str) -> Response:
    projection, path_params = api_registry.match(request.method.upper(), request_path)
    started = time.perf_counter()
    projection.request_count += 1
    projection.last_request_at = _utc_now_iso()
    status_code = 500
    body: Any = None
    query = dict(request.query_params)
    try:
        for name, expected in projection.required_headers.items():
            if request.headers.get(name) != expected:
                raise HTTPException(status_code=401, detail=f"Required request header missing or invalid: {name}")
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            raw = await request.body()
            if raw:
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    body = raw.decode("utf-8", errors="replace")
        _require_request_values(projection, path_params, query, body)
        delay = _request_delay_seconds(projection)
        if delay:
            await asyncio.sleep(delay)
        response = _response(projection, request.method.upper(), path_params, query, body)
        status_code = response.status_code
        return response
    except HTTPException as exc:
        status_code = exc.status_code
        if projection.error_mode == "default":
            raise
        return _error_response(projection, path_params, query, body, exc)
    finally:
        projection.record_request(status_code, (time.perf_counter() - started) * 1000.0)


@router.api_route("", methods=sorted(_ALLOWED_METHODS))
async def simulated_api_root(request: Request) -> Response:
    return await _dispatch(request, "/")


@router.api_route("/{request_path:path}", methods=sorted(_ALLOWED_METHODS))
async def simulated_api(request: Request, request_path: str) -> Response:
    return await _dispatch(request, "/" + request_path)
