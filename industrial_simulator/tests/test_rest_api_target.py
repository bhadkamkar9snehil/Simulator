from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.simulation.interfaces.rest_api import RestApiTarget, api_registry, router
from app.simulation.models import SignalValue, SimulationFrame, TargetBinding


def _frame(sequence: int, temperature: float) -> SimulationFrame:
    return SimulationFrame(
        simulation_id="sim-api-test",
        sequence=sequence,
        values={
            "Temperature": SignalValue(value=temperature, data_type="Double", unit="C"),
            "Running": SignalValue(value=True, data_type="Boolean"),
        },
        context={"Batch": "B-42"},
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_api_target_templates_live_data_and_request_inputs() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="orders-api",
        kind="api",
        config={
            "method": "POST",
            "path": "/orders/{order_id}",
            "response_mode": "template",
            "status_code": 201,
            "required_headers": "X-Api-Key: demo",
            "response_headers": "X-Simulated: yes",
            "response_template": """{
              "order": "${path.order_id}",
              "mode": "${query.mode}",
              "quantity": "${body.quantity}",
              "temperature": "${values.Temperature}",
              "batch": "${context.Batch}",
              "sequence": "${meta.sequence}"
            }""",
        },
    ))
    asyncio.run(target.start("sim-api-test", "API test", []))
    asyncio.run(target.publish(_frame(7, 42.5)))
    try:
        response = _client().post(
            "/sim-api/orders/A-100?mode=fast",
            headers={"X-Api-Key": "demo"},
            json={"quantity": 5},
        )
        assert response.status_code == 201
        assert response.headers["X-Simulated"] == "yes"
        assert response.json() == {
            "order": "A-100",
            "mode": "fast",
            "quantity": 5,
            "temperature": 42.5,
            "batch": "B-42",
            "sequence": 7,
        }
        assert target.status().details["request_count"] == 1
    finally:
        asyncio.run(target.stop())


def test_api_target_rejects_missing_required_header() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="secured-api",
        kind="api",
        config={
            "method": "GET",
            "path": "/secure",
            "response_mode": "values",
            "required_headers": "Authorization: Bearer demo-token",
        },
    ))
    asyncio.run(target.start("sim-api-test", "API test", []))
    asyncio.run(target.publish(_frame(0, 10.0)))
    try:
        response = _client().get("/sim-api/secure")
        assert response.status_code == 401
    finally:
        asyncio.run(target.stop())


def test_api_target_returns_configured_no_data_status_before_first_frame() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="empty-api",
        kind="api",
        config={
            "method": "GET",
            "path": "/empty",
            "response_mode": "record",
            "empty_status_code": 425,
        },
    ))
    asyncio.run(target.start("sim-api-test", "API test", []))
    try:
        response = _client().get("/sim-api/empty")
        assert response.status_code == 425
        assert "has not published data" in response.json()["detail"]
    finally:
        asyncio.run(target.stop())


def test_api_history_uses_same_canonical_frames() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="history-api",
        kind="api",
        config={
            "method": "GET",
            "path": "/history",
            "response_mode": "history",
            "fields": "Temperature",
            "include_context": True,
            "include_system_fields": True,
            "history_size": 2,
            "envelope": "items",
        },
    ))
    asyncio.run(target.start("sim-api-test", "API test", []))
    for sequence, temperature in [(0, 1.0), (1, 2.0), (2, 3.0)]:
        asyncio.run(target.publish(_frame(sequence, temperature)))
    try:
        payload = _client().get("/sim-api/history").json()
        assert [item["Temperature"] for item in payload["items"]] == [2.0, 3.0]
        assert all(item["Batch"] == "B-42" for item in payload["items"])
    finally:
        asyncio.run(target.stop())


def test_duplicate_live_method_and_path_are_rejected() -> None:
    first = RestApiTarget(TargetBinding(target_id="first", kind="api", config={"method": "GET", "path": "/same"}))
    second = RestApiTarget(TargetBinding(target_id="second", kind="api", config={"method": "GET", "path": "/same"}))
    asyncio.run(first.start("sim-one", "One", []))
    try:
        try:
            asyncio.run(second.start("sim-two", "Two", []))
        except ValueError as exc:
            assert "already in use" in str(exc)
        else:
            raise AssertionError("Duplicate simulated API routes must be rejected.")
    finally:
        asyncio.run(first.stop())
        api_registry.remove("sim-two", "second")
