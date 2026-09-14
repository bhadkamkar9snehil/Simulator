from __future__ import annotations

import asyncio
import datetime as dt
import socket
import uuid
from types import SimpleNamespace

import pytest

from app.models import ReplayConfig, TagMapping
from app.opcua_diagnostics import OpcUaDiagnostics
from app.opcua_server import OpcUaTagServer
from app.opcua_types import INTEGER_RANGES, coerce_value, data_value, split_type

try:
    from asyncua import Client, ua
except Exception:  # pragma: no cover
    Client = None
    ua = None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.parametrize("data_type,bounds", INTEGER_RANGES.items())
def test_integer_widths_enforce_opcua_ranges(data_type: str, bounds: tuple[int, int]) -> None:
    low, high = bounds
    assert coerce_value(data_type, str(low)) == low
    assert coerce_value(data_type, str(high)) == high
    with pytest.raises(ValueError):
        coerce_value(data_type, low - 1)
    with pytest.raises(ValueError):
        coerce_value(data_type, high + 1)


def test_arrays_dates_nulls_and_guid_are_coerced_without_type_inference() -> None:
    assert split_type("UInt16[]") == ("UInt16", True)
    assert split_type("Array[Double]") == ("Double", True)
    assert coerce_value("UInt16[]", "[0, 1, 65535]") == [0, 1, 65535]
    assert coerce_value("Double[]", "1.25,2.5") == [1.25, 2.5]
    assert coerce_value("String[]", None) is None
    assert coerce_value("Int32", None) is None

    parsed = coerce_value("DateTime", "2026-09-14T17:30:00+05:30")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == dt.timedelta(0)
    assert parsed == dt.datetime(2026, 9, 14, 12, 0, tzinfo=dt.timezone.utc)

    guid = uuid.uuid4()
    assert coerce_value("Guid", str(guid)) == guid


def test_tag_model_accepts_scalar_and_array_opcua_types_with_quality_metadata() -> None:
    tag = TagMapping(
        csv_column="values",
        tag_name="Values",
        node_id="sim.values",
        data_type="UInt32[]",
        quality="BadNoData",
        source_timestamp="2026-09-14T12:00:00Z",
    )
    assert tag.data_type == "UInt32[]"
    assert tag.quality == "BadNoData"
    with pytest.raises(ValueError):
        TagMapping(csv_column="x", tag_name="x", node_id="x", data_type="Imaginary128")


@pytest.mark.skipif(ua is None, reason="asyncua not installed")
def test_data_value_carries_explicit_variant_status_and_timestamp() -> None:
    dv = data_value("Int16[]", [1, 2, 3], "BadNoData", "2026-09-14T12:00:00Z")
    assert dv.Value.VariantType == ua.VariantType.Int16
    assert dv.Value.Value == [1, 2, 3]
    assert dv.StatusCode.is_bad()
    assert dv.SourceTimestamp == dt.datetime(2026, 9, 14, 12, 0, tzinfo=dt.timezone.utc)


@pytest.mark.asyncio
async def test_mock_server_preserves_configured_type_quality_timestamp_and_null() -> None:
    server = OpcUaTagServer()
    server.mock_mode = True
    server.running = True
    config = ReplayConfig(
        protocol="opcua",
        tags=[
            TagMapping(csv_column="a", tag_name="A", node_id="sim.a", data_type="UInt16[]", quality="Good"),
            TagMapping(csv_column="b", tag_name="B", node_id="sim.b", data_type="Int32"),
        ],
    )
    await server.configure_tags(config)
    await server.update_values({
        "sim.a": ("[1,2,65535]", "UInt16[]", "Uncertain", "2026-09-14T12:00:00Z"),
        "sim.b": (None, "Int32", "BadNoData", None),
    })
    assert server.variables["sim.a"]["value"] == [1, 2, 65535]
    assert server.variables["sim.a"]["quality"] == "Uncertain"
    assert server.variables["sim.b"]["value"] is None
    assert server.variables["sim.b"]["quality"] == "BadNoData"

    with pytest.raises(ValueError, match="Datatype change"):
        await server.update_values({"sim.b": (1.5, "Double")})


@pytest.mark.asyncio
async def test_diagnostics_counts_only_external_reads_and_writes() -> None:
    diagnostics = OpcUaDiagnostics(recent_limit=5)
    read = SimpleNamespace(NodeId="ns=2;s=A")
    write = SimpleNamespace(NodeId="ns=2;s=B", AttributeId=13)
    good = SimpleNamespace(is_bad=lambda: False, name="Good")
    bad = SimpleNamespace(is_bad=lambda: True, name="BadTypeMismatch")

    await diagnostics.on_post_read(SimpleNamespace(is_external=False, request_params=SimpleNamespace(NodesToRead=[read])))
    await diagnostics.on_post_read(SimpleNamespace(is_external=True, request_params=SimpleNamespace(NodesToRead=[read, read])))
    await diagnostics.on_post_write(SimpleNamespace(is_external=True, request_params=SimpleNamespace(NodesToWrite=[write, write]), response_params=[good, bad]))

    snapshot = diagnostics.snapshot(None)
    assert snapshot["read_requests"] == 1
    assert snapshot["read_nodes"] == 2
    assert snapshot["write_requests"] == 1
    assert snapshot["write_nodes"] == 2
    assert snapshot["failed_writes"] == 1
    assert [entry["kind"] for entry in snapshot["recent_activity"]] == ["write", "read"]


def test_diagnostics_session_snapshot_uses_asyncua_external_session_registry_shape() -> None:
    diagnostics = OpcUaDiagnostics()
    session_id = object()
    session = SimpleNamespace(
        name="UaExpert",
        session_id=session_id,
        state=SimpleNamespace(name="Activated"),
        user="Anonymous",
        session_timeout=60000,
        _last_activity=None,
    )
    subscription = SimpleNamespace(session_id=session_id)
    iserver = SimpleNamespace(
        _external_sessions={"token": session},
        subscription_service=SimpleNamespace(subscriptions={1: subscription}),
    )
    snapshot = diagnostics.snapshot(SimpleNamespace(iserver=iserver))
    assert snapshot["connected_clients"] == 1
    assert snapshot["session_count"] == 1
    assert snapshot["sessions"][0]["name"] == "UaExpert"
    assert snapshot["sessions"][0]["subscriptions"] == 1


@pytest.mark.skipif(Client is None or ua is None, reason="asyncua not installed")
def test_real_server_round_trips_explicit_types_quality_arrays_and_collects_activity() -> None:
    async def scenario() -> None:
        port = _free_port()
        endpoint = f"opc.tcp://127.0.0.1:{port}/simulator"
        server = OpcUaTagServer(endpoint=endpoint, advertised_endpoint=endpoint)
        config = ReplayConfig(
            protocol="opcua",
            namespace_uri="urn:test:fidelity",
            root_folder="Fidelity",
            tags=[
                TagMapping(csv_column="i16", tag_name="I16", node_id="sim.i16", data_type="Int16", writable=True),
                TagMapping(csv_column="u64", tag_name="U64", node_id="sim.u64", data_type="UInt64"),
                TagMapping(csv_column="arr", tag_name="Arr", node_id="sim.arr", data_type="Double[]"),
                TagMapping(csv_column="when", tag_name="When", node_id="sim.when", data_type="DateTime"),
                TagMapping(csv_column="nullable", tag_name="Nullable", node_id="sim.null", data_type="String"),
                TagMapping(csv_column="bad", tag_name="Bad", node_id="sim.bad", data_type="Double"),
            ],
        )
        await server.start()
        try:
            await server.configure_tags(config)
            await server.update_values({
                "sim.i16": (-32768, "Int16"),
                "sim.u64": (18446744073709551615, "UInt64"),
                "sim.arr": ([1.5, 2.5, 3.5], "Double[]"),
                "sim.when": ("2026-09-14T12:00:00Z", "DateTime"),
                "sim.null": (None, "String"),
                "sim.bad": (9.5, "Double", "BadNoData", "2026-09-14T12:00:00Z"),
            })

            async with Client(url=endpoint) as client:
                idx = await client.get_namespace_index("urn:test:fidelity")
                i16 = client.get_node(ua.NodeId("sim.i16", idx))
                u64 = client.get_node(ua.NodeId("sim.u64", idx))
                arr = client.get_node(ua.NodeId("sim.arr", idx))
                when = client.get_node(ua.NodeId("sim.when", idx))
                nullable = client.get_node(ua.NodeId("sim.null", idx))
                bad = client.get_node(ua.NodeId("sim.bad", idx))

                assert await i16.read_value() == -32768
                assert await u64.read_value() == 18446744073709551615
                assert await arr.read_value() == [1.5, 2.5, 3.5]
                assert await when.read_value() == dt.datetime(2026, 9, 14, 12, 0, tzinfo=dt.timezone.utc)
                assert await nullable.read_value() is None
                bad_dv = await bad.read_data_value()
                assert bad_dv.StatusCode.is_bad()
                assert bad_dv.SourceTimestamp == dt.datetime(2026, 9, 14, 12, 0, tzinfo=dt.timezone.utc)

                await i16.write_value(123)
                assert await i16.read_value() == 123
                await asyncio.sleep(0.05)

                status = server.get_status()
                diag = status["diagnostics"]
                assert status["diagnostics_available"] is True
                assert diag["connected_clients"] >= 1
                assert diag["read_requests"] >= 1
                assert diag["read_nodes"] >= 1
                assert diag["write_requests"] >= 1
                assert diag["write_nodes"] >= 1
        finally:
            await server.stop()

    asyncio.run(scenario())
