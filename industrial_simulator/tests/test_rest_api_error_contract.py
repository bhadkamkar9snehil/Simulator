from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.simulation.interfaces.rest_api import RestApiTarget, router
from app.simulation.models import TargetBinding


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_custom_json_error_uses_error_and_request_tokens() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="custom-json-error",
        kind="api",
        config={
            "method": "GET",
            "path": "/contract",
            "required_request_values": "query.site=plant-a",
            "request_error_status": 422,
            "error_mode": "json",
            "error_template": '{"code":"SIM-${error.status}","message":"${error.message}","site":"${query.site}"}',
            "response_headers": "X-Simulated-Status: ${error.status}",
        },
    ))
    asyncio.run(target.start("sim-error", "Error contract", []))
    try:
        response = _client().get("/sim-api/contract?site=plant-b")
        assert response.status_code == 422
        assert response.json() == {
            "code": "SIM-422",
            "message": "Required request value invalid: query.site",
            "site": "plant-b",
        }
        assert response.headers["X-Simulated-Status"] == "422"
    finally:
        asyncio.run(target.stop())


def test_custom_text_error_can_impersonate_text_api() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="custom-text-error",
        kind="api",
        config={
            "method": "GET",
            "path": "/text-error",
            "response_mode": "record",
            "empty_status_code": 503,
            "error_mode": "text",
            "error_media_type": "text/plain",
            "error_text_template": "ERR ${error.status}: ${error.message}",
        },
    ))
    asyncio.run(target.start("sim-error", "Error contract", []))
    try:
        response = _client().get("/sim-api/text-error")
        assert response.status_code == 503
        assert response.text == "ERR 503: Simulation has not published data yet."
        assert response.headers["content-type"].startswith("text/plain")
    finally:
        asyncio.run(target.stop())


def test_custom_empty_error_returns_no_body() -> None:
    target = RestApiTarget(TargetBinding(
        target_id="custom-empty-error",
        kind="api",
        config={
            "method": "GET",
            "path": "/empty-error/{id}",
            "selection_mode": "history_match",
            "match_frame": "values.Id",
            "match_request": "path.id",
            "not_found_status": 404,
            "error_mode": "empty",
        },
    ))
    asyncio.run(target.start("sim-error", "Error contract", []))
    try:
        response = _client().get("/sim-api/empty-error/missing")
        assert response.status_code == 404
        assert response.content == b""
    finally:
        asyncio.run(target.stop())
