from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.models import ReplayConfig
from app.opcua_server import OpcUaTagServer, ua

from ..models import SignalDefinition, SimulationFrame, TargetBinding, TargetRuntimeStatus
from .common import safe_name, tag_mapping


@dataclass
class OpcUaHandle:
    key: str
    target_id: str
    simulation_id: str
    server: OpcUaTagServer
    node_map: dict[str, str]
    shared: bool


@dataclass
class _SharedGroup:
    simulation_id: str
    simulation_name: str
    node_map: dict[str, str]
    variable_keys: set[str]
    folder: Any = None


@dataclass
class _SharedOpcUaHost:
    key: str
    server: OpcUaTagServer
    bind_host: str
    port: int
    path: str
    advertised_host: str
    namespace_uri: str
    root_folder_name: str
    namespace_index: int | None = None
    root_folder: Any = None
    groups: dict[str, _SharedGroup] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class InterfaceHostManager:
    """Own interface listeners whose lifecycle outlives one simulation target.

    Shared OPC UA hosts stay alive while simulations are added or removed. Each
    target gets a child folder under the configured common root and can therefore
    be removed without rebuilding or restarting unrelated simulations.
    """

    def __init__(self) -> None:
        self._shared_opcua: dict[str, _SharedOpcUaHost] = {}
        self._dedicated_opcua: dict[str, OpcUaHandle] = {}
        self._manager_lock = asyncio.Lock()

    async def acquire_opcua(
        self,
        simulation_id: str,
        simulation_name: str,
        binding: TargetBinding,
        schema: list[SignalDefinition],
    ) -> OpcUaHandle:
        if binding.hosting_mode == "dedicated":
            return await self._acquire_dedicated(simulation_id, simulation_name, binding, schema)
        return await self._acquire_shared(simulation_id, simulation_name, binding, schema)

    async def release_opcua(self, handle: OpcUaHandle) -> None:
        if not handle.shared:
            self._dedicated_opcua.pop(handle.target_id, None)
            await handle.server.stop()
            return

        async with self._manager_lock:
            host = self._shared_opcua.get(handle.key)
        if host is None:
            return

        async with host.lock:
            await _remove_shared_group(host, handle.target_id)
            if host.groups:
                return
            await host.server.stop()

        async with self._manager_lock:
            current = self._shared_opcua.get(handle.key)
            if current is host and not host.groups:
                self._shared_opcua.pop(handle.key, None)

    async def publish_opcua(self, handle: OpcUaHandle, frame: SimulationFrame) -> None:
        values = {
            handle.node_map[name]: (signal.value, signal.data_type)
            for name, signal in frame.values.items()
            if name in handle.node_map
        }
        if not values:
            return

        if not handle.shared:
            await handle.server.update_values(values)
            return

        host = self._shared_opcua.get(handle.key)
        if host is None:
            raise RuntimeError("Shared OPC UA host is no longer available.")
        async with host.lock:
            await host.server.update_values(values)

    async def shutdown(self) -> None:
        async with self._manager_lock:
            shared = list(self._shared_opcua.values())
            dedicated = list(self._dedicated_opcua.values())
            self._shared_opcua.clear()
            self._dedicated_opcua.clear()
        for host in shared:
            async with host.lock:
                await host.server.stop()
        for handle in dedicated:
            await handle.server.stop()

    def status(self) -> dict[str, Any]:
        return {
            "shared_opcua_hosts": {
                key: {
                    **host.server.get_status(),
                    "bind_host": host.bind_host,
                    "port": host.port,
                    "path": host.path,
                    "namespace_uri": host.namespace_uri,
                    "root_folder": host.root_folder_name,
                    "simulation_targets": list(host.groups),
                    "simulation_count": len(host.groups),
                    "tag_count": sum(len(group.node_map) for group in host.groups.values()),
                }
                for key, host in self._shared_opcua.items()
            },
            "dedicated_opcua_hosts": {
                target_id: {
                    **handle.server.get_status(),
                    "simulation_id": handle.simulation_id,
                    "tag_count": len(handle.node_map),
                }
                for target_id, handle in self._dedicated_opcua.items()
            },
        }

    async def _acquire_shared(
        self,
        simulation_id: str,
        simulation_name: str,
        binding: TargetBinding,
        schema: list[SignalDefinition],
    ) -> OpcUaHandle:
        config = binding.config
        bind_host = str(config.get("bind_host", "0.0.0.0")).strip() or "0.0.0.0"
        port = int(config.get("port", 4840))
        path = str(config.get("path", "simulator")).strip("/") or "simulator"
        advertised_host = str(config.get("advertised_host", "localhost")).strip() or "localhost"
        namespace_uri = str(config.get("namespace_uri", "http://local/unified-simulator"))
        root_folder = str(config.get("root_folder", "Simulations")).strip() or "Simulations"
        key = _listener_key(bind_host, port, path)

        async with self._manager_lock:
            host = self._shared_opcua.get(key)
            if host is None:
                host = _SharedOpcUaHost(
                    key=key,
                    server=OpcUaTagServer(
                        endpoint=f"opc.tcp://{bind_host}:{port}/{path}",
                        advertised_endpoint=f"opc.tcp://{advertised_host}:{port}/{path}",
                    ),
                    bind_host=bind_host,
                    port=port,
                    path=path,
                    advertised_host=advertised_host,
                    namespace_uri=namespace_uri,
                    root_folder_name=root_folder,
                )
                self._shared_opcua[key] = host

        _validate_shared_host(host, advertised_host, namespace_uri, root_folder)

        try:
            async with host.lock:
                if not host.server.running:
                    await host.server.start()
                node_map = _shared_node_map(simulation_id, binding.target_id, schema)
                await _add_shared_group(host, binding.target_id, simulation_id, simulation_name, schema, node_map)
        except Exception:
            async with self._manager_lock:
                if not host.groups and self._shared_opcua.get(key) is host:
                    self._shared_opcua.pop(key, None)
            if not host.groups:
                await host.server.stop()
            raise

        return OpcUaHandle(key, binding.target_id, simulation_id, host.server, node_map, True)

    async def _acquire_dedicated(
        self,
        simulation_id: str,
        simulation_name: str,
        binding: TargetBinding,
        schema: list[SignalDefinition],
    ) -> OpcUaHandle:
        config = binding.config
        if "port" not in config:
            raise ValueError("Dedicated OPC UA target requires config.port.")
        bind_host = str(config.get("bind_host", "0.0.0.0")).strip() or "0.0.0.0"
        port = int(config["port"])
        path = str(config.get("path", safe_name(simulation_id))).strip("/") or safe_name(simulation_id)
        advertised_host = str(config.get("advertised_host", "localhost")).strip() or "localhost"
        server = OpcUaTagServer(
            endpoint=f"opc.tcp://{bind_host}:{port}/{path}",
            advertised_endpoint=f"opc.tcp://{advertised_host}:{port}/{path}",
        )
        node_map = {signal.name: signal.node_id for signal in schema}
        await server.start()
        await server.configure_tags(
            _opcua_config(
                schema,
                node_map,
                str(config.get("namespace_uri", f"http://local/unified-simulator/{simulation_id}")),
                str(config.get("root_folder", safe_name(simulation_name))),
            )
        )
        handle = OpcUaHandle(binding.target_id, binding.target_id, simulation_id, server, node_map, False)
        self._dedicated_opcua[binding.target_id] = handle
        return handle


class OpcUaTarget:
    def __init__(self, binding: TargetBinding, hosts: InterfaceHostManager):
        self.target_id = binding.target_id
        self.binding = binding
        self._hosts = hosts
        self._handle: OpcUaHandle | None = None
        self._state = "created"
        self._last_error: str | None = None

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None:
        if self._handle is not None:
            return
        self._state = "starting"
        try:
            self._handle = await self._hosts.acquire_opcua(simulation_id, simulation_name, self.binding, schema)
            self._state = "running"
            self._last_error = None
        except Exception as exc:
            self._state = "error"
            self._last_error = str(exc)
            raise

    async def publish(self, frame: SimulationFrame) -> None:
        if self._handle is None:
            raise RuntimeError("OPC UA target is not started.")
        await self._hosts.publish_opcua(self._handle, frame)

    async def stop(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            await self._hosts.release_opcua(handle)
        self._state = "stopped"

    def status(self) -> TargetRuntimeStatus:
        details: dict[str, Any] = {}
        endpoint = None
        if self._handle is not None:
            details = {
                **self._handle.server.get_status(),
                "shared": self._handle.shared,
                "host_key": self._handle.key,
                "tag_count": len(self._handle.node_map),
            }
            endpoint = self._handle.server.get_endpoint()
        return TargetRuntimeStatus(
            target_id=self.target_id,
            kind="opcua",
            state=self._state,  # type: ignore[arg-type]
            endpoint=endpoint,
            last_error=self._last_error,
            details=details,
        )


def _listener_key(bind_host: str, port: int, path: str) -> str:
    return f"{bind_host}:{port}/{path}"


def _validate_shared_host(
    host: _SharedOpcUaHost,
    advertised_host: str,
    namespace_uri: str,
    root_folder: str,
) -> None:
    mismatches: list[str] = []
    if host.advertised_host != advertised_host:
        mismatches.append(f"advertised_host={host.advertised_host!r}")
    if host.namespace_uri != namespace_uri:
        mismatches.append(f"namespace_uri={host.namespace_uri!r}")
    if host.root_folder_name != root_folder:
        mismatches.append(f"root_folder={host.root_folder_name!r}")
    if mismatches:
        raise ValueError(
            "Shared OPC UA listener settings conflict with the existing host: " + ", ".join(mismatches)
        )


def _shared_node_map(
    simulation_id: str,
    target_id: str,
    schema: list[SignalDefinition],
) -> dict[str, str]:
    prefix = f"{safe_name(simulation_id)}.{safe_name(target_id)}"
    return {
        signal.name: f"{prefix}.{safe_name(signal.node_id or signal.name)}"
        for signal in schema
    }


async def _add_shared_group(
    host: _SharedOpcUaHost,
    target_id: str,
    simulation_id: str,
    simulation_name: str,
    schema: list[SignalDefinition],
    node_map: dict[str, str],
) -> None:
    if target_id in host.groups:
        raise ValueError(f"Shared OPC UA target already exists: {target_id}")

    duplicate = set(node_map.values()).intersection(host.server.variables)
    if duplicate:
        raise ValueError(f"OPC UA NodeId collision: {sorted(duplicate)[0]}")

    if host.server.mock_mode or host.server.server is None:
        for signal in schema:
            node_id = node_map[signal.name]
            host.server.variables[node_id] = {
                "value": _initial_value(signal.data_type, signal.initial_value),
                "signal": signal,
            }
        host.groups[target_id] = _SharedGroup(
            simulation_id,
            simulation_name,
            node_map,
            set(node_map.values()),
        )
        return

    async def add_impl() -> tuple[int, Any, Any]:
        server = host.server.server
        assert server is not None
        namespace_index = host.namespace_index
        if namespace_index is None:
            namespace_index = await server.register_namespace(host.namespace_uri)
        root = host.root_folder
        if root is None:
            root = await server.nodes.objects.add_folder(namespace_index, host.root_folder_name)
        group_name = safe_name(simulation_id)
        folder = await root.add_folder(namespace_index, group_name)
        for signal in schema:
            logical_node_id = node_map[signal.name]
            value = _initial_value(signal.data_type, signal.initial_value)
            browse_name = safe_name(signal.name)
            if ua is not None:
                variable = await folder.add_variable(
                    ua.NodeId(logical_node_id, namespace_index),
                    browse_name,
                    value,
                )
            else:  # pragma: no cover - real server implies ua is available
                variable = await folder.add_variable(namespace_index, browse_name, value)
            if signal.writable:
                await variable.set_writable()
            host.server.variables[logical_node_id] = variable
        return namespace_index, root, folder

    namespace_index, root, folder = await host.server._run_in_server_loop(add_impl())
    host.namespace_index = namespace_index
    host.root_folder = root
    host.groups[target_id] = _SharedGroup(
        simulation_id,
        simulation_name,
        node_map,
        set(node_map.values()),
        folder,
    )


async def _remove_shared_group(host: _SharedOpcUaHost, target_id: str) -> None:
    group = host.groups.pop(target_id, None)
    if group is None:
        return

    for node_id in group.variable_keys:
        host.server.variables.pop(node_id, None)

    if host.server.mock_mode or group.folder is None or host.server.server is None:
        return

    async def remove_impl() -> None:
        await group.folder.delete(recursive=True)

    await host.server._run_in_server_loop(remove_impl())


def _initial_value(data_type: str, value: Any) -> Any:
    if value is not None:
        return value
    if data_type == "Double":
        return 0.0
    if data_type == "Int64":
        return 0
    if data_type == "Boolean":
        return False
    return ""


def _opcua_config(
    schema: list[SignalDefinition],
    node_map: dict[str, str],
    namespace_uri: str,
    root_folder: str,
) -> ReplayConfig:
    return ReplayConfig(
        protocol="opcua",
        namespace_uri=namespace_uri,
        root_folder=root_folder,
        node_id_prefix=root_folder,
        tags=[tag_mapping(signal, node_map[signal.name], signal.name) for signal in schema],
    )
