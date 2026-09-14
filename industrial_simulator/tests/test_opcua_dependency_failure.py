from __future__ import annotations

import asyncio

import pytest

import app.opcua_server as opcua_server_module


def test_opcua_start_fails_instead_of_silently_running_mock(monkeypatch) -> None:
    monkeypatch.setattr(opcua_server_module, "Server", None)
    server = opcua_server_module.OpcUaTagServer()

    with pytest.raises(RuntimeError, match="asyncua could not be imported"):
        asyncio.run(server.start())

    assert server.running is False
    assert server.mock_mode is True
    assert server.get_status()["diagnostics_available"] is False
