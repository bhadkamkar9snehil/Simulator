from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.source_simulators import get_source_simulator, list_source_simulators
from app.source_simulators.jobs import (
    list_source_jobs,
    pause_source_job,
    resume_source_job,
    start_source_job,
    stop_source_job,
)
from app.source_simulators.sap_pp import ODATA_ENTITY_PATHS

source_api_router = APIRouter(prefix="/api/source-simulators")
sap_odata_router = APIRouter(prefix="/sap/opu/odata/sap")


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail={"error": str(exc)})
    return HTTPException(status_code=400, detail={"error": str(exc)})


def _odata(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"d": {"results": rows}}


@source_api_router.get("")
def source_simulators() -> dict[str, Any]:
    return {
        "sources": [
            {
                "connector_id": source.connector_id,
                "display_name": source.display_name,
                "description": source.description,
            }
            for source in list_source_simulators()
        ]
    }


@source_api_router.get("/{connector_id}/spec")
def source_spec(connector_id: str) -> dict[str, Any]:
    try:
        return get_source_simulator(connector_id).spec()
    except Exception as exc:
        raise _error(exc)


@source_api_router.get("/{connector_id}/entities")
def source_entities(connector_id: str) -> dict[str, Any]:
    try:
        source = get_source_simulator(connector_id)
        return {"connector_id": connector_id, "entities": source.entities()}
    except Exception as exc:
        raise _error(exc)


@source_api_router.get("/{connector_id}/query")
def source_query(
    connector_id: str,
    entity: str,
    filter_text: str = Query("", alias="filter"),
    top: int | None = Query(None, ge=1),
    skip: int = Query(0, ge=0),
    watermark: str | None = None,
) -> dict[str, Any]:
    try:
        rows = get_source_simulator(connector_id).query(entity, filter_text=filter_text, top=top, skip=skip, watermark=watermark)
        return {"connector_id": connector_id, "entity": entity, "row_count": len(rows), "rows": rows}
    except Exception as exc:
        raise _error(exc)


@source_api_router.post("/{connector_id}/run-cycle")
def source_run_cycle(connector_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return get_source_simulator(connector_id).run_cycle(**(payload or {}))
    except Exception as exc:
        raise _error(exc)


@source_api_router.get("/jobs")
def source_jobs() -> dict[str, Any]:
    return {"jobs": [job.model_dump() for job in list_source_jobs()]}


@source_api_router.post("/{connector_id}/jobs")
def source_job_start(connector_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        body = payload or {}
        job = start_source_job(
            connector_id=connector_id,
            entity=str(body.get("entity") or ""),
            interval_seconds=float(body.get("interval_seconds") or 15),
            max_cycles=int(body["max_cycles"]) if body.get("max_cycles") not in (None, "") else None,
            mode=str(body.get("mode") or "query"),
            filter_text=str(body.get("filter") or body.get("filter_text") or ""),
            top=int(body["top"]) if body.get("top") not in (None, "") else None,
            watermark=str(body["watermark"]) if body.get("watermark") else None,
            cycle_parameters=body.get("cycle_parameters") or None,
        )
        return job.model_dump()
    except Exception as exc:
        raise _error(exc)


@source_api_router.post("/jobs/{job_id}/stop")
def source_job_stop(job_id: str) -> dict[str, Any]:
    try:
        return stop_source_job(job_id).model_dump()
    except Exception as exc:
        raise _error(exc)


@source_api_router.post("/jobs/{job_id}/pause")
def source_job_pause(job_id: str) -> dict[str, Any]:
    try:
        return pause_source_job(job_id).model_dump()
    except Exception as exc:
        raise _error(exc)


@source_api_router.post("/jobs/{job_id}/resume")
def source_job_resume(job_id: str) -> dict[str, Any]:
    try:
        return resume_source_job(job_id).model_dump()
    except Exception as exc:
        raise _error(exc)


@sap_odata_router.get("")
def sap_catalog() -> dict[str, Any]:
    sap_pp = get_source_simulator("sap_pp")
    return {
        "service": "Industrial Simulator SAP PP OData",
        "status": "running",
        "entitySets": [entity["path"] for entity in sap_pp.entities()],
        "testHooks": {
            "simulate_error": "?simulate_error=true",
            "simulate_latency": "?simulate_latency=<ms>",
        },
    }


@sap_odata_router.get("/{path:path}")
async def sap_odata_endpoint(path: str, request: Request) -> dict[str, Any]:
    full_path = "/sap/opu/odata/sap/" + path
    if full_path not in ODATA_ENTITY_PATHS:
        raise HTTPException(status_code=404, detail={"error": f"Unknown SAP OData endpoint: {full_path}"})
    if request.query_params.get("simulate_error") == "true":
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "SAP_SERVICE_UNAVAILABLE", "message": "Simulated SAP backend outage."}},
        )
    delay = int(request.query_params.get("simulate_latency") or 0)
    if delay > 0:
        await asyncio.sleep(min(delay, 10000) / 1000)
    try:
        top_raw = request.query_params.get("$top")
        skip_raw = request.query_params.get("$skip")
        rows = get_source_simulator("sap_pp").query(
            ODATA_ENTITY_PATHS[full_path],
            filter_text=request.query_params.get("$filter") or "",
            top=int(top_raw) if top_raw else None,
            skip=int(skip_raw) if skip_raw else 0,
        )
        return _odata(rows)
    except Exception as exc:
        raise _error(exc)
