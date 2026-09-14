from __future__ import annotations

import asyncio

from app.simulation.interfaces import opcua as opcua_module
from app.simulation.models import ClockSpec, SignalDefinition, SignalValue, SimulationDefinition, SimulationFrame, SourceBinding, TargetBinding
from app.simulation.runtime import SimulationManager


class _FakeOpcUaServer:
    instances: list["_FakeOpcUaServer"] = []

    def __init__(self, endpoint=None, advertised_endpoint=None, server_options=None):
        self.endpoint = endpoint
        self.advertised_endpoint = advertised_endpoint
        self.server_options = dict(server_options or {})
        self.running = False
        self.mock_mode = True
        self.server = None
        self.variables = {}
        self.start_count = 0
        self.stop_count = 0
        _FakeOpcUaServer.instances.append(self)

    async def start(self):
        if not self.running:
            self.running = True
            self.start_count += 1

    async def stop(self):
        if self.running:
            self.stop_count += 1
        self.running = False
        self.variables.clear()

    async def configure_signals(self, namespace_uri, root_folder, schema, node_map, data_types, writable):
        for signal in schema:
            self.variables[node_map[signal.name]] = {"value": signal.initial_value}

    async def update_signals(self, values):
        for node_id, (value, _data_type, _quality, _source_timestamp) in values.items():
            if node_id in self.variables:
                self.variables[node_id]["value"] = value

    def get_status(self):
        return {
            "running": self.running,
            "endpoint": self.advertised_endpoint,
            "security_policy": self.server_options.get("security_policy", "none"),
            "authentication": self.server_options.get("authentication", "anonymous"),
        }

    def get_endpoint(self):
        return self.advertised_endpoint


class _FailFirstStartServer(_FakeOpcUaServer):
    should_fail = True

    async def start(self):
        if self.running:
            return
        self.start_count += 1
        if type(self).should_fail:
            type(self).should_fail = False
            await asyncio.sleep(0)
            raise RuntimeError("intentional first start failure")
        self.running = True


def _binding() -> TargetBinding:
    return TargetBinding(
        target_id="opcua",
        kind="opcua",
        hosting_mode="shared",
        failure_policy="stop_simulation",
        config={
            "bind_host": "0.0.0.0",
            "advertised_host": "localhost",
            "port": 4840,
            "path": "simulator",
            "namespace_uri": "http://local/unified-simulator",
            "root_folder": "Simulations",
        },
    )


def _dedicated_binding(port: int) -> TargetBinding:
    return TargetBinding(
        target_id="opcua",
        kind="opcua",
        hosting_mode="dedicated",
        failure_policy="stop_simulation",
        config={
            "bind_host": "127.0.0.1",
            "advertised_host": "localhost",
            "port": port,
            "path": f"sim-{port}",
            "namespace_uri": f"http://local/unified-simulator/{port}",
            "root_folder": f"Simulation{port}",
        },
    )


def _definition(simulation_id: str, start: int, target: TargetBinding | None = None) -> SimulationDefinition:
    return SimulationDefinition(
        simulation_id=simulation_id,
        name=simulation_id,
        source=SourceBinding(
            kind="inline",
            config={"rows": [{"value": start}, {"value": start + 1}, {"value": start + 2}]},
        ),
        clock=ClockSpec(frequency_hz=20.0),
        loop_mode="loop_forever",
        targets=[target or _binding()],
    )


async def _wait_for(predicate, message: str) -> None:
    for _ in range(300):
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError(message)


def test_shared_opcua_simulations_have_independent_lifecycle_controls(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(opcua_module, "OpcUaTagServer", _FakeOpcUaServer)
    monkeypatch.setattr(opcua_module, "Server", object())
    _FakeOpcUaServer.instances.clear()

    async def run() -> None:
        manager = SimulationManager(tmp_path / "runtime.json")
        await manager.create(_definition("sim-a", 10))
        await manager.create(_definition("sim-b", 100))

        await asyncio.gather(manager.start("sim-a"), manager.start("sim-b"))
        await _wait_for(
            lambda: manager.hosts.status()["shared_opcua_hosts"].get("0.0.0.0:4840", {}).get("target_count") == 2,
            "both simulations did not join the shared OPC UA host",
        )
        server = _FakeOpcUaServer.instances[0]
        assert len(_FakeOpcUaServer.instances) == 1
        assert server.start_count == 1

        await manager.pause("sim-a")
        assert manager.status("sim-a").state == "paused"
        assert manager.status("sim-b").state in {"running", "degraded"}
        assert manager.hosts.status()["shared_opcua_hosts"]["0.0.0.0:4840"]["target_count"] == 2
        assert server.stop_count == 0

        before_b = manager.status("sim-b").emitted_count
        await asyncio.sleep(0.08)
        assert manager.status("sim-b").emitted_count > before_b
        paused_a = manager.status("sim-a").emitted_count
        await asyncio.sleep(0.05)
        assert manager.status("sim-a").emitted_count == paused_a

        await manager.stop("sim-a")
        host = manager.hosts.status()["shared_opcua_hosts"]["0.0.0.0:4840"]
        assert host["simulation_count"] == 1
        assert host["simulation_targets"][0]["simulation_id"] == "sim-b"
        assert server.running is True
        assert server.stop_count == 0

        await manager.restart("sim-a")
        await _wait_for(
            lambda: manager.hosts.status()["shared_opcua_hosts"]["0.0.0.0:4840"]["target_count"] == 2,
            "restarted simulation did not rejoin shared host",
        )
        assert server.start_count == 1
        assert manager.status("sim-b").state in {"running", "degraded"}

        await manager.stop("sim-b")
        assert server.running is True
        assert manager.hosts.status()["shared_opcua_hosts"]["0.0.0.0:4840"]["simulation_count"] == 1

        await manager.stop("sim-a")
        assert manager.hosts.status()["shared_opcua_hosts"] == {}
        assert server.stop_count == 1
        await manager.shutdown()

    asyncio.run(run())


def test_failed_concurrent_join_cannot_orphan_successful_shared_member(monkeypatch) -> None:
    monkeypatch.setattr(opcua_module, "OpcUaTagServer", _FailFirstStartServer)
    monkeypatch.setattr(opcua_module, "Server", object())
    _FakeOpcUaServer.instances.clear()
    _FailFirstStartServer.should_fail = True

    async def run() -> None:
        hosts = opcua_module.InterfaceHostManager()
        schema = [SignalDefinition(name="value", node_id="value", data_type="Double")]
        results = await asyncio.gather(
            hosts.acquire_opcua("sim-a", "A", _binding(), schema),
            hosts.acquire_opcua("sim-b", "B", _binding(), schema),
            return_exceptions=True,
        )
        failures = [item for item in results if isinstance(item, Exception)]
        handles = [item for item in results if isinstance(item, opcua_module.OpcUaHandle)]
        assert len(failures) == 1
        assert len(handles) == 1

        handle = handles[0]
        status = hosts.status()["shared_opcua_hosts"]["0.0.0.0:4840"]
        assert status["target_count"] == 1
        assert status["pending_targets"] == 0
        assert status["simulation_targets"][0]["simulation_id"] == handle.simulation_id

        await hosts.publish_opcua(
            handle,
            SimulationFrame(
                simulation_id=handle.simulation_id,
                values={"value": SignalValue(value=42.0, data_type="Double")},
            ),
        )
        assert handle.server.variables[handle.node_map["value"]]["value"] == 42.0

        await hosts.release_opcua(handle)
        assert hosts.status()["shared_opcua_hosts"] == {}

    asyncio.run(run())


def test_last_shared_member_release_waits_for_pending_join(monkeypatch) -> None:
    monkeypatch.setattr(opcua_module, "OpcUaTagServer", _FakeOpcUaServer)
    monkeypatch.setattr(opcua_module, "Server", object())
    _FakeOpcUaServer.instances.clear()

    async def run() -> None:
        hosts = opcua_module.InterfaceHostManager()
        schema = [SignalDefinition(name="value", node_id="value", data_type="Double")]
        first = await hosts.acquire_opcua("sim-a", "A", _binding(), schema)
        server = first.server

        entered = asyncio.Event()
        allow_join = asyncio.Event()
        original_add = opcua_module._add_shared_group

        async def blocked_add(host, member_key, target_id, simulation_id, simulation_name, schema, node_map, data_types, writable, folder_name):
            if simulation_id == "sim-b":
                entered.set()
                await allow_join.wait()
            return await original_add(
                host,
                member_key,
                target_id,
                simulation_id,
                simulation_name,
                schema,
                node_map,
                data_types,
                writable,
                folder_name,
            )

        monkeypatch.setattr(opcua_module, "_add_shared_group", blocked_add)
        joining = asyncio.create_task(hosts.acquire_opcua("sim-b", "B", _binding(), schema))
        await entered.wait()
        assert hosts.status()["shared_opcua_hosts"]["0.0.0.0:4840"]["pending_targets"] == 1

        releasing = asyncio.create_task(hosts.release_opcua(first))
        await asyncio.sleep(0)
        assert server.running is True
        assert server.stop_count == 0

        allow_join.set()
        second = await joining
        await releasing
        status = hosts.status()["shared_opcua_hosts"]["0.0.0.0:4840"]
        assert status["simulation_count"] == 1
        assert status["simulation_targets"][0]["simulation_id"] == "sim-b"
        assert server.running is True
        assert server.start_count == 1
        assert server.stop_count == 0

        await hosts.release_opcua(second)
        assert server.stop_count == 1
        assert hosts.status()["shared_opcua_hosts"] == {}

    asyncio.run(run())


def test_dedicated_simulations_do_not_share_lifecycle(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(opcua_module, "OpcUaTagServer", _FakeOpcUaServer)
    monkeypatch.setattr(opcua_module, "Server", object())
    _FakeOpcUaServer.instances.clear()

    async def run() -> None:
        manager = SimulationManager(tmp_path / "runtime.json")
        await manager.create(_definition("sim-a", 10, _dedicated_binding(4841)))
        await manager.create(_definition("sim-b", 100, _dedicated_binding(4842)))
        await asyncio.gather(manager.start("sim-a"), manager.start("sim-b"))

        server_a = next(server for server in _FakeOpcUaServer.instances if ":4841/" in server.endpoint)
        server_b = next(server for server in _FakeOpcUaServer.instances if ":4842/" in server.endpoint)
        assert server_a is not server_b
        assert server_a.running and server_b.running

        await manager.pause("sim-a")
        assert manager.status("sim-a").state == "paused"
        assert manager.status("sim-b").state in {"running", "degraded"}
        assert server_b.start_count == 1
        assert server_b.stop_count == 0

        before_b = manager.status("sim-b").emitted_count
        await asyncio.sleep(0.08)
        assert manager.status("sim-b").emitted_count > before_b

        await manager.stop("sim-a")
        assert server_a.stop_count == 1
        assert server_b.running is True
        assert server_b.stop_count == 0

        await manager.restart("sim-a")
        replacement_a = next(
            server for server in reversed(_FakeOpcUaServer.instances)
            if ":4841/" in server.endpoint and server is not server_a
        )
        assert replacement_a.running is True
        assert server_b.running is True
        assert server_b.start_count == 1
        assert server_b.stop_count == 0

        await manager.stop("sim-a")
        await manager.stop("sim-b")
        assert replacement_a.stop_count == 1
        assert server_b.stop_count == 1
        await manager.shutdown()

    asyncio.run(run())
