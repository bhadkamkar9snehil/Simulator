from __future__ import annotations

import json

from fastapi.testclient import TestClient

from main import app


def test_stream_status_and_snapshot_include_runtime_state() -> None:
    client = TestClient(app)

    status = client.get("/api/streams/status")
    snapshot = client.get("/api/streams/snapshot?value_limit=5")

    assert status.status_code == 200
    streams = status.json()["streams"]
    assert streams["enabled"] is True
    assert {"snapshot", "ndjson", "sse"} <= set(streams["transports"])
    assert isinstance(streams["websocket_available"], bool)
    assert snapshot.status_code == 200
    payload = snapshot.json()
    assert "simulator" in payload
    assert "protocol" in payload
    assert "jobs" in payload
    assert "current_values" in payload


def test_ndjson_stream_emits_limited_snapshots() -> None:
    client = TestClient(app)

    response = client.get("/api/streams/ndjson?interval_ms=50&limit=2&value_limit=3")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    rows = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert len(rows) == 2
    assert all("current_values" in row for row in rows)


def test_sse_stream_emits_limited_snapshot_event() -> None:
    client = TestClient(app)

    response = client.get("/api/streams/sse?interval_ms=50&limit=1&value_limit=3")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: simulator.snapshot" in response.text
    assert "data: " in response.text


def test_websocket_stream_emits_snapshot() -> None:
    client = TestClient(app)
    if not client.get("/api/streams/status").json()["streams"]["websocket_available"]:
        return

    with client.websocket_connect("/api/streams/ws?interval_ms=50&limit=1&value_limit=3") as websocket:
        payload = websocket.receive_json()

    assert "simulator" in payload
    assert "protocol" in payload
    assert "current_values" in payload
