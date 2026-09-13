from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Query, Response

from .models import SignalDefinition, SimulationFrame, TargetBinding, TargetRuntimeStatus

router = APIRouter(prefix="/api/v2/odata", tags=["Unified OData"])


@dataclass
class ODataProjection:
    simulation_id: str
    target_id: str
    entity_name: str
    schema: list[SignalDefinition]
    max_rows: int
    rows: deque[dict[str, Any]] = field(init=False)

    def __post_init__(self) -> None:
        self.rows = deque(maxlen=self.max_rows)

    def append(self, frame: SimulationFrame) -> None:
        row: dict[str, Any] = {
            "Sequence": frame.sequence,
            "Timestamp": frame.timestamp,
            "SimulationId": frame.simulation_id,
        }
        row.update(frame.context)
        row.update({name: signal.value for name, signal in frame.values.items()})
        self.rows.append(row)


class ODataRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ODataProjection] = {}

    def register(
        self,
        simulation_id: str,
        target_id: str,
        entity_name: str,
        schema: list[SignalDefinition],
        max_rows: int,
    ) -> ODataProjection:
        projection = ODataProjection(simulation_id, target_id, entity_name, schema, max_rows)
        self._items[(simulation_id, target_id)] = projection
        return projection

    def remove(self, simulation_id: str, target_id: str) -> None:
        self._items.pop((simulation_id, target_id), None)

    def get(self, simulation_id: str, target_id: str) -> ODataProjection:
        projection = self._items.get((simulation_id, target_id))
        if projection is None:
            raise KeyError(target_id)
        return projection


odata_registry = ODataRegistry()


class ODataTarget:
    def __init__(self, binding: TargetBinding):
        self.target_id = binding.target_id
        self.binding = binding
        self._state = "created"
        self._simulation_id = ""
        self._projection: ODataProjection | None = None
        self._endpoint: str | None = None

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None:
        if self.binding.hosting_mode != "shared":
            raise ValueError("OData target currently uses the shared Industrial HTTP host.")
        entity_name = _entity_name(str(self.binding.config.get("entity", "SimulationData")))
        max_rows = int(self.binding.config.get("max_rows", 1000))
        if max_rows < 1:
            raise ValueError("OData target max_rows must be at least 1.")
        self._simulation_id = simulation_id
        self._projection = odata_registry.register(simulation_id, self.target_id, entity_name, schema, max_rows)
        self._endpoint = f"/api/v2/odata/{simulation_id}/{self.target_id}/{entity_name}"
        self._state = "running"

    async def publish(self, frame: SimulationFrame) -> None:
        if self._projection is None:
            raise RuntimeError("OData target is not started.")
        self._projection.append(frame)

    async def stop(self) -> None:
        if self._simulation_id:
            odata_registry.remove(self._simulation_id, self.target_id)
        self._projection = None
        self._state = "stopped"

    def status(self) -> TargetRuntimeStatus:
        return TargetRuntimeStatus(
            target_id=self.target_id,
            kind="odata",
            state=self._state,  # type: ignore[arg-type]
            endpoint=self._endpoint,
            details={"row_count": len(self._projection.rows) if self._projection else 0},
        )


def _projection(simulation_id: str, target_id: str) -> ODataProjection:
    try:
        return odata_registry.get(simulation_id, target_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"OData target not found: {target_id}") from exc


@router.get("/{simulation_id}/{target_id}")
def service_document(simulation_id: str, target_id: str) -> dict[str, Any]:
    projection = _projection(simulation_id, target_id)
    return {
        "@odata.context": f"/api/v2/odata/{simulation_id}/{target_id}/$metadata",
        "value": [{"name": projection.entity_name, "kind": "EntitySet", "url": projection.entity_name}],
    }


@router.get("/{simulation_id}/{target_id}/$metadata")
def metadata(simulation_id: str, target_id: str) -> Response:
    projection = _projection(simulation_id, target_id)
    properties = [
        '<Property Name="Sequence" Type="Edm.Int64" Nullable="false"/>',
        '<Property Name="Timestamp" Type="Edm.String"/>',
        '<Property Name="SimulationId" Type="Edm.String"/>',
    ]
    properties.extend(
        f'<Property Name="{escape(signal.name)}" Type="{_edm_type(signal.data_type)}"/>'
        for signal in projection.schema
    )
    entity = escape(projection.entity_name)
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">'
        '<edmx:DataServices><Schema Namespace="Simulator" xmlns="http://docs.oasis-open.org/odata/ns/edm">'
        f'<EntityType Name="{entity}"><Key><PropertyRef Name="Sequence"/></Key>{"".join(properties)}</EntityType>'
        f'<EntityContainer Name="Container"><EntitySet Name="{entity}" EntityType="Simulator.{entity}"/></EntityContainer>'
        '</Schema></edmx:DataServices></edmx:Edmx>'
    )
    return Response(content=xml, media_type="application/xml")


@router.get("/{simulation_id}/{target_id}/{entity_name}")
def entity_set(
    simulation_id: str,
    target_id: str,
    entity_name: str,
    top: int | None = Query(default=None, alias="$top", ge=0),
    skip: int = Query(default=0, alias="$skip", ge=0),
    select: str = Query(default="", alias="$select"),
    filter_text: str = Query(default="", alias="$filter"),
) -> dict[str, Any]:
    projection = _projection(simulation_id, target_id)
    if entity_name != projection.entity_name:
        raise HTTPException(status_code=404, detail=f"Entity set not found: {entity_name}")
    rows = list(projection.rows)
    if filter_text:
        rows = _apply_filter(rows, filter_text)
    if skip:
        rows = rows[skip:]
    if top is not None:
        rows = rows[:top]
    fields = [item.strip() for item in select.split(",") if item.strip()]
    if fields:
        rows = [{key: row.get(key) for key in fields if key in row} for row in rows]
    return {
        "@odata.context": f"/api/v2/odata/{simulation_id}/{target_id}/$metadata#{projection.entity_name}",
        "value": rows,
    }


def _apply_filter(rows: list[dict[str, Any]], filter_text: str) -> list[dict[str, Any]]:
    match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+eq\s+(.+?)\s*", filter_text)
    if not match:
        raise HTTPException(status_code=400, detail="Only simple OData equality filters are supported.")
    field, raw_value = match.groups()
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        value = value[1:-1].replace("''", "'")
    return [row for row in rows if str(row.get(field, "")) == value]


def _entity_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value.strip())
    if not cleaned:
        return "SimulationData"
    if cleaned[0].isdigit():
        cleaned = f"Entity_{cleaned}"
    return cleaned


def _edm_type(data_type: str) -> str:
    return {
        "Double": "Edm.Double",
        "Int64": "Edm.Int64",
        "Boolean": "Edm.Boolean",
        "String": "Edm.String",
    }.get(data_type, "Edm.String")
