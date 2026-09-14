from __future__ import annotations

import datetime as dt

import pytest

from app.opcua_support import (
    coerce_value,
    normalize_server_options,
    parse_type_overrides,
    parse_writable_signals,
    server_options_match,
)


def test_default_server_options_are_open_and_anonymous() -> None:
    options = normalize_server_options({})
    assert options["security_policy"] == "none"
    assert options["authentication"] == "anonymous"
    assert options["server_name"] == "Industrial Simulator OPC UA"
    assert options["password"] == ""


def test_username_authentication_requires_credentials() -> None:
    with pytest.raises(ValueError, match="requires both username and password"):
        normalize_server_options({"authentication": "username", "username": "operator"})

    options = normalize_server_options({
        "authentication": "username",
        "username": "operator",
        "password": "fixture-password",
    })
    assert options["username"] == "operator"
    assert options["password"] == "fixture-password"


def test_shared_server_option_conflict_redacts_password_name() -> None:
    left = normalize_server_options({
        "authentication": "username",
        "username": "operator",
        "password": "one",
    })
    right = normalize_server_options({
        "authentication": "username",
        "username": "operator",
        "password": "two",
    })
    assert server_options_match(left, right) == ["credentials"]


def test_parse_type_overrides_uses_canonical_scalar_and_array_types() -> None:
    available = {"Count", "Speed", "When", "Samples"}
    assert parse_type_overrides(
        "Count=UInt32\nSpeed=Float\nWhen=DateTime\nSamples=UInt16[]",
        available,
    ) == {
        "Count": "UInt32",
        "Speed": "Float",
        "When": "DateTime",
        "Samples": "UInt16[]",
    }

    with pytest.raises(ValueError, match="Unknown OPC UA type override signal"):
        parse_type_overrides("Missing=UInt32", available)
    with pytest.raises(ValueError, match="Unsupported OPC UA data type"):
        parse_type_overrides("Count=Decimal128", available)


def test_parse_writable_signals_rejects_unknown_names() -> None:
    available = {"Setpoint", "Mode"}
    assert parse_writable_signals("Setpoint, Mode", available) == {"Setpoint", "Mode"}
    with pytest.raises(ValueError, match="Unknown OPC UA writable signal"):
        parse_writable_signals("Setpoint, Missing", available)


def test_opcua_value_coercion_delegates_to_canonical_type_layer() -> None:
    assert coerce_value("12", "UInt32") == 12
    assert coerce_value("2.5", "Float") == 2.5
    assert coerce_value("yes", "Boolean") is True
    assert coerce_value("[1, 2, 65535]", "UInt16[]") == [1, 2, 65535]
    when = coerce_value("2026-09-14T12:30:00Z", "DateTime")
    assert isinstance(when, dt.datetime)
    assert when.tzinfo is not None

    with pytest.raises(ValueError, match="outside"):
        coerce_value(-1, "UInt16")
