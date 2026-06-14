import csv
import io
import json
import os
import random
import re
import shutil
import sqlite3
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, Response, jsonify, request, send_file, stream_with_context
from flask_cors import CORS

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"
DB_PATH = DATA_DIR / "studio.db"

DATA_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
CORS(app)
DB_LOCK = threading.RLock()

HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def as_json(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def execute(sql: str, params: Tuple = ()) -> None:
    with DB_LOCK, db() as conn:
        conn.execute(sql, params)
        conn.commit()


def query_one(sql: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
    with DB_LOCK, db() as conn:
        return conn.execute(sql, params).fetchone()


def query_all(sql: str, params: Tuple = ()) -> List[sqlite3.Row]:
    with DB_LOCK, db() as conn:
        return conn.execute(sql, params).fetchall()


def init_db() -> None:
    with DB_LOCK, db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                is_active INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS endpoints (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                description TEXT,
                tags TEXT,
                enabled INTEGER DEFAULT 1,
                mode TEXT DEFAULT 'static',
                status_code INTEGER DEFAULT 200,
                latency_ms INTEGER DEFAULT 0,
                failure_rate REAL DEFAULT 0,
                store_name TEXT,
                request_schema TEXT,
                response_template TEXT,
                error_template TEXT,
                rules TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS datastores (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                schema_json TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(project_id, name)
            );
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                store_name TEXT NOT NULL,
                record_id TEXT NOT NULL,
                data_json TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(project_id, store_name, record_id)
            );
            CREATE TABLE IF NOT EXISTS api_logs (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                endpoint_id TEXT,
                method TEXT,
                path TEXT,
                status_code INTEGER,
                request_json TEXT,
                response_json TEXT,
                error TEXT,
                duration_ms INTEGER,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                type TEXT,
                message TEXT,
                data_json TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sequences (
                name TEXT PRIMARY KEY,
                value INTEGER DEFAULT 0
            );
            """
        )
        conn.commit()
    if not query_one("SELECT id FROM projects LIMIT 1"):
        seed_default_project()


def active_project_id() -> Optional[str]:
    row = query_one("SELECT id FROM projects WHERE is_active=1 LIMIT 1")
    if row:
        return row["id"]
    row = query_one("SELECT id FROM projects ORDER BY created_at LIMIT 1")
    return row["id"] if row else None


def set_active_project(project_id: str) -> None:
    with DB_LOCK, db() as conn:
        conn.execute("UPDATE projects SET is_active=0")
        conn.execute("UPDATE projects SET is_active=1 WHERE id=?", (project_id,))
        conn.commit()


def next_sequence(name: str, width: int = 6) -> str:
    with DB_LOCK, db() as conn:
        row = conn.execute("SELECT value FROM sequences WHERE name=?", (name,)).fetchone()
        if not row:
            value = 1
            conn.execute("INSERT INTO sequences(name, value) VALUES(?, ?)", (name, value))
        else:
            value = int(row["value"]) + 1
            conn.execute("UPDATE sequences SET value=? WHERE name=?", (value, name))
        conn.commit()
    return str(value).zfill(width)


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path


def endpoint_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "method": row["method"],
        "path": row["path"],
        "description": row["description"] or "",
        "tags": as_json(row["tags"], []),
        "enabled": bool(row["enabled"]),
        "mode": row["mode"],
        "status_code": row["status_code"],
        "latency_ms": row["latency_ms"],
        "failure_rate": row["failure_rate"],
        "store_name": row["store_name"] or "",
        "request_schema": as_json(row["request_schema"], {"fields": []}),
        "response_template": as_json(row["response_template"], {}),
        "error_template": as_json(row["error_template"], {}),
        "rules": as_json(row["rules"], []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def datastore_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "description": row["description"] or "",
        "schema": as_json(row["schema_json"], {"fields": []}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_dotted(data: Any, key: str, default: Any = "") -> Any:
    if key in ("", None):
        return default
    current = data
    for part in str(key).split("."):
        if isinstance(current, dict):
            current = current.get(part, default)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except Exception:
                return default
        else:
            return default
    return current


def set_dotted(data: Dict[str, Any], key: str, value: Any) -> None:
    parts = str(key).split(".")
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def parse_body() -> Any:
    if request.data:
        try:
            return request.get_json(force=True, silent=False)
        except Exception:
            return request.data.decode("utf-8", errors="replace")
    return {}


def coerce_type(value: Any, field_type: str) -> Any:
    if value is None:
        return None
    field_type = (field_type or "text").lower()
    if field_type in ("number", "int", "integer"):
        return int(value)
    if field_type in ("decimal", "float"):
        return float(value)
    if field_type in ("bool", "boolean"):
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("1", "true", "yes", "y", "on")
    if field_type == "array" and not isinstance(value, list):
        return [value]
    if field_type == "object" and not isinstance(value, dict):
        raise ValueError("Expected object")
    return value


def validate_request_schema(schema: Dict[str, Any], body: Any, query_params: Dict[str, Any], headers: Dict[str, Any], path_params: Dict[str, Any]) -> Tuple[bool, List[str], Any]:
    errors: List[str] = []
    normalized = dict(body) if isinstance(body, dict) else body
    fields = schema.get("fields", []) if isinstance(schema, dict) else []
    if not fields:
        return True, [], normalized

    source_map = {
        "body": normalized if isinstance(normalized, dict) else {},
        "query": query_params,
        "headers": headers,
        "path": path_params,
    }

    for field in fields:
        name = field.get("name")
        if not name:
            continue
        source = field.get("source", "body")
        container = source_map.get(source, source_map["body"])
        value = get_dotted(container, name, None)
        if value in (None, "") and "default" in field:
            value = field.get("default")
            if source == "body" and isinstance(normalized, dict):
                set_dotted(normalized, name, value)
        if field.get("required") and value in (None, ""):
            errors.append(f"Missing required {source} field: {name}")
            continue
        if value not in (None, ""):
            try:
                value = coerce_type(value, field.get("type", "text"))
                if source == "body" and isinstance(normalized, dict):
                    set_dotted(normalized, name, value)
            except Exception as exc:
                errors.append(f"Invalid type for {source}.{name}: {exc}")
            enum_values = field.get("enum") or []
            if enum_values and value not in enum_values:
                errors.append(f"Invalid value for {source}.{name}: {value}. Allowed: {enum_values}")
    return len(errors) == 0, errors, normalized


TOKEN_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def render_token(token: str, ctx: Dict[str, Any]) -> Any:
    token = token.strip()
    if token == "now":
        return now_iso()
    if token == "uuid":
        return str(uuid.uuid4())
    if token.startswith("seq:"):
        parts = token.split(":")
        name = parts[1] if len(parts) > 1 else "SEQ"
        width = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 6
        return next_sequence(name, width)
    if token.startswith("random_int:"):
        parts = token.split(":")
        low = int(parts[1]) if len(parts) > 1 else 0
        high = int(parts[2]) if len(parts) > 2 else 100
        return random.randint(low, high)
    if token.startswith("random_choice:"):
        choices = token.split(":", 1)[1].split("|")
        return random.choice(choices)
    if token.startswith("calc:"):
        expr = token[5:]
        return safe_formula(expr, ctx)
    return get_dotted(ctx, token, "")


def render_template(value: Any, ctx: Dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: render_template(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [render_template(v, ctx) for v in value]
    if isinstance(value, str):
        matches = list(TOKEN_PATTERN.finditer(value))
        if len(matches) == 1 and matches[0].span() == (0, len(value)):
            return render_token(matches[0].group(1), ctx)
        def repl(match: re.Match) -> str:
            return str(render_token(match.group(1), ctx))
        return TOKEN_PATTERN.sub(repl, value)
    return value


def safe_formula(expr: str, ctx: Dict[str, Any]) -> Any:
    safe_names: Dict[str, Any] = {
        "min": min,
        "max": max,
        "round": round,
        "abs": abs,
        "int": int,
        "float": float,
        "len": len,
        "sum": sum,
    }
    flat = flatten_context(ctx)
    safe_names.update(flat)
    try:
        return eval(expr, {"__builtins__": {}}, safe_names)
    except Exception:
        return None


def flatten_context(ctx: Dict[str, Any]) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                clean = re.sub(r"\W+", "_", str(k))
                walk(f"{prefix}_{clean}" if prefix else clean, v)
        else:
            flat[prefix] = value
    walk("", ctx)
    return flat


def parse_path_pattern(pattern: str, actual_path: str) -> Optional[Dict[str, str]]:
    pattern = normalize_path(pattern)
    actual_path = normalize_path(actual_path)
    var_names = re.findall(r"\{([^/{}]+)\}", pattern)
    escaped = re.escape(pattern)
    for name in var_names:
        escaped = escaped.replace(re.escape("{" + name + "}"), f"(?P<{name}>[^/]+)")
    regex = "^" + escaped + "$"
    match = re.match(regex, actual_path)
    if not match:
        return None
    return match.groupdict()


def find_endpoint(method: str, path: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, str]]:
    project_id = active_project_id()
    if not project_id:
        return None, {}
    rows = query_all(
        "SELECT * FROM endpoints WHERE project_id=? AND enabled=1 AND upper(method)=? ORDER BY length(path) DESC",
        (project_id, method.upper()),
    )
    for row in rows:
        params = parse_path_pattern(row["path"], path)
        if params is not None:
            return endpoint_to_dict(row), params
    return None, {}


def insert_record(project_id: str, store_name: str, data: Dict[str, Any], record_id: Optional[str] = None) -> Dict[str, Any]:
    record_id = str(record_id or data.get("id") or data.get("recordId") or new_id(store_name.lower()))
    data = dict(data)
    data.setdefault("id", record_id)
    ts = now_iso()
    with DB_LOCK, db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO records(id, project_id, store_name, record_id, data_json, created_at, updated_at) VALUES(?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM records WHERE project_id=? AND store_name=? AND record_id=?), ?), ?)",
            (new_id("rec"), project_id, store_name, record_id, to_json(data), project_id, store_name, record_id, ts, ts),
        )
        conn.commit()
    return data


def get_records(project_id: str, store_name: str) -> List[Dict[str, Any]]:
    rows = query_all(
        "SELECT * FROM records WHERE project_id=? AND store_name=? ORDER BY created_at DESC",
        (project_id, store_name),
    )
    return [as_json(r["data_json"], {}) for r in rows]


def get_record(project_id: str, store_name: str, record_id: str) -> Optional[Dict[str, Any]]:
    row = query_one(
        "SELECT * FROM records WHERE project_id=? AND store_name=? AND record_id=?",
        (project_id, store_name, record_id),
    )
    return as_json(row["data_json"], {}) if row else None


def update_record(project_id: str, store_name: str, record_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_record(project_id, store_name, record_id)
    if not existing:
        return None
    existing.update(patch)
    insert_record(project_id, store_name, existing, record_id=record_id)
    return existing


def log_event(project_id: Optional[str], event_type: str, message: str, data: Any = None) -> None:
    execute(
        "INSERT INTO events(id, project_id, type, message, data_json, created_at) VALUES(?, ?, ?, ?, ?, ?)",
        (new_id("evt"), project_id, event_type, message, to_json(data or {}), now_iso()),
    )


def log_call(project_id: Optional[str], endpoint_id: Optional[str], method: str, path: str, status_code: int, request_json: Any, response_json: Any, error: str, duration_ms: int) -> None:
    execute(
        "INSERT INTO api_logs(id, project_id, endpoint_id, method, path, status_code, request_json, response_json, error, duration_ms, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (new_id("log"), project_id, endpoint_id, method, path, status_code, to_json(request_json), to_json(response_json), error, duration_ms, now_iso()),
    )


def evaluate_condition(condition: str, ctx: Dict[str, Any]) -> bool:
    if not condition:
        return True
    condition = condition.strip()
    # Supports examples: body.healthScore < 60, healthScore < 60, path.assetId == EAF_01
    match = re.match(r"^([A-Za-z0-9_.-]+)\s*(<=|>=|==|!=|<|>|contains)\s*(.+)$", condition)
    if not match:
        return False
    left_key, op, right_raw = match.groups()
    if "." not in left_key:
        left = get_dotted(ctx.get("body", {}), left_key, get_dotted(ctx, left_key, None))
    else:
        left = get_dotted(ctx, left_key, None)
    right_raw = right_raw.strip().strip('"').strip("'")
    if right_raw.startswith("{{") and right_raw.endswith("}}"):
        right = render_template(right_raw, ctx)
    else:
        try:
            right = json.loads(right_raw)
        except Exception:
            right = right_raw
    try:
        if isinstance(left, (int, float)) or isinstance(right, (int, float)):
            left_cmp = float(left)
            right_cmp = float(right)
        else:
            left_cmp = str(left)
            right_cmp = str(right)
        if op == "<":
            return left_cmp < right_cmp
        if op == "<=":
            return left_cmp <= right_cmp
        if op == ">":
            return left_cmp > right_cmp
        if op == ">=":
            return left_cmp >= right_cmp
        if op == "==":
            return left_cmp == right_cmp
        if op == "!=":
            return left_cmp != right_cmp
        if op == "contains":
            return str(right_cmp) in str(left_cmp)
    except Exception:
        return False
    return False


def run_rules(endpoint: Dict[str, Any], ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    project_id = endpoint["project_id"]
    for rule in endpoint.get("rules", []) or []:
        if rule.get("enabled", True) is False:
            continue
        name = rule.get("name", "Unnamed rule")
        condition = rule.get("condition", "")
        if not evaluate_condition(condition, ctx):
            continue
        actions = rule.get("actions", [])
        action_results: List[Dict[str, Any]] = []
        for action in actions:
            action_type = action.get("type")
            if action_type == "create_record":
                store = action.get("store")
                data = render_template(action.get("data", {}), ctx)
                if store and isinstance(data, dict):
                    rec = insert_record(project_id, store, data, data.get("id") or data.get("recordId"))
                    action_results.append({"type": action_type, "store": store, "record": rec})
            elif action_type == "update_record":
                store = action.get("store")
                record_id = render_template(action.get("record_id", ""), ctx)
                data = render_template(action.get("data", {}), ctx)
                if store and record_id and isinstance(data, dict):
                    rec = update_record(project_id, store, str(record_id), data)
                    action_results.append({"type": action_type, "store": store, "record": rec})
            elif action_type == "emit_event":
                event_type = render_template(action.get("event_type", "integration"), ctx)
                message = render_template(action.get("message", name), ctx)
                data = render_template(action.get("data", {}), ctx)
                log_event(project_id, str(event_type), str(message), data)
                action_results.append({"type": action_type, "event_type": event_type, "message": message})
            elif action_type == "call_internal_api":
                method = action.get("method", "POST")
                path = render_template(action.get("path", ""), ctx)
                body = render_template(action.get("body", {}), ctx)
                result = dispatch_internal(method, path, body)
                action_results.append({"type": action_type, "path": path, "result": result})
        results.append({"rule": name, "actions": action_results})
    return results


def dispatch_internal(method: str, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    endpoint, path_params = find_endpoint(method, path)
    if not endpoint:
        return {"ok": False, "error": f"No endpoint matched {method} {path}"}
    ctx = {
        "body": body,
        "query": {},
        "headers": {},
        "path": path_params,
        "now": now_iso(),
    }
    response, status = execute_endpoint(endpoint, ctx, body, path_params)
    return {"ok": status < 400, "status_code": status, "response": response}


def execute_endpoint(endpoint: Dict[str, Any], ctx: Dict[str, Any], body: Any, path_params: Dict[str, str]) -> Tuple[Any, int]:
    mode = endpoint.get("mode", "static")
    project_id = endpoint["project_id"]
    store_name = endpoint.get("store_name") or ""
    status_code = int(endpoint.get("status_code") or 200)

    if endpoint.get("latency_ms", 0):
        time.sleep(max(0, int(endpoint["latency_ms"])) / 1000.0)
    if endpoint.get("failure_rate") and random.random() < float(endpoint["failure_rate"]):
        error_response = endpoint.get("error_template") or {"success": False, "message": "Simulated failure"}
        return render_template(error_response, ctx), 500

    response: Any
    if mode == "echo_transform":
        template = endpoint.get("response_template") or {"success": True, "received": "{{body}}", "timestamp": "{{now}}"}
        response = render_template(template, ctx)
    elif mode == "crud":
        method = endpoint["method"].upper()
        record_id = path_params.get("id") or path_params.get("recordId") or path_params.get("notificationId") or path_params.get("workOrderId")
        if not store_name:
            response = {"success": False, "message": "CRUD endpoint needs store_name"}
            return response, 500
        if method == "GET" and record_id:
            record = get_record(project_id, store_name, record_id)
            if not record:
                return {"success": False, "message": f"Record not found: {record_id}"}, 404
            ctx["record"] = record
            response = render_template(endpoint.get("response_template") or {"success": True, "data": "{{record}}"}, ctx)
        elif method == "GET":
            records = get_records(project_id, store_name)
            ctx["records"] = records
            response = render_template(endpoint.get("response_template") or {"success": True, "count": len(records), "data": records}, ctx)
        elif method == "POST":
            data = body if isinstance(body, dict) else {"value": body}
            template = endpoint.get("response_template") or {}
            if template:
                rendered = render_template(template, ctx)
                if isinstance(rendered, dict) and "data" in rendered and isinstance(rendered["data"], dict):
                    data = rendered["data"]
            record_id = data.get("id") or data.get("recordId") or path_params.get("id")
            record = insert_record(project_id, store_name, data, record_id)
            ctx["record"] = record
            response = render_template(endpoint.get("response_template") or {"success": True, "data": record}, ctx)
        elif method in ("PATCH", "PUT"):
            if not record_id:
                return {"success": False, "message": "Update endpoint needs path parameter {id}"}, 400
            patch = body if isinstance(body, dict) else {"value": body}
            record = update_record(project_id, store_name, record_id, patch)
            if not record:
                return {"success": False, "message": f"Record not found: {record_id}"}, 404
            ctx["record"] = record
            response = render_template(endpoint.get("response_template") or {"success": True, "data": record}, ctx)
        elif method == "DELETE":
            if not record_id:
                return {"success": False, "message": "Delete endpoint needs path parameter {id}"}, 400
            execute("DELETE FROM records WHERE project_id=? AND store_name=? AND record_id=?", (project_id, store_name, record_id))
            response = render_template(endpoint.get("response_template") or {"success": True, "deletedId": record_id}, ctx)
        else:
            response = {"success": False, "message": f"Unsupported CRUD method: {method}"}
            return response, 405
    elif mode == "rule_based":
        if store_name and isinstance(body, dict):
            rec = insert_record(project_id, store_name, body)
            ctx["record"] = rec
        rule_results = run_rules(endpoint, ctx)
        ctx["ruleResults"] = rule_results
        response = render_template(endpoint.get("response_template") or {"success": True, "rules": rule_results}, ctx)
    else:
        response = render_template(endpoint.get("response_template") or {"success": True, "message": "OK", "timestamp": "{{now}}"}, ctx)

    if mode != "rule_based":
        rule_results = run_rules(endpoint, ctx)
        if isinstance(response, dict) and rule_results:
            response.setdefault("ruleResults", rule_results)
    return response, status_code


def handle_dynamic_request() -> Response:
    start = time.time()
    endpoint = None
    status = 404
    response_body: Any = {"success": False, "message": "No configured endpoint matched this method and path"}
    error = ""
    body = parse_body()
    try:
        endpoint, path_params = find_endpoint(request.method, request.path)
        if not endpoint:
            log_call(active_project_id(), None, request.method, request.path, 404, body, response_body, "not_found", int((time.time() - start) * 1000))
            return jsonify(response_body), 404
        query_params = {k: v for k, v in request.args.items()}
        headers = {k: v for k, v in request.headers.items()}
        ok, errors, normalized_body = validate_request_schema(endpoint.get("request_schema", {}), body, query_params, headers, path_params)
        if not ok:
            response_body = {"success": False, "message": "Request validation failed", "errors": errors}
            status = 400
        else:
            ctx = {
                "body": normalized_body,
                "query": query_params,
                "headers": headers,
                "path": path_params,
                "now": now_iso(),
            }
            response_body, status = execute_endpoint(endpoint, ctx, normalized_body, path_params)
        return jsonify(response_body), status
    except Exception as exc:
        error = str(exc)
        response_body = {"success": False, "message": "Simulator runtime error", "error": error}
        status = 500
        return jsonify(response_body), status
    finally:
        duration_ms = int((time.time() - start) * 1000)
        project_id = endpoint["project_id"] if endpoint else active_project_id()
        endpoint_id = endpoint["id"] if endpoint else None
        log_call(project_id, endpoint_id, request.method, request.path, status, body, response_body, error, duration_ms)
        if endpoint and status < 500:
            log_event(project_id, "api_call", f"{request.method} {request.path} -> {status}", {"endpoint": endpoint.get("name"), "status": status})


@app.route("/")
def index() -> Response:
    return Response(INDEX_HTML, mimetype="text/html")


@app.route("/api/studio/health")
def studio_health() -> Response:
    return jsonify({"success": True, "name": "API Simulator Studio", "time": now_iso(), "active_project_id": active_project_id()})


@app.route("/api/studio/projects", methods=["GET", "POST"])
def projects() -> Response:
    if request.method == "GET":
        rows = query_all("SELECT * FROM projects ORDER BY created_at DESC")
        return jsonify({"success": True, "data": [dict(r) for r in rows]})
    data = request.get_json(force=True)
    project_id = data.get("id") or new_id("proj")
    ts = now_iso()
    execute(
        "INSERT INTO projects(id, name, description, is_active, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?)",
        (project_id, data.get("name", "New Project"), data.get("description", ""), int(data.get("is_active", 0)), ts, ts),
    )
    if data.get("is_active"):
        set_active_project(project_id)
    return jsonify({"success": True, "id": project_id})


@app.route("/api/studio/projects/<project_id>/activate", methods=["POST"])
def activate_project(project_id: str) -> Response:
    set_active_project(project_id)
    return jsonify({"success": True, "active_project_id": project_id})


@app.route("/api/studio/endpoints", methods=["GET", "POST"])
def endpoints_collection() -> Response:
    project_id = request.args.get("project_id") or active_project_id()
    if request.method == "GET":
        rows = query_all("SELECT * FROM endpoints WHERE project_id=? ORDER BY updated_at DESC", (project_id,))
        return jsonify({"success": True, "data": [endpoint_to_dict(r) for r in rows]})
    data = request.get_json(force=True)
    endpoint_id = data.get("id") or new_id("ep")
    ts = now_iso()
    execute(
        """
        INSERT OR REPLACE INTO endpoints(id, project_id, name, method, path, description, tags, enabled, mode, status_code, latency_ms, failure_rate, store_name, request_schema, response_template, error_template, rules, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM endpoints WHERE id=?), ?), ?)
        """,
        (
            endpoint_id,
            data.get("project_id") or project_id,
            data.get("name", "New API"),
            data.get("method", "GET").upper(),
            normalize_path(data.get("path", "/api/v1/new")),
            data.get("description", ""),
            to_json(data.get("tags", [])),
            int(bool(data.get("enabled", True))),
            data.get("mode", "static"),
            int(data.get("status_code", 200)),
            int(data.get("latency_ms", 0)),
            float(data.get("failure_rate", 0)),
            data.get("store_name", ""),
            to_json(data.get("request_schema", {"fields": []})),
            to_json(data.get("response_template", {})),
            to_json(data.get("error_template", {})),
            to_json(data.get("rules", [])),
            endpoint_id,
            ts,
            ts,
        ),
    )
    return jsonify({"success": True, "id": endpoint_id})


@app.route("/api/studio/endpoints/<endpoint_id>", methods=["GET", "DELETE"])
def endpoint_item(endpoint_id: str) -> Response:
    row = query_one("SELECT * FROM endpoints WHERE id=?", (endpoint_id,))
    if not row:
        return jsonify({"success": False, "message": "Endpoint not found"}), 404
    if request.method == "GET":
        return jsonify({"success": True, "data": endpoint_to_dict(row)})
    execute("DELETE FROM endpoints WHERE id=?", (endpoint_id,))
    return jsonify({"success": True})


@app.route("/api/studio/datastores", methods=["GET", "POST"])
def datastores_collection() -> Response:
    project_id = request.args.get("project_id") or active_project_id()
    if request.method == "GET":
        rows = query_all("SELECT * FROM datastores WHERE project_id=? ORDER BY name", (project_id,))
        return jsonify({"success": True, "data": [datastore_to_dict(r) for r in rows]})
    data = request.get_json(force=True)
    store_id = data.get("id") or new_id("store")
    ts = now_iso()
    execute(
        "INSERT OR REPLACE INTO datastores(id, project_id, name, description, schema_json, created_at, updated_at) VALUES(?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM datastores WHERE id=?), ?), ?)",
        (store_id, data.get("project_id") or project_id, data.get("name"), data.get("description", ""), to_json(data.get("schema", {"fields": []})), store_id, ts, ts),
    )
    return jsonify({"success": True, "id": store_id})


@app.route("/api/studio/datastores/<store_name>/records", methods=["GET", "POST", "DELETE"])
def datastore_records(store_name: str) -> Response:
    project_id = request.args.get("project_id") or active_project_id()
    if request.method == "GET":
        return jsonify({"success": True, "data": get_records(project_id, store_name)})
    if request.method == "DELETE":
        execute("DELETE FROM records WHERE project_id=? AND store_name=?", (project_id, store_name))
        return jsonify({"success": True})
    data = request.get_json(force=True)
    if isinstance(data, list):
        saved = [insert_record(project_id, store_name, item if isinstance(item, dict) else {"value": item}) for item in data]
    else:
        saved = insert_record(project_id, store_name, data if isinstance(data, dict) else {"value": data})
    return jsonify({"success": True, "data": saved})


@app.route("/api/studio/logs")
def logs() -> Response:
    project_id = request.args.get("project_id") or active_project_id()
    rows = query_all("SELECT * FROM api_logs WHERE project_id=? ORDER BY created_at DESC LIMIT 300", (project_id,))
    data = []
    for r in rows:
        item = dict(r)
        item["request_json"] = as_json(item.get("request_json"), {})
        item["response_json"] = as_json(item.get("response_json"), {})
        data.append(item)
    return jsonify({"success": True, "data": data})


@app.route("/api/studio/events")
def events_collection() -> Response:
    project_id = request.args.get("project_id") or active_project_id()
    rows = query_all("SELECT * FROM events WHERE project_id=? ORDER BY created_at DESC LIMIT 300", (project_id,))
    data = []
    for r in rows:
        item = dict(r)
        item["data"] = as_json(item.pop("data_json"), {})
        data.append(item)
    return jsonify({"success": True, "data": data})


@app.route("/api/studio/stream/events")
def stream_events() -> Response:
    project_id = request.args.get("project_id") or active_project_id()

    def generate():
        last_seen = ""
        while True:
            rows = query_all("SELECT * FROM events WHERE project_id=? ORDER BY created_at DESC LIMIT 10", (project_id,))
            fresh = []
            for row in rows:
                if row["id"] == last_seen:
                    break
                fresh.append(row)
            if rows:
                last_seen = rows[0]["id"]
            for row in reversed(fresh):
                payload = dict(row)
                payload["data"] = as_json(payload.pop("data_json"), {})
                yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(1)

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/v1/stream/events")
def public_stream_events() -> Response:
    return stream_events()


@app.route("/api/v1/stream/tags")
def public_stream_tags() -> Response:
    project_id = active_project_id()
    assets = get_records(project_id, "Assets") if project_id else []
    if not assets:
        assets = [{"assetCode": "EAF_01"}, {"assetCode": "LRF_01"}, {"assetCode": "VD_01"}, {"assetCode": "CCM_01"}]

    def generate():
        tags = ["temperature", "power", "vibration", "healthScore", "runtimeMinutes"]
        while True:
            asset = random.choice(assets)
            asset_code = asset.get("assetCode") or asset.get("id") or "ASSET_01"
            tag = random.choice(tags)
            if tag == "healthScore":
                value = random.randint(45, 99)
            elif tag == "temperature":
                value = round(random.uniform(80, 1680), 2)
            elif tag == "vibration":
                value = round(random.uniform(0.8, 12.5), 2)
            elif tag == "power":
                value = round(random.uniform(2.5, 92.0), 2)
            else:
                value = random.randint(1, 3600)
            payload = {"timestamp": now_iso(), "assetCode": asset_code, "tag": tag, "value": value, "quality": "GOOD"}
            yield json.dumps(payload) + "\n"
            time.sleep(1)

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


@app.route("/api/studio/test-call", methods=["POST"])
def test_call() -> Response:
    data = request.get_json(force=True)
    method = data.get("method", "GET")
    path = normalize_path(data.get("path", "/"))
    body = data.get("body", {})
    result = dispatch_internal(method, path, body if isinstance(body, dict) else {"value": body})
    return jsonify({"success": True, "data": result})


@app.route("/api/studio/export/project")
def export_project() -> Response:
    project_id = request.args.get("project_id") or active_project_id()
    if not project_id:
        return jsonify({"success": False, "message": "No project selected"}), 400
    row = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not row:
        return jsonify({"success": False, "message": "Project not found"}), 404
    project = dict(row)
    endpoints = [endpoint_to_dict(r) for r in query_all("SELECT * FROM endpoints WHERE project_id=?", (project_id,))]
    stores = [datastore_to_dict(r) for r in query_all("SELECT * FROM datastores WHERE project_id=?", (project_id,))]
    records_by_store: Dict[str, List[Dict[str, Any]]] = {}
    for store in stores:
        records_by_store[store["name"]] = get_records(project_id, store["name"])
    package = {"exported_at": now_iso(), "project": project, "endpoints": endpoints, "datastores": stores, "records": records_by_store}
    out = EXPORT_DIR / f"{project['name'].lower().replace(' ', '_')}_project.json"
    out.write_text(to_json(package), encoding="utf-8")
    return send_file(out, as_attachment=True, download_name=out.name)


@app.route("/api/studio/import/project", methods=["POST"])
def import_project() -> Response:
    if "file" in request.files:
        raw = request.files["file"].read().decode("utf-8")
        package = json.loads(raw)
    else:
        package = request.get_json(force=True)
    project = package.get("project", {})
    old_project_id = project.get("id")
    project_id = new_id("proj")
    ts = now_iso()
    execute("INSERT INTO projects(id, name, description, is_active, created_at, updated_at) VALUES(?, ?, ?, 0, ?, ?)", (project_id, project.get("name", "Imported Project") + " Copy", project.get("description", ""), ts, ts))
    for ep in package.get("endpoints", []):
        ep["id"] = new_id("ep")
        ep["project_id"] = project_id
        with app.test_request_context(json=ep):
            pass
        save_endpoint_dict(ep, project_id)
    for store in package.get("datastores", []):
        store["id"] = new_id("store")
        store["project_id"] = project_id
        save_datastore_dict(store, project_id)
    for store_name, records in package.get("records", {}).items():
        for rec in records:
            insert_record(project_id, store_name, rec, rec.get("id") or rec.get("recordId"))
    return jsonify({"success": True, "old_project_id": old_project_id, "new_project_id": project_id})


def save_endpoint_dict(data: Dict[str, Any], project_id: str) -> None:
    endpoint_id = data.get("id") or new_id("ep")
    ts = now_iso()
    execute(
        """
        INSERT OR REPLACE INTO endpoints(id, project_id, name, method, path, description, tags, enabled, mode, status_code, latency_ms, failure_rate, store_name, request_schema, response_template, error_template, rules, created_at, updated_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (endpoint_id, project_id, data.get("name", "Imported API"), data.get("method", "GET"), normalize_path(data.get("path", "/")), data.get("description", ""), to_json(data.get("tags", [])), int(bool(data.get("enabled", True))), data.get("mode", "static"), int(data.get("status_code", 200)), int(data.get("latency_ms", 0)), float(data.get("failure_rate", 0)), data.get("store_name", ""), to_json(data.get("request_schema", {"fields": []})), to_json(data.get("response_template", {})), to_json(data.get("error_template", {})), to_json(data.get("rules", [])), ts, ts),
    )


def save_datastore_dict(data: Dict[str, Any], project_id: str) -> None:
    store_id = data.get("id") or new_id("store")
    ts = now_iso()
    execute("INSERT OR REPLACE INTO datastores(id, project_id, name, description, schema_json, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?)", (store_id, project_id, data.get("name"), data.get("description", ""), to_json(data.get("schema", {"fields": []})), ts, ts))


@app.route("/openapi.json")
def openapi() -> Response:
    project_id = request.args.get("project_id") or active_project_id()
    endpoints = [endpoint_to_dict(r) for r in query_all("SELECT * FROM endpoints WHERE project_id=?", (project_id,))]
    paths: Dict[str, Any] = {}
    for ep in endpoints:
        method = ep["method"].lower()
        path = re.sub(r"\{([^}]+)\}", r"{\1}", ep["path"])
        paths.setdefault(path, {})[method] = {
            "summary": ep["name"],
            "description": ep.get("description", ""),
            "tags": ep.get("tags", []),
            "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}} if method in ("post", "put", "patch") else None,
            "responses": {str(ep.get("status_code", 200)): {"description": "Configured simulator response", "content": {"application/json": {"schema": {"type": "object"}}}}},
        }
        if paths[path][method]["requestBody"] is None:
            del paths[path][method]["requestBody"]
    return jsonify({"openapi": "3.0.3", "info": {"title": "API Simulator Studio Export", "version": "1.0.0"}, "paths": paths})


@app.route("/postman_collection.json")
def postman_collection() -> Response:
    project_id = request.args.get("project_id") or active_project_id()
    endpoints = [endpoint_to_dict(r) for r in query_all("SELECT * FROM endpoints WHERE project_id=?", (project_id,))]
    items = []
    for ep in endpoints:
        raw_url = "{{baseUrl}}" + ep["path"]
        item = {
            "name": ep["name"],
            "request": {
                "method": ep["method"],
                "header": [{"key": "Content-Type", "value": "application/json"}],
                "url": {"raw": raw_url, "host": ["{{baseUrl}}"], "path": ep["path"].strip("/").split("/")},
            },
        }
        if ep["method"] in ("POST", "PUT", "PATCH"):
            sample = {f.get("name", "field"): f.get("sample", f.get("default", "")) for f in ep.get("request_schema", {}).get("fields", []) if f.get("source", "body") == "body"}
            item["request"]["body"] = {"mode": "raw", "raw": to_json(sample), "options": {"raw": {"language": "json"}}}
        items.append(item)
    return jsonify({"info": {"name": "API Simulator Studio", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"}, "item": items, "variable": [{"key": "baseUrl", "value": request.host_url.rstrip("/")}]})


@app.route("/api/v1/<path:dynamic_path>", methods=HTTP_METHODS)
def dynamic_api_v1(dynamic_path: str) -> Response:
    return handle_dynamic_request()


@app.route("/mock/<path:dynamic_path>", methods=HTTP_METHODS)
def dynamic_mock(dynamic_path: str) -> Response:
    return handle_dynamic_request()


def seed_default_project() -> None:
    project_id = "proj_steelshop_demo"
    ts = now_iso()
    execute("INSERT OR REPLACE INTO projects(id, name, description, is_active, created_at, updated_at) VALUES(?, ?, ?, 1, ?, ?)", (project_id, "ISP Steel Shop + SAP PM Demo", "Preloaded demo project for EAF, LRF, VD, CCM, historian, asset health, downtime, MES and SAP PM flows.", ts, ts))

    stores = [
        ("Assets", "Steel shop assets and equipment hierarchy", {"fields": [{"name": "assetCode", "type": "text", "required": True}, {"name": "equipmentType", "type": "enum", "enum": ["EAF", "LRF", "VD", "CCM"]}, {"name": "area", "type": "text"}, {"name": "healthScore", "type": "number"}, {"name": "status", "type": "text"}]}),
        ("TagReadings", "Incoming historian-style tag readings", {"fields": [{"name": "assetCode", "type": "text"}, {"name": "tag", "type": "text"}, {"name": "value", "type": "decimal"}, {"name": "timestamp", "type": "datetime"}]}),
        ("HealthSnapshots", "Calculated asset health records", {"fields": [{"name": "assetCode", "type": "text"}, {"name": "healthScore", "type": "number"}, {"name": "condition", "type": "text"}, {"name": "timestamp", "type": "datetime"}]}),
        ("DowntimeEvents", "Downtime records received from MES or shopfloor", {"fields": [{"name": "assetCode", "type": "text"}, {"name": "downtimeMinutes", "type": "number"}, {"name": "reason", "type": "text"}, {"name": "status", "type": "text"}]}),
        ("PMNotifications", "Mock SAP PM notifications", {"fields": [{"name": "notificationId", "type": "text"}, {"name": "assetCode", "type": "text"}, {"name": "priority", "type": "text"}, {"name": "status", "type": "text"}, {"name": "description", "type": "text"}]}),
        ("WorkOrders", "MES/SAP work orders", {"fields": [{"name": "workOrderId", "type": "text"}, {"name": "notificationId", "type": "text"}, {"name": "assetCode", "type": "text"}, {"name": "status", "type": "text"}]}),
    ]
    for name, desc, schema in stores:
        save_datastore_dict({"id": "store_" + name.lower(), "name": name, "description": desc, "schema": schema}, project_id)

    assets = [
        {"id": "EAF_01", "assetCode": "EAF_01", "equipmentType": "EAF", "area": "Steel Making Shop", "healthScore": 92, "status": "RUNNING", "description": "Electric Arc Furnace"},
        {"id": "LRF_01", "assetCode": "LRF_01", "equipmentType": "LRF", "area": "Steel Making Shop", "healthScore": 88, "status": "RUNNING", "description": "Ladle Refining Furnace"},
        {"id": "VD_01", "assetCode": "VD_01", "equipmentType": "VD", "area": "Steel Making Shop", "healthScore": 84, "status": "RUNNING", "description": "Vacuum Degassing Unit"},
        {"id": "CCM_01", "assetCode": "CCM_01", "equipmentType": "CCM", "area": "Steel Making Shop", "healthScore": 90, "status": "RUNNING", "description": "Continuous Casting Machine"},
    ]
    for asset in assets:
        insert_record(project_id, "Assets", asset, asset["assetCode"])

    endpoint_defs = [
        {
            "id": "ep_assets_list",
            "name": "List Assets",
            "method": "GET",
            "path": "/api/v1/assets",
            "mode": "crud",
            "store_name": "Assets",
            "response_template": {"success": True, "count": "{{calc:len(records)}}", "data": "{{records}}"},
            "tags": ["Assets"],
        },
        {
            "id": "ep_asset_get",
            "name": "Get Asset",
            "method": "GET",
            "path": "/api/v1/assets/{id}",
            "mode": "crud",
            "store_name": "Assets",
            "response_template": {"success": True, "data": "{{record}}"},
            "tags": ["Assets"],
        },
        {
            "id": "ep_historian_tags",
            "name": "Receive Historian Tag Reading",
            "method": "POST",
            "path": "/api/v1/historian/tags",
            "mode": "rule_based",
            "store_name": "TagReadings",
            "request_schema": {"fields": [{"name": "assetCode", "type": "text", "required": True}, {"name": "tag", "type": "text", "required": True}, {"name": "value", "type": "decimal", "required": True}, {"name": "timestamp", "type": "datetime", "default": "{{now}}"}]},
            "response_template": {"success": True, "message": "Tag accepted", "readingId": "{{record.id}}", "assetCode": "{{body.assetCode}}", "tag": "{{body.tag}}", "value": "{{body.value}}"},
            "rules": [{"name": "Emit tag received event", "condition": "", "actions": [{"type": "emit_event", "event_type": "historian_tag", "message": "Tag {{body.tag}} received for {{body.assetCode}}", "data": {"assetCode": "{{body.assetCode}}", "tag": "{{body.tag}}", "value": "{{body.value}}"}}]}],
            "tags": ["Historian"],
        },
        {
            "id": "ep_health_snapshot",
            "name": "Submit Asset Health Snapshot",
            "method": "POST",
            "path": "/api/v1/asset-health/snapshots",
            "mode": "rule_based",
            "store_name": "HealthSnapshots",
            "request_schema": {"fields": [{"name": "assetCode", "type": "text", "required": True}, {"name": "healthScore", "type": "number", "required": True}, {"name": "condition", "type": "text", "default": "AUTO"}]},
            "response_template": {"success": True, "message": "Health snapshot accepted", "assetCode": "{{body.assetCode}}", "healthScore": "{{body.healthScore}}", "status": "PROCESSED"},
            "rules": [
                {"name": "Create PM notification when health is low", "condition": "body.healthScore < 60", "actions": [
                    {"type": "create_record", "store": "PMNotifications", "data": {"id": "PM-{{seq:PM:6}}", "notificationId": "PM-{{seq:PMDISPLAY:6}}", "assetCode": "{{body.assetCode}}", "priority": "HIGH", "status": "CREATED", "source": "ASSET_HEALTH", "description": "Automatic PM notification because health score is {{body.healthScore}}", "createdAt": "{{now}}"}},
                    {"type": "emit_event", "event_type": "sap_pm_notification", "message": "PM notification created for {{body.assetCode}} due to low health", "data": {"assetCode": "{{body.assetCode}}", "healthScore": "{{body.healthScore}}", "source": "ASSET_HEALTH"}}
                ]}
            ],
            "tags": ["Asset Health", "SAP PM"],
        },
        {
            "id": "ep_downtime_create",
            "name": "Create Downtime Event",
            "method": "POST",
            "path": "/api/v1/downtime/events",
            "mode": "rule_based",
            "store_name": "DowntimeEvents",
            "request_schema": {"fields": [{"name": "assetCode", "type": "text", "required": True}, {"name": "downtimeMinutes", "type": "number", "required": True}, {"name": "reason", "type": "text", "default": "UNSPECIFIED"}]},
            "response_template": {"success": True, "message": "Downtime event logged", "assetCode": "{{body.assetCode}}", "downtimeMinutes": "{{body.downtimeMinutes}}"},
            "rules": [
                {"name": "Create PM notification for major downtime", "condition": "body.downtimeMinutes > 10", "actions": [
                    {"type": "create_record", "store": "PMNotifications", "data": {"id": "PM-DT-{{seq:PMDT:6}}", "notificationId": "PM-DT-{{seq:PMDTDISPLAY:6}}", "assetCode": "{{body.assetCode}}", "priority": "MEDIUM", "status": "CREATED", "source": "DOWNTIME", "description": "Downtime {{body.downtimeMinutes}} minutes. Reason: {{body.reason}}", "createdAt": "{{now}}"}},
                    {"type": "emit_event", "event_type": "downtime_pm_notification", "message": "PM notification created for downtime on {{body.assetCode}}", "data": {"assetCode": "{{body.assetCode}}", "downtimeMinutes": "{{body.downtimeMinutes}}"}}
                ]}
            ],
            "tags": ["Downtime", "SAP PM"],
        },
        {
            "id": "ep_pm_create",
            "name": "Create SAP PM Notification",
            "method": "POST",
            "path": "/api/v1/sap/pm/notifications",
            "mode": "crud",
            "store_name": "PMNotifications",
            "request_schema": {"fields": [{"name": "assetCode", "type": "text", "required": True}, {"name": "priority", "type": "text", "default": "MEDIUM"}, {"name": "description", "type": "text", "required": True}]},
            "response_template": {"success": True, "message": "SAP PM notification created", "data": {"id": "PM-{{seq:PMMANUAL:6}}", "notificationId": "PM-{{seq:PMMANUALDISPLAY:6}}", "assetCode": "{{body.assetCode}}", "priority": "{{body.priority}}", "description": "{{body.description}}", "status": "CREATED", "source": "API", "createdAt": "{{now}}"}},
            "rules": [{"name": "Emit PM notification created", "condition": "", "actions": [{"type": "emit_event", "event_type": "sap_pm_notification", "message": "SAP PM notification API called for {{body.assetCode}}", "data": {"assetCode": "{{body.assetCode}}", "priority": "{{body.priority}}"}}]}],
            "tags": ["SAP PM"],
        },
        {
            "id": "ep_pm_list",
            "name": "List SAP PM Notifications",
            "method": "GET",
            "path": "/api/v1/sap/pm/notifications",
            "mode": "crud",
            "store_name": "PMNotifications",
            "response_template": {"success": True, "data": "{{records}}"},
            "tags": ["SAP PM"],
        },
        {
            "id": "ep_pm_get",
            "name": "Get SAP PM Notification",
            "method": "GET",
            "path": "/api/v1/sap/pm/notifications/{id}",
            "mode": "crud",
            "store_name": "PMNotifications",
            "response_template": {"success": True, "data": "{{record}}"},
            "tags": ["SAP PM"],
        },
        {
            "id": "ep_workorder_create",
            "name": "Create MES Work Order",
            "method": "POST",
            "path": "/api/v1/mes/workorders",
            "mode": "crud",
            "store_name": "WorkOrders",
            "request_schema": {"fields": [{"name": "assetCode", "type": "text", "required": True}, {"name": "notificationId", "type": "text"}, {"name": "operation", "type": "text", "default": "Inspection"}]},
            "response_template": {"success": True, "message": "MES work order created", "data": {"id": "WO-{{seq:WO:6}}", "workOrderId": "WO-{{seq:WODISPLAY:6}}", "assetCode": "{{body.assetCode}}", "notificationId": "{{body.notificationId}}", "operation": "{{body.operation}}", "status": "OPEN", "createdAt": "{{now}}"}},
            "tags": ["MES"],
        },
    ]
    for ep in endpoint_defs:
        ep.setdefault("project_id", project_id)
        ep.setdefault("description", "")
        ep.setdefault("enabled", True)
        ep.setdefault("status_code", 200)
        ep.setdefault("latency_ms", 0)
        ep.setdefault("failure_rate", 0)
        ep.setdefault("request_schema", {"fields": []})
        ep.setdefault("error_template", {})
        ep.setdefault("rules", [])
        save_endpoint_dict(ep, project_id)
    log_event(project_id, "system", "Default Steel Shop + SAP PM demo project seeded", {"project_id": project_id})


INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>API Simulator Studio</title>
  <style>
    :root{--bg:#09111f;--panel:#101b2d;--panel2:#152238;--border:#263852;--text:#e8eef8;--muted:#91a1b8;--accent:#59a7ff;--ok:#3bd671;--warn:#f5b84b;--bad:#ff5c7a;--code:#07101d}
    *{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#07101d,#0b1424 45%,#11192a);font-family:Segoe UI,Inter,Arial,sans-serif;color:var(--text)}
    header{display:flex;gap:18px;align-items:center;justify-content:space-between;padding:18px 24px;border-bottom:1px solid var(--border);background:rgba(9,17,31,.92);position:sticky;top:0;z-index:5;backdrop-filter:blur(10px)}
    h1{font-size:20px;margin:0}.sub{font-size:12px;color:var(--muted);margin-top:3px}.wrap{display:grid;grid-template-columns:240px 1fr;min-height:calc(100vh - 74px)}
    nav{padding:16px;border-right:1px solid var(--border);background:rgba(16,27,45,.72)}nav button{width:100%;display:block;background:transparent;border:1px solid transparent;color:var(--muted);padding:10px 12px;border-radius:10px;text-align:left;cursor:pointer;margin-bottom:6px;font-size:14px}nav button.active,nav button:hover{background:var(--panel2);border-color:var(--border);color:var(--text)}
    main{padding:20px;overflow:auto}.grid{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:14px;margin-bottom:16px}.card{background:rgba(16,27,45,.92);border:1px solid var(--border);border-radius:14px;padding:16px;box-shadow:0 12px 30px rgba(0,0,0,.18)}.metric{font-size:28px;font-weight:700}.label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.split{display:grid;grid-template-columns:360px 1fr;gap:16px}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    input,select,textarea{width:100%;background:var(--code);border:1px solid var(--border);border-radius:9px;color:var(--text);padding:9px;font:13px Consolas,monospace}textarea{min-height:150px;resize:vertical}.short{min-height:78px}.field{margin-bottom:10px}.field label{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}.btn{background:var(--accent);color:#06101e;border:none;padding:9px 12px;border-radius:9px;font-weight:700;cursor:pointer}.btn.secondary{background:var(--panel2);color:var(--text);border:1px solid var(--border)}.btn.danger{background:var(--bad);color:white}.btn.small{font-size:12px;padding:6px 8px}.pill{display:inline-flex;gap:6px;align-items:center;border:1px solid var(--border);background:var(--panel2);border-radius:999px;color:var(--muted);padding:4px 8px;font-size:12px}
    table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid var(--border);padding:8px;text-align:left;vertical-align:top}th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}.clickable{cursor:pointer}.clickable:hover{background:rgba(89,167,255,.08)}pre{white-space:pre-wrap;background:var(--code);border:1px solid var(--border);border-radius:10px;padding:12px;max-height:360px;overflow:auto}.hide{display:none}.ok{color:var(--ok)}.bad{color:var(--bad)}.muted{color:var(--muted)}a{color:var(--accent)}
    @media(max-width:1000px){.wrap{grid-template-columns:1fr}nav{display:flex;overflow:auto;border-right:none;border-bottom:1px solid var(--border)}nav button{width:auto;white-space:nowrap}.grid{grid-template-columns:1fr 1fr}.split,.two{grid-template-columns:1fr}}
  </style>
</head>
<body>
<header>
  <div><h1>API Simulator Studio</h1><div class="sub">Config-driven API builder, mock controller, stream simulator and demo integration runtime</div></div>
  <div class="row"><select id="projectSelect" style="min-width:260px"></select><button class="btn secondary" onclick="activateSelectedProject()">Activate</button><a class="pill" href="/openapi.json" target="_blank">OpenAPI</a><a class="pill" href="/postman_collection.json" target="_blank">Postman</a></div>
</header>
<div class="wrap">
<nav>
  <button class="active" onclick="showTab('dashboard',this)">Dashboard</button>
  <button onclick="showTab('apis',this)">API Builder</button>
  <button onclick="showTab('stores',this)">Data Stores</button>
  <button onclick="showTab('test',this)">Test Console</button>
  <button onclick="showTab('logs',this)">Logs</button>
  <button onclick="showTab('streams',this)">Streams</button>
  <button onclick="showTab('export',this)">Import / Export</button>
</nav>
<main>
<section id="dashboard" class="tab">
  <div class="grid">
    <div class="card"><div class="label">Endpoints</div><div class="metric" id="mEndpoints">0</div></div>
    <div class="card"><div class="label">Data Stores</div><div class="metric" id="mStores">0</div></div>
    <div class="card"><div class="label">API Calls</div><div class="metric" id="mLogs">0</div></div>
    <div class="card"><div class="label">Events</div><div class="metric" id="mEvents">0</div></div>
  </div>
  <div class="two">
    <div class="card"><h3>Recent API Calls</h3><div id="recentLogs"></div></div>
    <div class="card"><h3>Recent Events</h3><div id="recentEvents"></div></div>
  </div>
</section>
<section id="apis" class="tab hide">
  <div class="split">
    <div class="card">
      <div class="row" style="justify-content:space-between"><h3>API Catalog</h3><button class="btn small" onclick="newEndpoint()">New</button></div>
      <div id="apiList"></div>
    </div>
    <div class="card">
      <h3>Endpoint Designer</h3>
      <input type="hidden" id="epId" />
      <div class="two"><div class="field"><label>Name</label><input id="epName" /></div><div class="field"><label>Method</label><select id="epMethod"><option>GET</option><option>POST</option><option>PUT</option><option>PATCH</option><option>DELETE</option></select></div></div>
      <div class="field"><label>Path</label><input id="epPath" placeholder="/api/v1/module/resource/{id}" /></div>
      <div class="two"><div class="field"><label>Mode</label><select id="epMode"><option value="static">static</option><option value="echo_transform">echo_transform</option><option value="crud">crud</option><option value="rule_based">rule_based</option></select></div><div class="field"><label>Store Name</label><input id="epStore" placeholder="Optional data store" /></div></div>
      <div class="two"><div class="field"><label>Status Code</label><input id="epStatus" value="200" /></div><div class="field"><label>Latency MS</label><input id="epLatency" value="0" /></div></div>
      <div class="field"><label>Description</label><input id="epDesc" /></div>
      <div class="field"><label>Request Schema JSON</label><textarea id="epSchema" class="short"></textarea></div>
      <div class="field"><label>Response Template JSON</label><textarea id="epResponse"></textarea></div>
      <div class="field"><label>Rules JSON</label><textarea id="epRules" class="short"></textarea></div>
      <div class="row"><button class="btn" onclick="saveEndpoint()">Save Endpoint</button><button class="btn secondary" onclick="duplicateEndpoint()">Duplicate</button><button class="btn danger" onclick="deleteEndpoint()">Delete</button></div>
    </div>
  </div>
</section>
<section id="stores" class="tab hide">
  <div class="split">
    <div class="card"><div class="row" style="justify-content:space-between"><h3>Data Stores</h3><button class="btn small" onclick="newStore()">New</button></div><div id="storeList"></div></div>
    <div class="card"><h3>Store Designer</h3><input type="hidden" id="storeId" /><div class="field"><label>Name</label><input id="storeName" /></div><div class="field"><label>Description</label><input id="storeDesc" /></div><div class="field"><label>Schema JSON</label><textarea id="storeSchema"></textarea></div><div class="row"><button class="btn" onclick="saveStore()">Save Store</button><button class="btn secondary" onclick="loadStoreRecords()">Load Records</button><button class="btn danger" onclick="clearStoreRecords()">Clear Records</button></div><h4>Records</h4><pre id="storeRecords">[]</pre><div class="field"><label>Add Record JSON</label><textarea id="newRecord" class="short">{}</textarea></div><button class="btn secondary" onclick="addRecord()">Add Record</button></div>
  </div>
</section>
<section id="test" class="tab hide">
  <div class="card"><h3>Test Console</h3><div class="two"><div class="field"><label>Method</label><select id="testMethod"><option>GET</option><option>POST</option><option>PUT</option><option>PATCH</option><option>DELETE</option></select></div><div class="field"><label>Path</label><input id="testPath" value="/api/v1/assets" /></div></div><div class="field"><label>Request Body JSON</label><textarea id="testBody" class="short">{}</textarea></div><button class="btn" onclick="testCall()">Call API</button><h4>Response</h4><pre id="testResponse"></pre></div>
</section>
<section id="logs" class="tab hide"><div class="card"><div class="row" style="justify-content:space-between"><h3>API Logs</h3><button class="btn secondary small" onclick="loadAll()">Refresh</button></div><div id="logsTable"></div></div></section>
<section id="streams" class="tab hide"><div class="two"><div class="card"><h3>Event Stream</h3><p class="muted">SSE endpoint: <code>/api/v1/stream/events</code></p><pre id="eventStream"></pre></div><div class="card"><h3>Tag Stream</h3><p class="muted">NDJSON endpoint: <code>/api/v1/stream/tags</code></p><pre id="tagStream">Open this URL in a client to consume continuous NDJSON tag data.</pre></div></div></section>
<section id="export" class="tab hide"><div class="card"><h3>Import / Export</h3><p>Export the active project as a portable JSON package.</p><p><a class="btn" href="/api/studio/export/project">Download Project JSON</a></p><p><a class="btn secondary" href="/openapi.json">Download OpenAPI JSON</a> <a class="btn secondary" href="/postman_collection.json">Download Postman Collection</a></p><h4>Create New Project</h4><div class="two"><input id="newProjectName" placeholder="Project name" /><input id="newProjectDesc" placeholder="Description" /></div><br/><button class="btn" onclick="createProject()">Create Project</button><h4>Import Project JSON</h4><input type="file" id="importFile" /><br/><br/><button class="btn secondary" onclick="importProject()">Import</button></div></section>
</main>
</div>
<script>
let projects=[], endpoints=[], stores=[], logs=[], events=[];
function j(id){return document.getElementById(id)}
async function api(url, opts={}){const r=await fetch(url, opts); const t=await r.text(); try{return JSON.parse(t)}catch(e){return {success:false, raw:t}}}
function pretty(x){return JSON.stringify(x,null,2)}
function parseJson(id,fallback){try{return JSON.parse(j(id).value||'')}catch(e){alert('Invalid JSON in '+id+': '+e.message); throw e}}
function showTab(id,btn){document.querySelectorAll('.tab').forEach(x=>x.classList.add('hide'));j(id).classList.remove('hide');document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));btn.classList.add('active')}
async function loadAll(){
  projects=(await api('/api/studio/projects')).data||[]; endpoints=(await api('/api/studio/endpoints')).data||[]; stores=(await api('/api/studio/datastores')).data||[]; logs=(await api('/api/studio/logs')).data||[]; events=(await api('/api/studio/events')).data||[];
  renderProjects(); renderDashboard(); renderApiList(); renderStoreList(); renderLogs();
}
function renderProjects(){j('projectSelect').innerHTML=projects.map(p=>`<option value="${p.id}" ${p.is_active?'selected':''}>${p.name}${p.is_active?' (active)':''}</option>`).join('')}
async function activateSelectedProject(){await api('/api/studio/projects/'+j('projectSelect').value+'/activate',{method:'POST'}); await loadAll()}
function renderDashboard(){j('mEndpoints').textContent=endpoints.length;j('mStores').textContent=stores.length;j('mLogs').textContent=logs.length;j('mEvents').textContent=events.length;j('recentLogs').innerHTML=table(logs.slice(0,8),['method','path','status_code','duration_ms','created_at']);j('recentEvents').innerHTML=table(events.slice(0,8),['type','message','created_at'])}
function table(rows,cols){if(!rows.length)return '<p class="muted">No data yet.</p>';return '<table><thead><tr>'+cols.map(c=>'<th>'+c+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+cols.map(c=>'<td>'+escapeHtml(String(r[c]??''))+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
function escapeHtml(s){return s.replace(/[&<>]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]))}
function renderApiList(){j('apiList').innerHTML=endpoints.map(ep=>`<div class="card clickable" style="padding:10px;margin-bottom:8px" onclick="editEndpoint('${ep.id}')"><b>${ep.name}</b><div><span class="pill">${ep.method}</span> <span class="pill">${ep.mode}</span></div><div class="muted">${ep.path}</div></div>`).join('')||'<p class="muted">No endpoints.</p>'}
function newEndpoint(){j('epId').value='';j('epName').value='New API';j('epMethod').value='GET';j('epPath').value='/api/v1/new/resource';j('epMode').value='static';j('epStore').value='';j('epStatus').value='200';j('epLatency').value='0';j('epDesc').value='';j('epSchema').value=pretty({fields:[]});j('epResponse').value=pretty({success:true,message:'OK',timestamp:'{{now}}'});j('epRules').value=pretty([])}
function editEndpoint(id){const ep=endpoints.find(x=>x.id===id); if(!ep)return; j('epId').value=ep.id;j('epName').value=ep.name;j('epMethod').value=ep.method;j('epPath').value=ep.path;j('epMode').value=ep.mode;j('epStore').value=ep.store_name||'';j('epStatus').value=ep.status_code;j('epLatency').value=ep.latency_ms;j('epDesc').value=ep.description||'';j('epSchema').value=pretty(ep.request_schema||{fields:[]});j('epResponse').value=pretty(ep.response_template||{});j('epRules').value=pretty(ep.rules||[])}
async function saveEndpoint(){const payload={id:j('epId').value||undefined,name:j('epName').value,method:j('epMethod').value,path:j('epPath').value,mode:j('epMode').value,store_name:j('epStore').value,status_code:+j('epStatus').value||200,latency_ms:+j('epLatency').value||0,description:j('epDesc').value,request_schema:parseJson('epSchema',{}),response_template:parseJson('epResponse',{}),rules:parseJson('epRules',[]),enabled:true};await api('/api/studio/endpoints',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});await loadAll()}
async function duplicateEndpoint(){if(!j('epId').value)return; j('epId').value=''; j('epName').value+=' Copy'; await saveEndpoint()}
async function deleteEndpoint(){if(!j('epId').value)return; if(!confirm('Delete this endpoint?'))return; await api('/api/studio/endpoints/'+j('epId').value,{method:'DELETE'}); newEndpoint(); await loadAll()}
function renderStoreList(){j('storeList').innerHTML=stores.map(s=>`<div class="card clickable" style="padding:10px;margin-bottom:8px" onclick="editStore('${s.id}')"><b>${s.name}</b><div class="muted">${s.description||''}</div></div>`).join('')||'<p class="muted">No stores.</p>'}
function newStore(){j('storeId').value='';j('storeName').value='NewStore';j('storeDesc').value='';j('storeSchema').value=pretty({fields:[]});j('storeRecords').textContent='[]';j('newRecord').value='{}'}
function editStore(id){const s=stores.find(x=>x.id===id); if(!s)return; j('storeId').value=s.id;j('storeName').value=s.name;j('storeDesc').value=s.description||'';j('storeSchema').value=pretty(s.schema||{fields:[]});loadStoreRecords()}
async function saveStore(){const payload={id:j('storeId').value||undefined,name:j('storeName').value,description:j('storeDesc').value,schema:parseJson('storeSchema',{})};await api('/api/studio/datastores',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});await loadAll()}
async function loadStoreRecords(){if(!j('storeName').value)return; const res=await api('/api/studio/datastores/'+encodeURIComponent(j('storeName').value)+'/records'); j('storeRecords').textContent=pretty(res.data||[])}
async function clearStoreRecords(){if(!j('storeName').value)return; if(!confirm('Clear all records from this store?'))return; await api('/api/studio/datastores/'+encodeURIComponent(j('storeName').value)+'/records',{method:'DELETE'}); await loadStoreRecords(); await loadAll()}
async function addRecord(){const rec=parseJson('newRecord',{}); await api('/api/studio/datastores/'+encodeURIComponent(j('storeName').value)+'/records',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(rec)}); await loadStoreRecords(); await loadAll()}
async function testCall(){const payload={method:j('testMethod').value,path:j('testPath').value,body:parseJson('testBody',{})};const res=await api('/api/studio/test-call',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});j('testResponse').textContent=pretty(res);await loadAll()}
function renderLogs(){j('logsTable').innerHTML=table(logs,['method','path','status_code','duration_ms','error','created_at'])}
async function createProject(){await api('/api/studio/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:j('newProjectName').value||'New Project',description:j('newProjectDesc').value||'',is_active:1})});await loadAll()}
async function importProject(){const f=j('importFile').files[0]; if(!f)return alert('Choose a project JSON file.'); const fd=new FormData();fd.append('file',f);const res=await fetch('/api/studio/import/project',{method:'POST',body:fd});alert(await res.text());await loadAll()}
function startEventStream(){const es=new EventSource('/api/studio/stream/events'); es.onmessage=(e)=>{const box=j('eventStream'); box.textContent=(e.data+'\n'+box.textContent).slice(0,8000)}}
newEndpoint(); newStore(); loadAll(); startEventStream(); setInterval(loadAll,5000);
</script>
</body>
</html>'''


init_db()

if __name__ == "__main__":
    raw_port = str(os.environ.get("PORT", "5050")).strip()
    try:
        port = int(raw_port or "5050")
    except ValueError:
        port = 5050
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
