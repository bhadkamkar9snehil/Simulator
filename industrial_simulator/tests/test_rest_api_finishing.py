from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.simulation.interfaces.rest_api import (
    API_ROUTE_PREFIX,
    RestApiTarget,
    _clean_route_prefix,
    api_registry,
    router,
)
from app.simulation.models import SignalValue, SimulationFrame, TargetBinding


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _frame(sequence: int, order_id: str = "A-1", site: str = "north") -> SimulationFrame:
    return SimulationFrame(
        simulation_id="sim-rest-finishing",
        sequence=sequence,
        values={
            "OrderId": SignalValue(value=order_id, data_type="String"),
            "Temperature": SignalValue(value=20.0 + sequence, data_type="Double"),
        },
        context={"Site": site},
    )


def _target(target_id: str, config: dict) -> RestApiTarget:
    return RestApiTarget(TargetBinding(target_id=target_id, kind="api", config=config))


def test_form_urlencoded_repeated_query_values_and_cookies() -> None:
    target = _target(
        "form-api",
        {
            "method": "POST",
            "path": "/submit",
            "response_mode": "template",
            "required_cookies": "session=abc123",
            "required_request_values": (
                "query.tag.0=alpha\n"
                "query.tag.1=beta\n"
                "body.item.0=one\n"
                "body.item.1=two\n"
                "cookie.session=abc123"
            ),
            "response_cookies": "result=${body.item.1}",
            "response_template": """{
                "tags": "${query.tag}",
                "first_tag": "${query.tag.0}",
                "items": "${body.item}",
                "second_item": "${body.item.1}",
                "session": "${cookie.session}"
            }""",
        },
    )
    asyncio.run(target.start("sim-rest-finishing", "REST finishing", []))
    try:
        response = _client().post(
            f"{API_ROUTE_PREFIX}/submit?tag=alpha&tag=beta",
            data={"item": ["one", "two"]},
            cookies={"session": "abc123"},
        )
        assert response.status_code == 200
        assert response.json() == {
            "tags": ["alpha", "beta"],
            "first_tag": "alpha",
            "items": ["one", "two"],
            "second_item": "two",
            "session": "abc123",
        }
        assert response.cookies["result"] == "two"
    finally:
        asyncio.run(target.stop())


def test_required_cookie_uses_configured_request_error_status() -> None:
    target = _target(
        "cookie-api",
        {
            "method": "GET",
            "path": "/cookie-required",
            "response_mode": "template",
            "response_template": '{"ok":true}',
            "required_cookies": "session=expected",
            "request_error_status": 403,
        },
    )
    asyncio.run(target.start("sim-rest-finishing", "REST finishing", []))
    try:
        response = _client().get(f"{API_ROUTE_PREFIX}/cookie-required")
        assert response.status_code == 403
        assert target.status().details["client_error_count"] == 1
    finally:
        asyncio.run(target.stop())


def test_head_falls_back_to_get_and_options_are_synthesized() -> None:
    target = _target(
        "method-api",
        {
            "method": "GET",
            "path": "/method-check",
            "response_mode": "template",
            "response_template": '{"value":"payload"}',
            "response_headers": "X-Simulated: yes",
        },
    )
    asyncio.run(target.start("sim-rest-finishing", "REST finishing", []))
    try:
        client = _client()
        get_response = client.get(f"{API_ROUTE_PREFIX}/method-check")
        head_response = client.head(f"{API_ROUTE_PREFIX}/method-check")
        options_response = client.options(f"{API_ROUTE_PREFIX}/method-check")

        assert get_response.status_code == 200
        assert head_response.status_code == 200
        assert head_response.content == b""
        assert head_response.headers["X-Simulated"] == "yes"
        assert head_response.headers.get("content-length") == get_response.headers.get("content-length")

        assert options_response.status_code == 204
        allowed = {item.strip() for item in options_response.headers["Allow"].split(",")}
        assert {"GET", "HEAD", "OPTIONS"} <= allowed

        details = target.status().details
        assert details["request_count"] == 2
        assert details["success_count"] == 2
    finally:
        asyncio.run(target.stop())


def test_bodyless_status_codes_do_not_emit_configured_payloads() -> None:
    target = _target(
        "not-modified-api",
        {
            "method": "GET",
            "path": "/not-modified",
            "status_code": 304,
            "response_mode": "template",
            "response_template": '{"must_not_be_sent":true}',
        },
    )
    asyncio.run(target.start("sim-rest-finishing", "REST finishing", []))
    try:
        response = _client().get(f"{API_ROUTE_PREFIX}/not-modified")
        assert response.status_code == 304
        assert response.content == b""
    finally:
        asyncio.run(target.stop())


def test_history_match_supports_multiple_explicit_match_fields() -> None:
    target = _target(
        "multi-match-api",
        {
            "method": "GET",
            "path": "/orders/{order_id}",
            "selection_mode": "history_match",
            "match_fields": (
                "values.OrderId=path.order_id\n"
                "context.Site=query.site"
            ),
            "response_mode": "record",
            "fields": "OrderId,Temperature",
            "include_system_fields": False,
        },
    )
    asyncio.run(target.start("sim-rest-finishing", "REST finishing", []))
    asyncio.run(target.publish(_frame(1, order_id="A-1", site="north")))
    asyncio.run(target.publish(_frame(2, order_id="A-1", site="south")))
    try:
        north = _client().get(f"{API_ROUTE_PREFIX}/orders/A-1?site=north")
        south = _client().get(f"{API_ROUTE_PREFIX}/orders/A-1?site=south")
        assert north.status_code == 200
        assert north.json()["Temperature"] == 21.0
        assert south.status_code == 200
        assert south.json()["Temperature"] == 22.0
    finally:
        asyncio.run(target.stop())


def test_request_metrics_reset_on_new_runtime_start() -> None:
    target = _target(
        "metrics-reset-api",
        {
            "method": "GET",
            "path": "/metrics-reset",
            "response_mode": "template",
            "response_template": '{"ok":true}',
        },
    )
    client = _client()

    asyncio.run(target.start("sim-rest-finishing", "REST finishing", []))
    try:
        assert client.get(f"{API_ROUTE_PREFIX}/metrics-reset").status_code == 200
        assert target.status().details["request_count"] == 1
    finally:
        asyncio.run(target.stop())

    stopped = target.status().details
    assert stopped["request_count"] == 1
    assert stopped["metrics_started_at"]

    asyncio.run(target.start("sim-rest-finishing", "REST finishing", []))
    try:
        restarted = target.status().details
        assert restarted["request_count"] == 0
        assert restarted["success_count"] == 0
        assert restarted["last_status_code"] is None
        assert restarted["metrics_started_at"]

        assert client.get(f"{API_ROUTE_PREFIX}/metrics-reset").status_code == 200
        assert target.status().details["request_count"] == 1
    finally:
        asyncio.run(target.stop())
        api_registry.remove("sim-rest-finishing", "metrics-reset-api")


def test_route_prefix_normalization_is_stable() -> None:
    assert _clean_route_prefix("sim-api") == "/sim-api"
    assert _clean_route_prefix("/integration/api/") == "/integration/api"
