from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.simulation.models import SignalDefinition, SignalValue, SimulationFrame, TargetBinding
from app.simulation.odata import ODataTarget, entity_set, metadata, service_document


def test_odata_target_projects_and_queries_frames() -> None:
    target = ODataTarget(
        TargetBinding(
            target_id="sap",
            kind="odata",
            config={"entity": "ProductionOrders", "max_rows": 2},
        )
    )
    schema = [
        SignalDefinition(name="OrderId", node_id="OrderId", data_type="String"),
        SignalDefinition(name="Yield", node_id="Yield", data_type="Double"),
    ]

    async def exercise() -> None:
        await target.start("plant_a", "Plant A", schema)
        for sequence, order_id in enumerate(("PO-1", "PO-2", "PO-3"), start=1):
            await target.publish(
                SimulationFrame(
                    simulation_id="plant_a",
                    sequence=sequence,
                    timestamp=f"2026-09-13T05:00:0{sequence}Z",
                    values={
                        "OrderId": SignalValue(value=order_id, data_type="String"),
                        "Yield": SignalValue(value=sequence * 10.0, data_type="Double"),
                    },
                    context={"Plant": "1001"},
                )
            )

        document = service_document("plant_a", "sap")
        assert document["value"][0]["name"] == "ProductionOrders"

        rows = entity_set(
            "plant_a",
            "sap",
            "ProductionOrders",
            top=None,
            skip=0,
            select="OrderId,Yield",
            filter_text="OrderId eq 'PO-3'",
        )["value"]
        assert rows == [{"OrderId": "PO-3", "Yield": 30.0}]

        response = metadata("plant_a", "sap")
        text = response.body.decode("utf-8")
        assert 'EntitySet Name="ProductionOrders"' in text
        assert 'Property Name="Yield" Type="Edm.Double"' in text

        status = target.status()
        assert status.state == "running"
        assert status.details["row_count"] == 2
        await target.stop()

    asyncio.run(exercise())

    with pytest.raises(HTTPException) as exc:
        service_document("plant_a", "sap")
    assert exc.value.status_code == 404


def test_odata_target_rejects_dedicated_hosting() -> None:
    target = ODataTarget(TargetBinding(target_id="odata", kind="odata", hosting_mode="dedicated"))

    async def exercise() -> None:
        with pytest.raises(ValueError, match="shared Industrial HTTP host"):
            await target.start("sim", "Simulation", [])

    asyncio.run(exercise())
