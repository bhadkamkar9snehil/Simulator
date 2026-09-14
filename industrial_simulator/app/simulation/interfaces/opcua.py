from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.models import ReplayConfig
from app.opcua_server import Server, ua
from app.opcua_support import initial_value, normalize_server_options, server_options_match, variant_type

from ..models import SignalDefinition, SimulationFrame, TargetBinding, TargetRuntimeStatus
from .common import safe_name, tag_mapping
from .opcua_server import UnifiedOpcUaServer as OpcUaTagServer


@dataclass
class OpcUaHandle:
    key: str
    member_key: str
    target_id: str
    simulation_id: str
    server: OpcUaTagServer
    node_map: dict[str, str]
    shared: bool
    port: int
    folder_name: str
    writable_count: int


@dataclass
class _SharedGroup:
    simulation_id: str
    simulation_name: str
    target_id: str
    node_map: dict[str, str]
    variable_keys: set[str]
    folder_name: str
    writable_count: int
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
    server_options: dict[str, Any]
    namespace_index: int | None = None
    root_folder: Any = None
    groups: dict[str, _SharedGroup] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class InterfaceHostManager:
    """Own interface listeners whose lifecycle outlives one simulation target."""

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
        if Server is None:
            raise RuntimeError("OPC UA target is unavailable because asyncua could not be imported.")
        if binding.hosting_mode == "dedicated":
            return await self._acquire_dedicated(simulation_id, simulation_name, binding, schema)
        return await self._acquire_shared(simulation_id, simulation_name, binding, schema)

    async def release_opcua(self, handle: OpcUaHandle) -> None:
        if not handle.shared:
            async with self._manager_lock:
                self._dedicated_opcua.pop(handle.member_key, None)
            await handle.server.stop()
            return

        async with self._manager_lock:
            host = self._shared_opcua.get(handle.key)
        if host is None:
            return

        async with host.lock:
            await _remove_shared_group(host, handle.member_key)
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
                    "simulation_targets": [
                        {
                            "member_key": member_key,
                            "simulation_id": group.simulation_id,
                            "target_id": group.target_id,
                            "folder": group.folder_name,
                            "tag_count": len(group.node_map),
                            "writable_count": group.writable_count,
                        }
                        for member_key, group in host.groups.items()
                    ],
                    "simulation_count": len({group.simulation_id for group in host.groups.values()}),
                    "target_count": len(host.groups),
                    "tag_count": sum(len(group.node_map) for group in host.groups.values()),
                    "writable_count": sum(group.writable_count for group in host.groups.values()),
                }
                for key, host in self._shared_opcua.items()
            },
            "dedicated_opcua_hosts": {
                member_key: {
                    **handle.server.get_status(),
                    "simulation_id": handle.simulation_id,
                    "target_id": handle.target_id,
                    "folder": handle.folder_name,
                    "tag_count": len(handle.node_map),
                    "writable_count": handle.writable_count,
                    "port": handle.port,
                }
                for member_key, handle in self._dedicated_opcua.items()
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
        namespace_uri = str(config.get("namespace_uri", "http://local/unified-simulator")).strip()
        root_folder = str(config.get("root_folder", "Simulations")).strip() or "Simulations"
        server_options = normalize_server_options(config)
        key = _listener_key(bind_host, port)
        member_key = _member_key(simulation_id, binding.target_id)

        async with self._manager_lock:
            if any(handle.port == port for handle in self._dedicated_opcua.values()):
                raise ValueError(f"OPC UA port {port} is already reserved by a dedicated target.")
            conflicting_shared = next(
                (item for item in self._shared_opcua.values() if item.port == port and item.key != key),
                None,
            )
            if conflicting_shared is not None:
                raise ValueError(
                    f"OPC UA port {port} is already reserved by shared listener {conflicting_shared.key}."
                )
            host = self._shared_opcua.get(key)
            if host is None:
                host = _SharedOpcUaHost(
                    key=key,
                    server=OpcUaTagServer(
                        endpoint=f"opc.tcp://{bind_host}:{port}/{path}",
                        advertised_endpoint=f"opc.tcp://{advertised_host}:{port}/{path}",
                        server_options=server_options,
                    ),
                    bind_host=bind_host,
                    port=port,
                    path=path,
                    advertised_host=advertised_host,
                    namespace_uri=namespace_uri,
                    root_folder_name=root_folder,
                    server_options=server_options,
                )
                self._shared_opcua[key] = host

        _validate_shared_host(host, path, advertised_host, namespace_uri, root_folder, server_options)

        try:
            async with host.lock:
                if not host.server.running:
                    await host.server.start()
                node_map = _shared_node_map(simulation_id, binding.target_id, schema, config)
                folder_name = _group_folder_name(simulation_id, simulation_name, binding.target_id, config)
                await _add_shared_group(
                    host,
                    member_key,
                    binding.target_id,
                    simulation_id,
                    simulation_name,
                    schema,
                    node_map,
                    folder_name,
                )
        except Exception:
            async with self._manager_lock:
                if not host.groups and self._shared_opcua.get(key) is host:
                    self._shared_opcua.pop(key, None)
            if not host.groups:
                await host.server.stop()
            raise

        writable_count = sum(1 for signal in schema if signal.writable)
        return OpcUaHandle(
            key,
            member_key,
            binding.target_id,
            simulation_id,
            host.server,
            node_map,
            True,
            port,
            folder_name,
            writable_count,
        )

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
        namespace_uri = str(config.get("namespace_uri", f"http://local/unified-simulator/{simulation_id}")).strip()
        root_folder = str(config.get("root_folder", safe_name(simulation_name))).strip() or safe_name(simulation_name)
        server_options = normalize_server_options(config)
        member_key = _member_key(simulation_id, binding.target_id)
        key = _listener_key(bind_host, port)
        server = OpcUaTagServer(
            endpoint=f"opc.tcp://{bind_host}:{port}/{path}",
            advertised_endpoint=f"opc.tcp://{advertised_host}:{port}/{path}",
            server_options=server_options,
        )
        node_map = {signal.name: signal.node_id for signal in schema}
        writable_count = sum(1 for signal in schema if signal.writable)
        handle = OpcUaHandle(
            key,
            member_key,
            binding.target_id,
            simulation_id,
            server,
            node_map,
            False,
            port,
            root_folder,
            writable_count,
        )

        async with self._manager_lock:
            if member_key in self._dedicated_opcua:
                raise ValueError(f"Dedicated OPC UA target already exists: {member_key}")
            if any(host.port == port for host in self._shared_opcua.values()):
                raise ValueError(f"OPC UA port {port} is already reserved by a shared listener.")
            if any(existing.port == port for existing in self._dedicated_opcua.values()):
                raise ValueError(f"OPC UA port {port} is already reserved by another dedicated target.")
            self._dedicated_opcua[member_key] = handle

        try:
            await server.start()
            await server.configure_tags(_opcua_config(schema, node_map, namespace_uri, root_folder))
        except Exception:
            async with self._manager_lock:
                if self._dedicated_opcua.get(member_key) is handle:
                    self._dedicated_opcua.pop(member_key, None)
            await server.stop()
            raise
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
                "member_key": self._handle.member_key,
                "folder": self._handle.folder_name,
                "tag_count": len(self._handle.node_map),
                "writable_count": self._handle.writable_count,
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


def _listener_key(bind_host: str, port: int) -> str:
    return f"{bind_host}:{port}"


def _member_key(simulation_id: str, target_id: str) -> str:
    return f"{simulation_id}/{target_id}"


def _validate_shared_host(
    host: _SharedOpcUaHost,
    path: str,
    advertised_host: str,
    namespace_uri: str,
    root_folder: str,
    server_options: dict[str, Any],
) -> None:
    mismatches: list[str] = []
    if host.path != path:
        mismatches.append(f"path={host.path!r}")
    if host.advertised_host != advertised_host:
        mismatches.append(f"advertised_host={host.advertised_host!r}")
    if host.namespace_uri != namespace_uri:
        mismatches.append(f"namespace_uri={host.namespace_uri!r}")
    if host.root_folder_name != root_folder:
        mismatches.append(f"root_folder={host.root_folder_name!r}")
    mismatches.extend(server_options_match(host.server_options, server_options))
    if mismatches:
        raise ValueError(
            "Shared OPC UA listener settings conflict with the existing host: " + ", ".join(mismatches)
        )


def _shared_node_map(
    simulation_id: str,
    target_id: str,
    schema: list[SignalDefinition],
    config: dict[str, Any],
) -> dict[str, str]:
    prefix = str(config.get("node_id_prefix", "")).strip()
    if not prefix:
        prefix = f"{safe_name(simulation_id)}.{safe_name(target_id)}"
    else:
        prefix = safe_name(prefix)
    return {
        signal.name: f"{prefix}.{safe_name(signal.node_id or signal.name)}"
        for signal in schema
    }


def _group_folder_name(
    simulation_id: str,
    simulation_name: str,
    target_id: str,
    config: dict[str, Any],
) -> str:
    template = str(config.get("group_folder", "{simulation_id}.{target_id}")).strip()
    values = {
        "simulation_id": simulation_id,
        "simulation_name": simulation_name,
        "target_id": target_id,
    }
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return safe_name(template)


async def _add_shared_group(
    host: _SharedOpcUaHost,
    member_key: str,
    target_id: str,
    simulation_id: str,
    simulation_name: str,
    schema: list[SignalDefinition],
    node_map: dict[str, str],
    folder_name: str,
) -> None:
    if member_key in host.groups:
        raise ValueError(f"Shared OPC UA target already exists: {member_key}")

    duplicate = set(node_map.values()).intersection(host.server.variables)
    if duplicate:
        raise ValueError(f"OPC UA NodeId collision: {sorted(duplicate)[0]}")

    writable_count = sum(1 for signal in schema if signal.writable)
    if host.server.mock_mode or host.server.server is None:
        for signal in schema:
            node_id = node_map[signal.name]
            host.server.variables[node_id] = {
                "value": initial_value(signal.data_type, signal.initial_value),
                "signal": signal,
            }
        host.groups[member_key] = _SharedGroup(
            simulation_id,
            simulation_name,
            target_id,
            node_map,
            set(node_map.values()),
            folder_name,
            writable_count,
        )
        return

    async def add_impl() -> tuple[Any, dict[str, Any]]:
        server = host.server.server
        assert server is not None
        namespace_index = host.namespace_index
        if namespace_index is None:
            namespace_index = await server.register_namespace(host.namespace_uri)
            host.namespace_index = namespace_index
        root = host.root_folder
        if root is None:
            root = await server.nodes.objects.add_folder(namespace_index, host.root_folder_name)
            host.root_folder = root
        folder = await root.add_folder(namespace_index, folder_name)
        created: dict[str, Any] = {}
        try:
            for signal in schema:
                logical_node_id = node_map[signal.name]
                value = initial_value(signal.data_type, signal.initial_value)
                browse_name = safe_name(signal.name)
                if ua is not None:
                    variable = await folder.add_variable(
                        ua.NodeId(logical_node_id, namespace_index),
                        browse_name,
                        value,
                        varianttype=variant_type(signal.data_type),
                    )
                else:  # pragma: no cover - real server implies ua is available
                    variable = await folder.add_variable(namespace_index, browse_name, value)
                if signal.writable:
                    await variable.set_writable()
                created[logical_node_id] = variable
        except Exception:
            try:
                await folder.delete(recursive=True)
            except Exception:
                pass
            raise
        return folder, created

    folder, created = await host.server._run_in_server_loop(add_impl())
    host.server.variables.update(created)
    host.groups[member_key] = _SharedGroup(
        simulation_id,
        simulation_name,
        target_id,
        node_map,
        set(node_map.values()),
        folder_name,
        writable_count,
        folder,
    )


async def _remove_shared_group(host: _SharedOpcUaHost, member_key: str) -> None:
    group = host.groups.pop(member_key, None)
    if group is None:
        return

    for node_id in group.variable_keys:
        host.server.variables.pop(node_id, None)

    if host.server.mock_mode or group.folder is None or host.server.server is None:
        return

    async def remove_impl() -> None:
        await group.folder.delete(recursive=True)

    await host.server._run_in_server_loop(remove_impl())


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
