from __future__ import annotations

from typing import Any
import re

LABEL_COLUMNS = {"timestamp", "scenario", "operating_state", "phase", "product", "heat_id"}
BOOLEAN_SUFFIXES = ("_active", "_alarm", "_fault", "_enabled")
INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\d*\.\d+|\d+)([eE][+-]?\d+)?$")


def is_empty(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def infer_column_type(column: str, values: list[Any]) -> str:
    name = column.strip().lower()
    if name in LABEL_COLUMNS:
        return "String"
    samples = [str(v).strip() for v in values if not is_empty(v)]
    if not samples:
        return "String"
    lower = [v.lower() for v in samples]
    boolean_like = all(v in {"true", "false", "0", "1", "yes", "no"} for v in lower)
    if boolean_like and name.endswith(BOOLEAN_SUFFIXES):
        return "Boolean"
    if all(INT_RE.match(v) for v in samples):
        return "Int64"
    if all(FLOAT_RE.match(v) for v in samples):
        return "Double"
    return "String"


def infer_types(rows: list[dict[str, Any]], columns: list[str], sample_size: int = 100) -> dict[str, str]:
    sample = rows[:sample_size]
    return {col: infer_column_type(col, [row.get(col, "") for row in sample]) for col in columns}


def convert_value(value: Any, data_type: str) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    if data_type == "Double":
        return float(text)
    if data_type == "Int64":
        return int(float(text))
    if data_type == "Boolean":
        return text.lower() in {"true", "1", "yes", "y", "on"}
    return text


def sanitize_tag_name(value: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_.]+", "_", value.strip())
    out = re.sub(r"_+", "_", out).strip("._")
    return out or "Tag"


def is_default_disabled_column(column: str) -> bool:
    name = column.lower()
    if name in LABEL_COLUMNS:
        return True
    if name.endswith(("_active", "_alarm")):
        return True
    return False
