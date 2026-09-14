from __future__ import annotations

from types import SimpleNamespace

from app.opcua_diagnostics import OpcUaDiagnostics


def test_session_introspection_unavailable_is_explicit_not_zero() -> None:
    diagnostics = OpcUaDiagnostics()
    snapshot = diagnostics.snapshot(SimpleNamespace(iserver=SimpleNamespace()))

    assert snapshot["session_introspection_available"] is False
    assert snapshot["subscription_introspection_available"] is False
    assert snapshot["connected_clients"] is None
    assert snapshot["session_count"] is None
    assert snapshot["sessions"] == []


def test_subscription_introspection_unavailable_is_independent() -> None:
    session = SimpleNamespace(
        name="Client",
        session_id="session-1",
        state=SimpleNamespace(name="Activated"),
        user="Anonymous",
        session_timeout=60000,
        _last_activity=None,
    )
    iserver = SimpleNamespace(_external_sessions={"token": session})
    snapshot = OpcUaDiagnostics().snapshot(SimpleNamespace(iserver=iserver))

    assert snapshot["session_introspection_available"] is True
    assert snapshot["subscription_introspection_available"] is False
    assert snapshot["connected_clients"] == 1
    assert snapshot["session_count"] == 1
    assert snapshot["sessions"][0]["subscriptions"] is None
