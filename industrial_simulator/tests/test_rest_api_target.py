from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.simulation.interfaces.rest_api import RestApiTarget, api_registry, router
from app.simulation.models import ClockSpec, SignalValue, SimulationDefinition, SimulationFrame, SourceBinding, TargetBinding
from app.simulation.runtime import SimulationManager


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


def _order_frame(sequence: int, order_id: str, temperature: float) -> SimulationFrame:
    frame = _frame(sequence, temperature)
    frame.values["OrderId"] = SignalValue(value=order_id, data_type="String")
    return frame


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
        details = target.status().details
        assert details["request_count"] == 1
        assert details["success_count"] == 1
        assert details["last_status_code"] == 201
        assert details["last_latency_ms"] is not None
    finally:
        asyncio.run(target.stop())


def test_api_target_rejects_missing_required_header_and_counts_client_error() -> None:
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
        details = target.status().details
        assert details["request_count"] == 1
        assert details["client_error_count"] == 1
        assert details["last_status_code"] == 401
    finally:
        asyncio.run(target.stop())


def test_api_target_requires_query_and_body_values() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="request-contract",
        kind="api",
        config={
            "method": "POST",
            "path": "/quality",
            "response_mode": "template",
            "response_template": '{"accepted":true}',
            "required_request_values": "query.site=plant-a\nbody.type=result\nbody.sample_id",
            "request_error_status": 422,
        },
    ))
    asyncio.run(target.start("sim-api-test", "API test", []))
    try:
        missing = _client().post("/sim-api/quality?site=plant-a", json={"type": "result"})
        assert missing.status_code == 422
        wrong = _client().post(
            "/sim-api/quality?site=plant-b",
            json={"type": "result", "sample_id": "S-1"},
        )
        assert wrong.status_code == 422
        accepted = _client().post(
            "/sim-api/quality?site=plant-a",
            json={"type": "result", "sample_id": "S-1"},
        )
        assert accepted.status_code == 200
        assert accepted.json() == {"accepted": True}
        details = target.status().details
        assert details["request_count"] == 3
        assert details["client_error_count"] == 2
        assert details["success_count"] == 1
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


def test_history_response_supports_order_offset_and_limit() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="paged-history",
        kind="api",
        config={
            "method": "GET",
            "path": "/paged-history",
            "response_mode": "history",
            "fields": "Temperature",
            "include_system_fields": False,
            "history_size": 5,
            "history_order": "newest_first",
            "default_page_size": 2,
            "max_page_size": 3,
        },
    ))
    asyncio.run(target.start("sim-api-test", "API test", []))
    for sequence, temperature in enumerate([1.0, 2.0, 3.0, 4.0]):
        asyncio.run(target.publish(_frame(sequence, temperature)))
    try:
        first = _client().get("/sim-api/paged-history").json()
        assert [item["Temperature"] for item in first] == [4.0, 3.0]
        page = _client().get("/sim-api/paged-history?offset=1&limit=2").json()
        assert [item["Temperature"] for item in page] == [3.0, 2.0]
        invalid = _client().get("/sim-api/paged-history?limit=4")
        assert invalid.status_code == 400
        assert target.status().details["client_error_count"] == 1
    finally:
        asyncio.run(target.stop())


def test_history_match_selects_retained_frame_without_moving_simulation() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="order-lookup",
        kind="api",
        config={
            "method": "GET",
            "path": "/lookup/{order_id}",
            "selection_mode": "history_match",
            "match_frame": "values.OrderId",
            "match_request": "path.order_id",
            "response_mode": "record",
            "fields": "OrderId,Temperature",
            "include_system_fields": False,
            "not_found_status": 404,
        },
    ))
    asyncio.run(target.start("sim-api-test", "API test", []))
    asyncio.run(target.publish(_order_frame(0, "A-1", 21.5)))
    asyncio.run(target.publish(_order_frame(1, "A-2", 22.5)))
    try:
        found = _client().get("/sim-api/lookup/A-1")
        assert found.status_code == 200
        assert found.json() == {"Temperature": 21.5, "OrderId": "A-1"}
        missing = _client().get("/sim-api/lookup/A-9")
        assert missing.status_code == 404
        details = target.status().details
        assert details["request_count"] == 2
        assert details["success_count"] == 1
        assert details["client_error_count"] == 1
    finally:
        asyncio.run(target.stop())


def test_response_headers_can_use_request_and_selected_frame_tokens() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="header-template",
        kind="api",
        config={
            "method": "GET",
            "path": "/orders/{order_id}",
            "selection_mode": "history_match",
            "match_frame": "values.OrderId",
            "match_request": "path.order_id",
            "response_mode": "record",
            "fields": "OrderId",
            "include_system_fields": False,
            "response_headers": "Location: /orders/${path.order_id}\nETag: seq-${meta.sequence}",
        },
    ))
    asyncio.run(target.start("sim-api-test", "API test", []))
    asyncio.run(target.publish(_order_frame(4, "A-4", 20.0)))
    asyncio.run(target.publish(_order_frame(5, "A-5", 21.0)))
    try:
        response = _client().get("/sim-api/orders/A-4")
        assert response.status_code == 200
        assert response.headers["Location"] == "/orders/A-4"
        assert response.headers["ETag"] == "seq-4"
        assert response.json()["OrderId"] == "A-4"
    finally:
        asyncio.run(target.stop())


def test_api_can_serve_text_or_xml_with_template_tokens() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="xml-api",
        kind="api",
        config={
            "method": "GET",
            "path": "/xml/{id}",
            "body_mode": "text",
            "media_type": "application/xml",
            "text_template": '<reading id="${path.id}">${values.Temperature}</reading>',
        },
    ))
    asyncio.run(target.start("sim-api-test", "API test", []))
    asyncio.run(target.publish(_frame(3, 19.75)))
    try:
        response = _client().get("/sim-api/xml/T-1")
        assert response.status_code == 200
        assert response.text == '<reading id="T-1">19.75</reading>'
        assert response.headers["content-type"].startswith("application/xml")
    finally:
        asyncio.run(target.stop())


def test_api_can_return_explicitly_empty_body() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="no-content-api",
        kind="api",
        config={
            "method": "POST",
            "path": "/accepted",
            "body_mode": "empty",
            "status_code": 204,
        },
    ))
    asyncio.run(target.start("sim-api-test", "API test", []))
    try:
        response = _client().post("/sim-api/accepted", json={"value": 1})
        assert response.status_code == 204
        assert response.content == b""
    finally:
        asyncio.run(target.stop())


def test_semantically_duplicate_dynamic_routes_are_rejected() -> None:
    first = RestApiTarget(TargetBinding(target_id="first", kind="api", config={"method": "GET", "path": "/orders/{id}"}))
    second = RestApiTarget(TargetBinding(target_id="second", kind="api", config={"method": "GET", "path": "/orders/{name}"}))
    asyncio.run(first.start("sim-one", "One", []))
    try:
        try:
            asyncio.run(second.start("sim-two", "Two", []))
        except ValueError as exc:
            assert "conflicts with" in str(exc)
        else:
            raise AssertionError("Equivalent dynamic API routes must be rejected.")
    finally:
        asyncio.run(first.stop())
        api_registry.remove("sim-two", "second")


def test_static_route_wins_over_dynamic_route() -> None:
    dynamic = RestApiTarget(TargetBinding(
        target_id="dynamic",
        kind="api",
        config={
            "method": "GET",
            "path": "/orders/{id}",
            "response_mode": "template",
            "response_template": '{"kind":"dynamic","id":"${path.id}"}',
        },
    ))
    static = RestApiTarget(TargetBinding(
        target_id="static",
        kind="api",
        config={
            "method": "GET",
            "path": "/orders/current",
            "response_mode": "template",
            "response_template": '{"kind":"static"}',
        },
    ))
    asyncio.run(dynamic.start("sim-dynamic", "Dynamic", []))
    asyncio.run(static.start("sim-static", "Static", []))
    try:
        assert _client().get("/sim-api/orders/current").json() == {"kind": "static"}
        assert _client().get("/sim-api/orders/A-1").json() == {"kind": "dynamic", "id": "A-1"}
    finally:
        asyncio.run(dynamic.stop())
        asyncio.run(static.stop())


def test_api_target_keeps_request_metrics_after_stop() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="metrics-api",
        kind="api",
        config={"method": "GET", "path": "/metrics", "response_mode": "template", "response_template": '{"ok":true}'},
    ))
    asyncio.run(target.start("sim-metrics", "Metrics", []))
    assert _client().get("/sim-api/metrics").status_code == 200
    asyncio.run(target.stop())
    status = target.status()
    assert status.state == "stopped"
    assert status.details["request_count"] == 1
    assert status.details["success_count"] == 1
    assert status.details["last_status_code"] == 200
    assert status.details["last_latency_ms"] is not None
    assert status.details["path"] == "/sim-api/metrics"


def test_simulation_manager_publishes_source_data_to_callable_api(tmp_path) -> None:
    async def run() -> None:
        manager = SimulationManager(tmp_path / "runtime.json")
        definition = SimulationDefinition(
            simulation_id="sim-api-e2e",
            name="API end to end",
            source=SourceBinding(
                kind="inline",
                config={"rows": [{"Temperature": 18.5}, {"Temperature": 19.25}]},
            ),
            clock=ClockSpec(mode="fixed_rate", frequency_hz=100.0),
            loop_mode="loop_forever",
            targets=[TargetBinding(
                target_id="public-api",
                kind="api",
                config={
                    "method": "GET",
                    "path": "/plant/current",
                    "response_mode": "record",
                    "fields": "Temperature",
                    "include_system_fields": False,
                },
            )],
        )
        await manager.create(definition)
        await manager.start(definition.simulation_id)
        for _ in range(100):
            if manager.status(definition.simulation_id).emitted_count:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("Simulation did not publish an API frame.")

        response = _client().get("/sim-api/plant/current")
        assert response.status_code == 200
        assert response.json()["Temperature"] in {18.5, 19.25}
        status = manager.status(definition.simulation_id)
        assert status.targets[0].kind == "api"
        assert status.targets[0].details["request_count"] == 1
        await manager.shutdown()

    asyncio.run(run())
