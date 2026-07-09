from __future__ import annotations

import asyncio
import socket

import pytest

from app.models import ReplayConfig, TagMapping
from app.opcua_server import OpcUaTagServer, _patch_asyncua_python314_property_annotations


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_opcua_server_streams_updated_tag_value() -> None:
    asyncua = pytest.importorskip("asyncua")
    _patch_asyncua_python314_property_annotations()

    async def run() -> None:
        port = free_port()
        endpoint = f"opc.tcp://127.0.0.1:{port}/simulator"
        server = OpcUaTagServer(endpoint=endpoint, advertised_endpoint=endpoint)
        namespace_uri = "http://local/industrial-tag-simulator/test"
        node_id = "TagSimulator.polyester_fiber.poy_pic_307_melt_pressure_bar"
        try:
            await server.start()
            await server.configure_tags(
                ReplayConfig(
                    protocol="opcua",
                    csv_file="not_used.csv",
                    namespace_uri=namespace_uri,
                    root_folder="TagSimulator",
                    tags=[
                        TagMapping(
                            csv_column="poy_pic_307_melt_pressure_bar",
                            tag_name="poy_pic_307_melt_pressure_bar",
                            node_id=node_id,
                            data_type="Double",
                            initial_value=123.45,
                        )
                    ],
                )
            )
            await server.update_values({node_id: (127.89, "Double")})

            async with asyncua.Client(url=endpoint) as client:
                idx = await client.get_namespace_index(namespace_uri)
                root = await client.nodes.objects.get_child([f"{idx}:TagSimulator"])
                children = await root.get_children()
                browse_names = [str((await child.read_browse_name()).Name) for child in children]
                assert "TagSimulator_polyester_fiber_poy_pic_307_melt_pressure_bar" in browse_names

                variable = await root.get_child([f"{idx}:TagSimulator_polyester_fiber_poy_pic_307_melt_pressure_bar"])
                assert await variable.read_value() == 127.89
        finally:
            await server.stop()

    asyncio.run(run())
