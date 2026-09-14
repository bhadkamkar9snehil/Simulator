from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.models import ReplayConfig, TagMapping
from app import opcua_server


class _FakeVariable:
    def __init__(self) -> None:
        self.writable = False

    async def set_writable(self) -> None:
        self.writable = True


class _FakeFolder:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str, object]] = []

    async def add_variable(self, node_id: object, browse_name: str, value: object) -> _FakeVariable:
        self.calls.append((node_id, browse_name, value))
        return _FakeVariable()


class _FakeObjects:
    def __init__(self, folder: _FakeFolder) -> None:
        self.folder = folder

    async def add_folder(self, namespace_index: int, browse_name: str) -> _FakeFolder:
        assert namespace_index == 7
        assert browse_name == "PlantA"
        return self.folder


class _FakeServer:
    def __init__(self, folder: _FakeFolder) -> None:
        self.nodes = SimpleNamespace(objects=_FakeObjects(folder))

    async def register_namespace(self, uri: str) -> int:
        assert uri == "urn:test:plant-a"
        return 7


class _FakeUa:
    @staticmethod
    def NodeId(identifier: str, namespace_index: int) -> tuple[str, int]:
        return identifier, namespace_index


def _config(*node_ids: str) -> ReplayConfig:
    return ReplayConfig(
        protocol="opcua",
        namespace_uri="urn:test:plant-a",
        root_folder="PlantA",
        node_id_prefix="PlantA",
        tags=[
            TagMapping(
                csv_column=f"col-{index}",
                tag_name=f"Tag {index}",
                node_id=node_id,
                data_type="Double",
            )
            for index, node_id in enumerate(node_ids)
        ],
    )


def test_configured_string_node_id_is_passed_to_asyncua(monkeypatch) -> None:
    folder = _FakeFolder()
    server = opcua_server.OpcUaTagServer()
    server.mock_mode = False
    server.server = _FakeServer(folder)
    monkeypatch.setattr(opcua_server, "ua", _FakeUa)

    asyncio.run(server._configure_tags_impl(_config("Line1.Pressure", "Line1.Flow")))

    assert [call[0] for call in folder.calls] == [
        ("Line1.Pressure", 7),
        ("Line1.Flow", 7),
    ]
    assert set(server.variables) == {"Line1.Pressure", "Line1.Flow"}


def test_duplicate_configured_node_ids_are_rejected() -> None:
    server = opcua_server.OpcUaTagServer()
    try:
        asyncio.run(server._configure_tags_impl(_config("Duplicate", "Duplicate")))
    except ValueError as exc:
        assert "unique NodeIds" in str(exc)
    else:
        raise AssertionError("Duplicate OPC UA NodeIds should fail validation.")
