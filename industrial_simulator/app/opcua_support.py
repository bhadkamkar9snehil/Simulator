from __future__ import annotations

import datetime as dt
from typing import Any

from app.opcua_types import (
    coerce_value as coerce_opcua_value,
    default_value,
    is_supported_type,
    status_code as canonical_status_code,
    variant_type as canonical_variant_type,
)

try:
    from asyncua import ua  # type: ignore
    try:
        from asyncua.crypto.permission_rules import User, UserRole  # type: ignore
    except Exception:  # asyncua 1.1 compatibility
        from asyncua.server.users import User, UserRole  # type: ignore
except Exception:  # pragma: no cover - handled by the unified target before start
    ua = None
    User = None
    UserRole = None


SECURITY_POLICIES = {
    "none",
    "basic256sha256_sign",
    "basic256sha256_sign_encrypt",
    "basic256sha256_both",
    "none_and_basic256sha256",
}
AUTHENTICATION_MODES = {"anonymous", "username", "anonymous_or_username"}


def normalize_server_options(config: dict[str, Any] | None) -> dict[str, Any]:
    config = config or {}
    security_policy = str(config.get("security_policy", "none")).strip().lower()
    authentication = str(config.get("authentication", "anonymous")).strip().lower()
    if security_policy not in SECURITY_POLICIES:
        raise ValueError(f"Unsupported OPC UA security policy: {security_policy}")
    if authentication not in AUTHENTICATION_MODES:
        raise ValueError(f"Unsupported OPC UA authentication mode: {authentication}")

    username = str(config.get("username", "")).strip()
    password = str(config.get("password", ""))
    if authentication in {"username", "anonymous_or_username"} and (not username or not password):
        raise ValueError("OPC UA username authentication requires both username and password.")

    return {
        "security_policy": security_policy,
        "authentication": authentication,
        "username": username,
        "password": password,
        "server_name": str(config.get("server_name", "Industrial Simulator OPC UA")).strip()
        or "Industrial Simulator OPC UA",
        "application_uri": str(
            config.get("application_uri", "urn:local:industrial-simulator:opcua")
        ).strip()
        or "urn:local:industrial-simulator:opcua",
        "certificate_path": str(config.get("certificate_path", "")).strip() or None,
        "private_key_path": str(config.get("private_key_path", "")).strip() or None,
    }


def public_server_options(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "security_policy": options["security_policy"],
        "authentication": options["authentication"],
        "username": options["username"] if options["authentication"] != "anonymous" else None,
        "server_name": options["server_name"],
        "application_uri": options["application_uri"],
        "certificate_path": options["certificate_path"],
        "private_key_path": options["private_key_path"],
    }


def server_options_match(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for key in (
        "security_policy",
        "authentication",
        "username",
        "password",
        "server_name",
        "application_uri",
        "certificate_path",
        "private_key_path",
    ):
        if left.get(key) != right.get(key):
            mismatches.append("credentials" if key == "password" else key)
    return sorted(set(mismatches))


def parse_writable_signals(value: Any, available: set[str]) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        names = {str(item).strip() for item in value if str(item).strip()}
    else:
        names = {item.strip() for item in str(value).replace("\n", ",").split(",") if item.strip()}
    unknown = sorted(names - available)
    if unknown:
        raise ValueError(f"Unknown OPC UA writable signal: {unknown[0]}")
    return names


def parse_type_overrides(value: Any, available: set[str]) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        raw = {str(key).strip(): str(item).strip() for key, item in value.items()}
    else:
        raw: dict[str, str] = {}
        for line in str(value).splitlines():
            line = line.strip()
            if not line:
                continue
            name, separator, data_type = line.partition("=")
            if not separator:
                raise ValueError(f"OPC UA type override must use Signal=Type: {line}")
            raw[name.strip()] = data_type.strip()
    unknown = sorted(set(raw) - available)
    if unknown:
        raise ValueError(f"Unknown OPC UA type override signal: {unknown[0]}")
    invalid = sorted({data_type for data_type in raw.values() if not is_supported_type(data_type)})
    if invalid:
        raise ValueError(f"Unsupported OPC UA data type: {invalid[0]}")
    return raw


def security_policy_types(policy: str) -> list[Any]:
    if ua is None:
        raise RuntimeError("asyncua UA types are unavailable.")
    mapping = {
        "none": [ua.SecurityPolicyType.NoSecurity],
        "basic256sha256_sign": [ua.SecurityPolicyType.Basic256Sha256_Sign],
        "basic256sha256_sign_encrypt": [ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt],
        "basic256sha256_both": [
            ua.SecurityPolicyType.Basic256Sha256_Sign,
            ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt,
        ],
        "none_and_basic256sha256": [
            ua.SecurityPolicyType.NoSecurity,
            ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt,
        ],
    }
    return mapping[policy]


def identity_tokens(authentication: str) -> list[Any]:
    if ua is None:
        raise RuntimeError("asyncua UA types are unavailable.")
    tokens: list[Any] = []
    if authentication in {"anonymous", "anonymous_or_username"}:
        tokens.append(ua.AnonymousIdentityToken)
    if authentication in {"username", "anonymous_or_username"}:
        tokens.append(ua.UserNameIdentityToken)
    return tokens


def _user(name: str | None = None) -> Any:
    if User is None or UserRole is None:
        return None
    try:
        return User(role=UserRole.User, name=name) if name else User(role=UserRole.User)
    except TypeError:  # older asyncua User constructor
        return User(role=UserRole.User)


class FixtureUserManager:
    """Small credential fixture for simulator endpoints, not an account system."""

    def __init__(self, options: dict[str, Any]):
        self.authentication = options["authentication"]
        self.username = options["username"]
        self.password = options["password"]

    def get_user(
        self,
        iserver: Any,
        username: str | None = None,
        password: str | None = None,
        certificate: Any = None,
    ) -> Any:
        if username is None:
            return _user() if self.authentication in {"anonymous", "anonymous_or_username"} else None
        if self.authentication in {"username", "anonymous_or_username"}:
            if username == self.username and password == self.password:
                return _user(username)
        return None


# Compatibility facade only. Datatype semantics live in app.opcua_types.
def variant_type(data_type: str) -> Any:
    return canonical_variant_type(data_type)


def status_code(quality: Any) -> Any:
    return canonical_status_code(quality)


def opcua_timestamp(value: str | dt.datetime | None) -> dt.datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        try:
            parsed = dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=dt.timezone.utc)


def initial_value(data_type: str, value: Any) -> Any:
    if value is None:
        return default_value(data_type)
    return coerce_opcua_value(data_type, value)


def coerce_value(value: Any, data_type: str) -> Any:
    """Legacy argument order facade over the canonical OPC UA coercion layer."""
    return coerce_opcua_value(data_type, value)
