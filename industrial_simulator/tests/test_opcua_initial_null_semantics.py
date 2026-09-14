from __future__ import annotations

import asyncio

from app.models import ReplayConfig, TagMapping
from app.opcua_server import OpcUaTagServer
from app.simulation.interfaces.opcua_server import UnifiedOpcUaServer
from app.simulation.models import SignalDefinition


def test_mock_host_distinguishes_omitted_initial_value_from_explicit_null() -> None:
    async def scenario() -> None:
        server = OpcUaTagServer()
        server.mock_mode = True
        server.running = True
        config = ReplayConfig(
            protocol="opcua",
            tags=[
                TagMapping(csv_column="defaulted", tag_name="Defaulted", node_id="sim.defaulted", data_type="Int32"),
                TagMapping(csv_column="nullable", tag_name="Nullable", node_id="sim.nullable", data_type="Int32", initial_value=None),
            ],
        )
        await server.configure_tags(config)

        assert server.variables["sim.defaulted"]["value"] == 0
        assert server.variables["sim.nullable"]["value"] is None

    asyncio.run(scenario())


def test_unified_adapter_preserves_initial_value_field_set_intent() -> None:
    server = UnifiedOpcUaServer()
    omitted = SignalDefinition(name="Omitted", node_id="Omitted", data_type="Int32")
    explicit_null = SignalDefinition(name="Null", node_id="Null", data_type="Int32", initial_value=None)
    node_map = {"Omitted": "sim.omitted", "Null": "sim.null"}
    data_types = {"Omitted": "Int32", "Null": "Int32"}

    omitted_tag = server._tag_from_signal(omitted, node_map, data_types, set())
    null_tag = server._tag_from_signal(explicit_null, node_map, data_types, set())

    assert "initial_value" not in omitted_tag.model_fields_set
    assert "initial_value" in null_tag.model_fields_set
    assert null_tag.initial_value is None
