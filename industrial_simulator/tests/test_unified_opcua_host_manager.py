from __future__ import annotations

import asyncio

from app.simulation.interfaces import opcua as opcua_module
from app.simulation.models import SignalDefinition, SignalValue, SimulationFrame, TargetBinding


class _FakeOpcUaServer:
    instances: list["_FakeOpcUaServer"] = []

    def __init__(
        self,
        endpoint: str | None = None,
        advertised_endpoint: str | None = None,
        server_options: dict | None = None,
    ):
        self.endpoint = endpoint or "opc.tcp://0.0.0.0:4840/simulator"
        self.advertised_endpoint = advertised_endpoint or "opc.tcp://localhost:4840/simulator"
        self.server_options = dict(server_options or {})
        self.running = False
        self.mock_mode = True
        self.server = None
        self.variables: dict[str, dict] = {}
        self.start_count = 0
        self.stop_count = 0
        self.configured = None
        _FakeOpcUaServer.instances.append(self)

    async def start(self) -> None:
        if not self.running:
            self.start_count += 1
            self.running = True

    async def stop(self) -> None:
        if self.running:
            self.stop_count += 1
        self.running = False

    async def configure_tags(self, config) -> None:
        self.configured = config
        for tag in config.tags:
            self.variables[tag.node_id] = {"value": tag.initial_value, "tag": tag}

    async def update_values(self, values) -> None:
        for node_id, (value, _data_type) in values.items():
            if node_id in self.variables:
                self.variables[node_id]["value"] = value

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "endpoint": self.advertised_endpoint,
            "security_policy": self.server_options.get("security_policy", "none"),
            "authentication": self.server_options.get("authentication", "anonymous"),
        }

    def get_endpoint(self) -> str:
        return self.advertised_endpoint


SCHEMA = [
    SignalDefinition(name="pressure", node_id="pressure", data_type="Double", writable=True),
    SignalDefinition(name="running", node_id="running", data_type="Boolean"),
]


def _fake_runtime(monkeypatch) -> None:
    _FakeOpcUaServer.instances.clear()
    monkeypatch.setattr(opcua_module, "OpcUaTagServer", _FakeOpcUaServer)
    monkeypatch.setattr(opcua_module, "Server", object())


def _shared_binding(target_id: str = "opcua", port: int = 4840) -> TargetBinding:
    return TargetBinding(
        target_id=target_id,
        kind="opcua",
        hosting_mode="shared",
        config={
            "bind_host": "0.0.0.0",
            "advertised_host": "localhost",
            "port": port,
            "path": "simulator",
            "namespace_uri": "http://local/unified-simulator",
            "root_folder": "Simulations",
            "security_policy": "none",
            "authentication": "anonymous",
        },
    )


def _dedicated_binding(target_id: str = "opcua", port: int = 4842) -> TargetBinding:
    return TargetBinding(
        target_id=target_id,
        kind="opcua",
        hosting_mode="dedicated",
        config={
            "bind_host": "127.0.0.1",
            "advertised_host": "test-host",
            "port": port,
            "path": "line-a",
            "security_policy": "none",
            "authentication": "anonymous",
        },
    )


def test_shared_host_add_remove_does_not_restart_other_simulations(monkeypatch) -> None:
    _fake_runtime(monkeypatch)
    manager = opcua_module.InterfaceHostManager()

    async def exercise() -> None:
        first = await manager.acquire_opcua("sim-a", "Simulation A", _shared_binding(), SCHEMA)
        second = await manager.acquire_opcua("sim-b", "Simulation B", _shared_binding(), SCHEMA)

        assert first.server is second.server
        assert first.member_key == "sim-a/opcua"
        assert second.member_key == "sim-b/opcua"
        assert first.server.start_count == 1
        assert first.server.stop_count == 0

        status = manager.status()["shared_opcua_hosts"]["0.0.0.0:4840"]
        assert status["simulation_count"] == 2
        assert status["target_count"] == 2
        assert status["tag_count"] == 4
        assert status["writable_count"] == 2

        await manager.publish_opcua(
            first,
            SimulationFrame(
                simulation_id="sim-a",
                values={"pressure": SignalValue(value=12.5, data_type="Double")},
            ),
        )
        assert first.server.variables[first.node_map["pressure"]]["value"] == 12.5

        await manager.release_opcua(first)
        assert first.server.running is True
        assert first.server.stop_count == 0
        remaining = manager.status()["shared_opcua_hosts"]["0.0.0.0:4840"]
        assert remaining["simulation_count"] == 1
        assert remaining["simulation_targets"][0]["simulation_id"] == "sim-b"
        assert all(not key.startswith("sim-a.") for key in first.server.variables)

        await manager.release_opcua(second)
        assert first.server.stop_count == 1
        assert manager.status()["shared_opcua_hosts"] == {}

    asyncio.run(exercise())


def test_same_target_id_is_scoped_per_simulation(monkeypatch) -> None:
    _fake_runtime(monkeypatch)
    manager = opcua_module.InterfaceHostManager()

    async def exercise() -> None:
        first = await manager.acquire_opcua("sim-a", "Simulation A", _shared_binding("primary"), SCHEMA)
        second = await manager.acquire_opcua("sim-b", "Simulation B", _shared_binding("primary"), SCHEMA)
        assert first.member_key != second.member_key
        assert set(manager.status()["shared_opcua_hosts"]["0.0.0.0:4840"]["simulation_targets"][0]) >= {
            "member_key",
            "simulation_id",
            "target_id",
            "tag_count",
            "folder",
            "writable_count",
        }
        await manager.shutdown()

    asyncio.run(exercise())


def test_shared_listener_rejects_conflicting_host_level_settings(monkeypatch) -> None:
    _fake_runtime(monkeypatch)
    manager = opcua_module.InterfaceHostManager()

    async def exercise() -> None:
        first = await manager.acquire_opcua("sim-a", "Simulation A", _shared_binding(), SCHEMA)
        conflicting = _shared_binding("other")
        conflicting.config["root_folder"] = "DifferentRoot"
        try:
            await manager.acquire_opcua("sim-b", "Simulation B", conflicting, SCHEMA)
        except ValueError as exc:
            assert "Shared OPC UA listener settings conflict" in str(exc)
        else:
            raise AssertionError("Expected shared host configuration conflict")
        assert first.server.running is True
        assert first.server.stop_count == 0
        await manager.shutdown()

    asyncio.run(exercise())


def test_shared_listener_rejects_conflicting_security(monkeypatch) -> None:
    _fake_runtime(monkeypatch)
    manager = opcua_module.InterfaceHostManager()

    async def exercise() -> None:
        first = await manager.acquire_opcua("sim-a", "Simulation A", _shared_binding(), SCHEMA)
        conflicting = _shared_binding("secure")
        conflicting.config["security_policy"] = "basic256sha256_sign_encrypt"
        try:
            await manager.acquire_opcua("sim-b", "Simulation B", conflicting, SCHEMA)
        except ValueError as exc:
            assert "security_policy" in str(exc)
        else:
            raise AssertionError("Expected shared security configuration conflict")
        assert first.server.running is True
        await manager.shutdown()

    asyncio.run(exercise())


def test_shared_listener_uses_custom_prefix_and_group_folder(monkeypatch) -> None:
    _fake_runtime(monkeypatch)
    manager = opcua_module.InterfaceHostManager()

    async def exercise() -> None:
        binding = _shared_binding()
        binding.config["node_id_prefix"] = "Plant1.Line2"
        binding.config["group_folder"] = "{simulation_name}-{target_id}"
        handle = await manager.acquire_opcua("sim-a", "Mixer A", binding, SCHEMA)
        assert handle.node_map["pressure"] == "Plant1.Line2.pressure"
        assert handle.folder_name == "Mixer_A-opcua"
        assert handle.writable_count == 1
        await manager.shutdown()

    asyncio.run(exercise())


def test_username_authentication_is_passed_to_server(monkeypatch) -> None:
    _fake_runtime(monkeypatch)
    manager = opcua_module.InterfaceHostManager()

    async def exercise() -> None:
        binding = _dedicated_binding()
        binding.config.update({
            "security_policy": "basic256sha256_sign_encrypt",
            "authentication": "username",
            "username": "operator",
            "password": "sim-password",
        })
        handle = await manager.acquire_opcua("sim-a", "Simulation A", binding, SCHEMA)
        assert handle.server.server_options["security_policy"] == "basic256sha256_sign_encrypt"
        assert handle.server.server_options["authentication"] == "username"
        assert handle.server.server_options["username"] == "operator"
        assert handle.server.server_options["password"] == "sim-password"
        status = manager.status()["dedicated_opcua_hosts"]["sim-a/opcua"]
        assert status["security_policy"] == "basic256sha256_sign_encrypt"
        assert status["authentication"] == "username"
        await manager.shutdown()

    asyncio.run(exercise())


def test_shared_listener_rejects_different_path_on_same_port(monkeypatch) -> None:
    _fake_runtime(monkeypatch)
    manager = opcua_module.InterfaceHostManager()

    async def exercise() -> None:
        await manager.acquire_opcua("sim-a", "Simulation A", _shared_binding(), SCHEMA)
        conflicting = _shared_binding("other")
        conflicting.config["path"] = "another-endpoint"
        try:
            await manager.acquire_opcua("sim-b", "Simulation B", conflicting, SCHEMA)
        except ValueError as exc:
            assert "Shared OPC UA listener settings conflict" in str(exc)
        else:
            raise AssertionError("Expected shared listener path conflict")
        await manager.shutdown()

    asyncio.run(exercise())


def test_dedicated_targets_honor_bind_host(monkeypatch) -> None:
    _fake_runtime(monkeypatch)
    manager = opcua_module.InterfaceHostManager()

    async def exercise() -> None:
        handle = await manager.acquire_opcua("sim-a", "Simulation A", _dedicated_binding(), SCHEMA)
        assert handle.server.endpoint == "opc.tcp://127.0.0.1:4842/line-a"
        assert handle.server.get_endpoint() == "opc.tcp://test-host:4842/line-a"
        assert handle.member_key == "sim-a/opcua"
        await manager.release_opcua(handle)

    asyncio.run(exercise())


def test_dedicated_targets_cannot_reserve_same_port_twice(monkeypatch) -> None:
    _fake_runtime(monkeypatch)
    manager = opcua_module.InterfaceHostManager()

    async def exercise() -> None:
        first = await manager.acquire_opcua("sim-a", "Simulation A", _dedicated_binding("opcua-a", 4842), SCHEMA)
        try:
            await manager.acquire_opcua("sim-b", "Simulation B", _dedicated_binding("opcua-b", 4842), SCHEMA)
        except ValueError as exc:
            assert "already reserved" in str(exc)
        else:
            raise AssertionError("Expected duplicate dedicated port reservation to fail")
        assert first.server.running is True
        await manager.release_opcua(first)

    asyncio.run(exercise())


def test_shared_and_dedicated_targets_cannot_share_port(monkeypatch) -> None:
    _fake_runtime(monkeypatch)
    manager = opcua_module.InterfaceHostManager()

    async def exercise() -> None:
        shared = await manager.acquire_opcua("sim-a", "Simulation A", _shared_binding(port=4840), SCHEMA)
        try:
            await manager.acquire_opcua("sim-b", "Simulation B", _dedicated_binding("dedicated", 4840), SCHEMA)
        except ValueError as exc:
            assert "shared listener" in str(exc)
        else:
            raise AssertionError("Expected shared/dedicated port reservation conflict")
        await manager.release_opcua(shared)

    asyncio.run(exercise())
