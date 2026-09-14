from __future__ import annotations

import ast
import datetime as dt
import json
import math
from dataclasses import dataclass
from typing import Any

try:
    from asyncua import ua  # type: ignore
except Exception:  # pragma: no cover
    ua = None


# Keep conversion policy isolated from replay/orchestration (Ponytail: one reason to change).
SCALAR_TYPES = {
    "Boolean", "SByte", "Byte", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64",
    "Float", "Double", "String", "DateTime", "Guid", "ByteString", "XmlElement", "NodeId",
    "QualifiedName", "LocalizedText", "StatusCode",
}
INTEGER_RANGES = {
    "SByte": (-128, 127), "Byte": (0, 255), "Int16": (-32768, 32767), "UInt16": (0, 65535),
    "Int32": (-2147483648, 2147483647), "UInt32": (0, 4294967295),
    "Int64": (-9223372036854775808, 9223372036854775807), "UInt64": (0, 18446744073709551615),
}
QUALITY_ALIASES = {
    "good": "Good", "uncertain": "Uncertain", "bad": "Bad", "bad_nodata": "BadNoData",
    "bad_no_data": "BadNoData", "badnotconnected": "BadNotConnected", "bad_not_connected": "BadNotConnected",
    "badcommunicationerror": "BadCommunicationError", "bad_communication_error": "BadCommunicationError",
    "badoutofservice": "BadOutOfService", "bad_out_of_service": "BadOutOfService",
    "uncertainlastusablevalue": "UncertainLastUsableValue", "uncertain_last_usable_value": "UncertainLastUsableValue",
}


def split_type(data_type: str) -> tuple[str, bool]:
    text = (data_type or "String").strip()
    if text.endswith("[]"):
        return text[:-2], True
    if text.startswith("Array[") and text.endswith("]"):
        return text[6:-1].strip(), True
    return text, False


def is_supported_type(data_type: str) -> bool:
    base, _ = split_type(data_type)
    return base in SCALAR_TYPES


def parse_array(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"null", "none", "nan"}:
            return None
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(text)
                if isinstance(parsed, (list, tuple)):
                    return list(parsed)
            except Exception:
                pass
        return [part.strip() for part in text.split(",")]
    raise ValueError(f"Expected array-compatible value, got {type(value).__name__}.")


def _nullish(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "null", "none", "nan", "nat"}:
        return True
    return False


def _datetime(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, dt.date):
        parsed = dt.datetime.combine(value, dt.time())
    else:
        text = str(value).strip().replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def coerce_scalar(data_type: str, value: Any) -> Any:
    if _nullish(value):
        return None
    if data_type == "Boolean":
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}: return True
            if lowered in {"false", "0", "no", "off"}: return False
            raise ValueError(f"Invalid Boolean value: {value!r}")
        return bool(value)
    if data_type in INTEGER_RANGES:
        result = int(value)
        low, high = INTEGER_RANGES[data_type]
        if not low <= result <= high:
            raise ValueError(f"{data_type} value {result} is outside [{low}, {high}].")
        return result
    if data_type in {"Float", "Double"}:
        return float(value)
    if data_type == "String":
        return str(value)
    if data_type == "DateTime":
        return _datetime(value)
    if ua is None:
        return value
    if data_type == "Guid": return ua.Guid(str(value))
    if data_type == "ByteString":
        if isinstance(value, bytes): return value
        if isinstance(value, bytearray): return bytes(value)
        return str(value).encode("utf-8")
    if data_type == "XmlElement": return ua.XmlElement(str(value))
    if data_type == "NodeId": return ua.NodeId.from_string(str(value))
    if data_type == "QualifiedName": return ua.QualifiedName.from_string(str(value))
    if data_type == "LocalizedText": return ua.LocalizedText(str(value))
    if data_type == "StatusCode": return status_code(value)
    raise ValueError(f"Unsupported OPC UA datatype: {data_type}")


def coerce_value(data_type: str, value: Any) -> Any:
    base, is_array = split_type(data_type)
    if base not in SCALAR_TYPES:
        raise ValueError(f"Unsupported OPC UA datatype: {data_type}")
    if is_array:
        items = parse_array(value)
        return None if items is None else [coerce_scalar(base, item) for item in items]
    return coerce_scalar(base, value)


def variant_type(data_type: str) -> Any:
    if ua is None:
        return None
    base, _ = split_type(data_type)
    mapping = {
        "Boolean": ua.VariantType.Boolean, "SByte": ua.VariantType.SByte, "Byte": ua.VariantType.Byte,
        "Int16": ua.VariantType.Int16, "UInt16": ua.VariantType.UInt16, "Int32": ua.VariantType.Int32,
        "UInt32": ua.VariantType.UInt32, "Int64": ua.VariantType.Int64, "UInt64": ua.VariantType.UInt64,
        "Float": ua.VariantType.Float, "Double": ua.VariantType.Double, "String": ua.VariantType.String,
        "DateTime": ua.VariantType.DateTime, "Guid": ua.VariantType.Guid, "ByteString": ua.VariantType.ByteString,
        "XmlElement": ua.VariantType.XmlElement, "NodeId": ua.VariantType.NodeId,
        "QualifiedName": ua.VariantType.QualifiedName, "LocalizedText": ua.VariantType.LocalizedText,
        "StatusCode": ua.VariantType.StatusCode,
    }
    return mapping[base]


def status_code(value: Any = "Good") -> Any:
    if ua is None:
        return value
    if isinstance(value, ua.StatusCode):
        return value
    if isinstance(value, int):
        return ua.StatusCode(value)
    text = str(value or "Good").strip()
    alias = QUALITY_ALIASES.get(text.lower(), text)
    code = getattr(ua.StatusCodes, alias, None)
    if code is None:
        raise ValueError(f"Unknown OPC UA quality/status code: {value!r}")
    return ua.StatusCode(code)


def data_value(data_type: str, value: Any, quality: Any = "Good", source_timestamp: Any = None) -> Any:
    coerced = coerce_value(data_type, value)
    if ua is None:
        return {"value": coerced, "quality": quality, "source_timestamp": source_timestamp}
    variant = ua.Variant(coerced, variant_type(data_type))
    dv = ua.DataValue(variant)
    dv.StatusCode = status_code(quality)
    if source_timestamp is not None and not _nullish(source_timestamp):
        dv.SourceTimestamp = _datetime(source_timestamp)
    return dv


def default_value(data_type: str) -> Any:
    base, is_array = split_type(data_type)
    if is_array: return []
    if base == "Boolean": return False
    if base in INTEGER_RANGES: return 0
    if base in {"Float", "Double"}: return 0.0
    if base == "DateTime": return dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    if base == "ByteString": return b""
    return ""
