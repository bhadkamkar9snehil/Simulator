from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.models import ReplayConfig, TagMapping
from app.opcua_server import OpcUaTagServer

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
class _SharedOpcUaHost:
    key: str
    server: OpcUaTagServer
    namespace_uri: str
    root_folder: str
    groups: dict[str, tuple[str, str, list[SignalDefinition], TargetBinding]] = field(default_factory=dict)
    node_maps: dict[str, dict[str, str]] = field(default_factory=dict)
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
            host.groups.pop(handle.target_id, None)
            host.node_maps.pop(handle.target_id, None)
            if host.groups:
                await self._reconfigure_shared(host)
            else:
                await host.server.stop()
                async with self._manager_lock:
                    self._shared_opcua.pop(handle.key, None)

    async def publish_opcua(self, handle: OpcUaHandle, frame: SimulationFrame) -> None:
        values = {
            handle.node_map[name]: (signal.value, signal.data_type)
            for name, signal in frame.values.items()
            if name in handle.node_map
        }
        if not values:
            return
        if handle.shared:
            host = self._shared_opcua.get(handle.key)
            if host is None:
                raise RuntimeError("Shared OPC UA host is no longer available.")
            async with host.lock:
                await host.server.update_values(values)
            return
        await handle.server.update_values(values)

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
                key: {**host.server.get_status(), "simulation_targets": list(host.groups)}
                for key, host in self._shared_opcua.items()
            },
            "dedicated_opcua_hosts": {
                target_id: handle.server.get_status()
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
        port = int(config.get("port", 4840))
        path = str(config.get("path", "simulator")).strip("/") or "simulator"
        advertised_host = str(config.get("advertised_host", "localhost"))
        key = str(config.get("host_key") or f"{port}/{path}")

        async with self._manager_lock:
            host = self._shared_opcua.get(key)
            if host is None:
                host = _SharedOpcUaHost(
                    key=key,
                    server=OpcUaTagServer(
                        endpoint=f"opc.tcp://0.0.0.0:{port}/{path}",
                        advertised_endpoint=f"opc.tcp://{advertised_host}:{port}/{path}",
                    ),
                    namespace_uri=str(config.get("namespace_uri", "http://local/unified-simulator")),
                    root_folder=str(config.get("root_folder", "Simulations")),
                )
                self._shared_opcua[key] = host

        async with host.lock:
            host.groups[binding.target_id] = (simulation_id, simulation_name, schema, binding)
            await self._reconfigure_shared(host)
            node_map = dict(host.node_maps[binding.target_id])
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
        port = int(config["port"])
        path = str(config.get("path", safe_name(simulation_id))).strip("/") or safe_name(simulation_id)
        advertised_host = str(config.get("advertised_host", "localhost"))
        server = OpcUaTagServer(
            endpoint=f"opc.tcp://0.0.0.0:{port}/{path}",
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

    async def _reconfigure_shared(self, host: _SharedOpcUaHost) -> None:
        all_tags: list[TagMapping] = []
        host.node_maps.clear()
        for target_id, (simulation_id, _simulation_name, schema, _binding) in host.groups.items():
            prefix = f"{safe_name(simulation_id)}.{safe_name(target_id)}"
            node_map: dict[str, str] = {}
            for signal in schema:
                node_id = f"{prefix}.{safe_name(signal.node_id or signal.name)}"
                node_map[signal.name] = node_id
                all_tags.append(tag_mapping(signal, node_id, f"{simulation_id}.{signal.name}"))
            host.node_maps[target_id] = node_map

        await host.server.stop()
        await host.server.start()
        await host.server.configure_tags(
            ReplayConfig(
                protocol="opcua",
                namespace_uri=host.namespace_uri,
                root_folder=host.root_folder,
                node_id_prefix=host.root_folder,
                tags=all_tags,
            )
        )


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
            details = self._handle.server.get_status()
            endpoint = self._handle.server.get_endpoint()
        return TargetRuntimeStatus(
            target_id=self.target_id,
            kind="opcua",
            state=self._state,  # type: ignore[arg-type]
            endpoint=endpoint,
            last_error=self._last_error,
            details=details,
        )


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
