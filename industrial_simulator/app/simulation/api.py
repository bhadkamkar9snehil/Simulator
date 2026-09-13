from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse

from .models import SimulationDefinition, SimulationStatus, WorldDefinition
from .preview import preview_definition
from .runtime import simulation_manager

router = APIRouter(prefix="/api/v2", tags=["Unified simulations"])
T = TypeVar("T")


async def _call(action: Callable[..., Awaitable[T]], *args: Any) -> T:
    try:
        return await action(*args)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Resource not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _read(action: Callable[..., T], *args: Any) -> T:
    try:
        return action(*args)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Resource not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    return {
        "sources": {
            "implemented": ["csv", "dataset", "generator", "source_simulator", "sap_pp", "lims_odbc", "inline"],
            "planned": ["sql", "http", "recorded_opcua", "recorded_mqtt"],
            "dataset_storage": ["csv", "xlsx", "parquet", "parquet_folder"],
        },
        "targets": {
            "implemented": ["opcua", "mqtt", "http", "sql_server", "odata", "memory"],
            "planned": ["modbus_tcp", "kafka"],
        },
        "hosting_modes": ["shared", "dedicated"],
        "loop_modes": ["once", "loop_forever", "hold_last", "ping_pong"],
        "clock_modes": ["fixed_rate", "source_timestamp"],
        "failure_policies": ["continue", "retry", "stop_simulation"],
        "overflow_policies": ["block", "drop_oldest", "drop_newest"],
    }


@router.get("/runtime")
def runtime_snapshot() -> dict[str, Any]:
    return simulation_manager.runtime_snapshot().model_dump()


@router.get("/interfaces")
def interface_status() -> dict[str, Any]:
    return simulation_manager.interface_status()


@router.get("/simulations")
def list_simulations() -> list[dict[str, Any]]:
    definitions = {item.simulation_id: item for item in simulation_manager.list_definitions()}
    return [
        {
            "definition": definitions[status_item.simulation_id].model_dump(),
            "status": status_item.model_dump(),
        }
        for status_item in simulation_manager.list_status()
    ]


@router.post("/simulations/preview")
async def preview_simulation(definition: SimulationDefinition) -> dict[str, Any]:
    return await _call(preview_definition, definition)


@router.post("/simulations", response_model=SimulationStatus, status_code=status.HTTP_201_CREATED)
async def create_simulation(definition: SimulationDefinition) -> SimulationStatus:
    return await _call(simulation_manager.create, definition)


@router.get("/simulations/{simulation_id}")
def get_simulation(simulation_id: str) -> dict[str, Any]:
    return {
        "definition": _read(simulation_manager.get_definition, simulation_id).model_dump(),
        "status": _read(simulation_manager.status, simulation_id).model_dump(),
    }


@router.put("/simulations/{simulation_id}", response_model=SimulationStatus)
async def replace_simulation(simulation_id: str, definition: SimulationDefinition) -> SimulationStatus:
    return await _call(simulation_manager.replace, simulation_id, definition)


@router.delete("/simulations/{simulation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_simulation(simulation_id: str) -> Response:
    await _call(simulation_manager.delete, simulation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/simulations/{simulation_id}/start", response_model=SimulationStatus)
async def start_simulation(simulation_id: str) -> SimulationStatus:
    return await _call(simulation_manager.start, simulation_id)


@router.post("/simulations/{simulation_id}/pause", response_model=SimulationStatus)
async def pause_simulation(simulation_id: str) -> SimulationStatus:
    return await _call(simulation_manager.pause, simulation_id)


@router.post("/simulations/{simulation_id}/resume", response_model=SimulationStatus)
async def resume_simulation(simulation_id: str) -> SimulationStatus:
    return await _call(simulation_manager.resume, simulation_id)


@router.post("/simulations/{simulation_id}/stop", response_model=SimulationStatus)
async def stop_simulation(simulation_id: str) -> SimulationStatus:
    return await _call(simulation_manager.stop, simulation_id)


@router.get("/simulations/{simulation_id}/snapshot")
def simulation_snapshot(simulation_id: str) -> dict[str, Any]:
    return _read(simulation_manager.snapshot, simulation_id)


@router.get("/simulations/{simulation_id}/targets/{target_id}")
def http_target_snapshot(simulation_id: str, target_id: str) -> dict[str, Any]:
    frame = _read(simulation_manager.http_frame, simulation_id, target_id)
    return {
        "simulation_id": simulation_id,
        "target_id": target_id,
        "frame": frame.model_dump() if frame is not None else None,
    }


@router.get("/simulations/{simulation_id}/targets/{target_id}/ndjson")
def http_target_ndjson(
    simulation_id: str,
    target_id: str,
    interval_ms: int = 250,
    limit: int | None = None,
) -> StreamingResponse:
    _read(simulation_manager.http_frame, simulation_id, target_id)
    return StreamingResponse(
        _http_frame_stream(simulation_id, target_id, interval_ms, limit, sse=False),
        media_type="application/x-ndjson",
    )


@router.get("/simulations/{simulation_id}/targets/{target_id}/sse")
def http_target_sse(
    simulation_id: str,
    target_id: str,
    interval_ms: int = 250,
    limit: int | None = None,
) -> StreamingResponse:
    _read(simulation_manager.http_frame, simulation_id, target_id)
    return StreamingResponse(
        _http_frame_stream(simulation_id, target_id, interval_ms, limit, sse=True),
        media_type="text/event-stream",
    )


@router.websocket("/simulations/{simulation_id}/targets/{target_id}/ws")
async def http_target_websocket(websocket: WebSocket, simulation_id: str, target_id: str) -> None:
    try:
        _read(simulation_manager.http_frame, simulation_id, target_id)
    except HTTPException:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    last_sequence: int | None = None
    try:
        while True:
            frame = simulation_manager.http_frame(simulation_id, target_id)
            if frame is not None and frame.sequence != last_sequence:
                await websocket.send_json(frame.model_dump())
                last_sequence = frame.sequence
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return


async def _http_frame_stream(
    simulation_id: str,
    target_id: str,
    interval_ms: int,
    limit: int | None,
    *,
    sse: bool,
) -> AsyncIterator[bytes]:
    interval = max(50, interval_ms) / 1000.0
    sent = 0
    last_sequence: int | None = None
    while limit is None or sent < limit:
        frame = simulation_manager.http_frame(simulation_id, target_id)
        if frame is not None and frame.sequence != last_sequence:
            payload = json.dumps(frame.model_dump(), default=str, separators=(",", ":"))
            if sse:
                yield f"id: {frame.sequence}\nevent: simulation.frame\ndata: {payload}\n\n".encode("utf-8")
            else:
                yield (payload + "\n").encode("utf-8")
            last_sequence = frame.sequence
            sent += 1
        await asyncio.sleep(interval)


@router.get("/worlds")
def list_worlds() -> list[WorldDefinition]:
    return list(simulation_manager.worlds.values())


@router.post("/worlds", response_model=WorldDefinition, status_code=status.HTTP_201_CREATED)
async def create_world(world: WorldDefinition) -> WorldDefinition:
    return await _call(simulation_manager.create_world, world)


@router.get("/worlds/{world_id}", response_model=WorldDefinition)
def get_world(world_id: str) -> WorldDefinition:
    world = simulation_manager.worlds.get(world_id)
    if world is None:
        raise HTTPException(status_code=404, detail=f"Resource not found: {world_id}")
    return world


@router.put("/worlds/{world_id}", response_model=WorldDefinition)
async def replace_world(world_id: str, world: WorldDefinition) -> WorldDefinition:
    return await _call(simulation_manager.replace_world, world_id, world)


@router.delete("/worlds/{world_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_world(world_id: str) -> Response:
    await _call(simulation_manager.delete_world, world_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/worlds/{world_id}/start", response_model=list[SimulationStatus])
async def start_world(world_id: str) -> list[SimulationStatus]:
    return await _call(simulation_manager.start_world, world_id)


@router.post("/worlds/{world_id}/stop", response_model=list[SimulationStatus])
async def stop_world(world_id: str) -> list[SimulationStatus]:
    return await _call(simulation_manager.stop_world, world_id)
