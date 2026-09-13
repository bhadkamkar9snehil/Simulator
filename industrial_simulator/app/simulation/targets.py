from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

from app.models import ReplayConfig, TagMapping
from app.mqtt_publisher import MqttTagPublisher
from app.opcua_server import OpcUaTagServer
from app.sql_server import run_sql_action

from .contracts import SimulationTarget
from .models import SignalDefinition, SimulationFrame, TargetBinding, TargetRuntimeStatus


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._-")
    return cleaned or "item"


def _tag_mapping(signal: SignalDefinition, node_id: str, tag_name: str | None = None) -> TagMapping:
    return TagMapping(
        enabled=True,
        csv_column=signal.name,
        tag_name=tag_name or signal.name,
        node_id=node_id,
        data_type=signal.data_type,
        initial_value=signal.initial_value,
        writable=signal.writable,
    )


@dataclass
class _OpcUaHandle:
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
    """Own listeners whose lifecycle is broader than one SimulationInstance.

    The existing OPC UA server can expose a union of tags but not yet mutate
    folders incrementally. During migration we therefore rebuild a shared host
    when its membership changes. Publishing is isolated behind the host lock so
    concurrent simulations never write while the host is being rebuilt.
    """

    def __init__(self) -> None:
        self._shared_opcua: dict[str, _SharedOpcUaHost] = {}
        self._dedicated_opcua: dict[str, _OpcUaHandle] = {}
        self._manager_lock = asyncio.Lock()

    async def acquire_opcua(
        self,
        simulation_id: str,
        simulation_name: str,
        binding: TargetBinding,
        schema: list[SignalDefinition],
    ) -> _OpcUaHandle:
        if binding.hosting_mode == "dedicated":
            return await self._acquire_dedicated(simulation_id, simulation_name, binding, schema)
        return await self._acquire_shared(simulation_id, simulation_name, binding, schema)

    async def release_opcua(self, handle: _OpcUaHandle) -> None:
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

    async def publish_opcua(self, handle: _OpcUaHandle, frame: SimulationFrame) -> None:
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
                key: {
                    **host.server.get_status(),
                    "simulation_targets": list(host.groups),
                }
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
    ) -> _OpcUaHandle:
        config = binding.config
        port = int(config.get("port", 4840))
        path = str(config.get("path", "simulator")).strip("/") or "simulator"
        advertised_host = str(config.get("advertised_host", "localhost"))
        key = str(config.get("host_key") or f"{port}/{path}")

        async with self._manager_lock:
            host = self._shared_opcua.get(key)
            if host is None:
                server = OpcUaTagServer(
                    endpoint=f"opc.tcp://0.0.0.0:{port}/{path}",
                    advertised_endpoint=f"opc.tcp://{advertised_host}:{port}/{path}",
                )
                host = _SharedOpcUaHost(
                    key=key,
                    server=server,
                    namespace_uri=str(config.get("namespace_uri", "http://local/unified-simulator")),
                    root_folder=str(config.get("root_folder", "Simulations")),
                )
                self._shared_opcua[key] = host

        async with host.lock:
            host.groups[binding.target_id] = (simulation_id, simulation_name, schema, binding)
            await self._reconfigure_shared(host)
            node_map = dict(host.node_maps[binding.target_id])
        return _OpcUaHandle(
            key=key,
            target_id=binding.target_id,
            simulation_id=simulation_id,
            server=host.server,
            node_map=node_map,
            shared=True,
        )

    async def _acquire_dedicated(
        self,
        simulation_id: str,
        simulation_name: str,
        binding: TargetBinding,
        schema: list[SignalDefinition],
    ) -> _OpcUaHandle:
        config = binding.config
        if "port" not in config:
            raise ValueError("Dedicated OPC UA target requires config.port.")
        port = int(config["port"])
        path = str(config.get("path", _safe(simulation_id))).strip("/") or _safe(simulation_id)
        advertised_host = str(config.get("advertised_host", "localhost"))
        server = OpcUaTagServer(
            endpoint=f"opc.tcp://0.0.0.0:{port}/{path}",
            advertised_endpoint=f"opc.tcp://{advertised_host}:{port}/{path}",
        )
        node_map = {signal.name: signal.node_id for signal in schema}
        replay_config = _opcua_config(
            schema=schema,
            node_map=node_map,
            namespace_uri=str(config.get("namespace_uri", f"http://local/unified-simulator/{simulation_id}")),
            root_folder=str(config.get("root_folder", _safe(simulation_name))),
        )
        await server.start()
        await server.configure_tags(replay_config)
        handle = _OpcUaHandle(
            key=binding.target_id,
            target_id=binding.target_id,
            simulation_id=simulation_id,
            server=server,
            node_map=node_map,
            shared=False,
        )
        self._dedicated_opcua[binding.target_id] = handle
        return handle

    async def _reconfigure_shared(self, host: _SharedOpcUaHost) -> None:
        all_tags: list[TagMapping] = []
        host.node_maps.clear()
        for target_id, (simulation_id, _simulation_name, schema, _binding) in host.groups.items():
            prefix = f"{_safe(simulation_id)}.{_safe(target_id)}"
            node_map: dict[str, str] = {}
            for signal in schema:
                node_id = f"{prefix}.{_safe(signal.node_id or signal.name)}"
                node_map[signal.name] = node_id
                all_tags.append(_tag_mapping(signal, node_id, f"{simulation_id}.{signal.name}"))
            host.node_maps[target_id] = node_map

        replay_config = ReplayConfig(
            protocol="opcua",
            namespace_uri=host.namespace_uri,
            root_folder=host.root_folder,
            node_id_prefix=host.root_folder,
            tags=all_tags,
        )
        await host.server.stop()
        await host.server.start()
        await host.server.configure_tags(replay_config)


class OpcUaTarget:
    def __init__(self, binding: TargetBinding, hosts: InterfaceHostManager):
        self.target_id = binding.target_id
        self.binding = binding
        self._hosts = hosts
        self._handle: _OpcUaHandle | None = None
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
        handle = self._handle
        self._handle = None
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


class MqttTarget:
    def __init__(self, binding: TargetBinding):
        self.target_id = binding.target_id
        self.binding = binding
        self._publisher: MqttTagPublisher | None = None
        self._state = "created"
        self._last_error: str | None = None
        self._node_map: dict[str, str] = {}

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None:
        config = self.binding.config
        self._state = "starting"
        publisher = MqttTagPublisher(
            host=str(config.get("host", "localhost")),
            port=int(config.get("port", 1883)),
            topic_prefix=str(config.get("topic_prefix", f"simulator/{simulation_id}")),
            client_id=str(config.get("client_id", f"sim-{simulation_id}-{self.target_id}")),
        )
        self._node_map = {
            signal.name: f"{_safe(simulation_id)}.{_safe(signal.node_id or signal.name)}"
            for signal in schema
        }
        replay_config = ReplayConfig(
            protocol="mqtt",
            mqtt_host=str(config.get("host", "localhost")),
            mqtt_port=int(config.get("port", 1883)),
            mqtt_topic_prefix=str(config.get("topic_prefix", f"simulator/{simulation_id}")),
            mqtt_device_id=str(config.get("device_id", simulation_name or simulation_id)),
            mqtt_client_id=str(config.get("client_id", f"sim-{simulation_id}-{self.target_id}")),
            mqtt_username=config.get("username"),
            mqtt_password=config.get("password"),
            mqtt_qos=int(config.get("qos", 0)),
            mqtt_retain=bool(config.get("retain", False)),
            publish_individual_tags=bool(config.get("publish_individual_tags", True)),
            publish_aggregate=bool(config.get("publish_aggregate", True)),
            tags=[_tag_mapping(signal, self._node_map[signal.name], signal.name) for signal in schema],
        )
        try:
            await publisher.start()
            await publisher.configure_tags(replay_config)
            self._publisher = publisher
            self._state = "running"
            self._last_error = None
        except Exception as exc:
            await publisher.stop()
            self._state = "error"
            self._last_error = str(exc)
            raise

    async def publish(self, frame: SimulationFrame) -> None:
        if self._publisher is None:
            raise RuntimeError("MQTT target is not started.")
        values = {
            self._node_map[name]: (signal.value, signal.data_type)
            for name, signal in frame.values.items()
            if name in self._node_map
        }
        metadata = {
            self._node_map[name]: {
                "tag": name,
                "unit": signal.unit,
                "quality": signal.quality,
                **signal.metadata,
            }
            for name, signal in frame.values.items()
            if name in self._node_map
        }
        await self._publisher.update_values(values, timestamp=frame.timestamp, mqtt_metadata=metadata)

    async def stop(self) -> None:
        publisher = self._publisher
        self._publisher = None
        if publisher is not None:
            await publisher.stop()
        self._state = "stopped"

    def status(self) -> TargetRuntimeStatus:
        details = self._publisher.get_status() if self._publisher is not None else {}
        endpoint = self._publisher.get_endpoint() if self._publisher is not None else None
        return TargetRuntimeStatus(
            target_id=self.target_id,
            kind="mqtt",
            state=self._state,  # type: ignore[arg-type]
            endpoint=endpoint,
            last_error=self._last_error,
            details=details,
        )


class SqlServerTarget:
    """Batched SQL Server projection using the existing System.Data helper."""

    def __init__(self, binding: TargetBinding):
        self.target_id = binding.target_id
        self.binding = binding
        self._state = "created"
        self._last_error: str | None = None
        self._buffer: list[dict[str, Any]] = []
        self._rows_written = 0
        self._endpoint: str | None = None

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None:
        config = self.binding.config
        server = str(config.get("server", "localhost"))
        port = int(config.get("port", 1433))
        database = str(config.get("database", "master"))
        table = str(config.get("table", "dbo.tag_snapshots"))
        self._endpoint = f"sqlserver://{server}:{port}/{database}/{table}"
        self._state = "starting"
        result = await asyncio.to_thread(run_sql_action, "test", config)
        if not result.get("ok"):
            self._state = "error"
            self._last_error = str(result.get("error") or result.get("stderr") or "SQL Server connection failed.")
            raise ValueError(self._last_error)
        self._state = "running"
        self._last_error = None

    async def publish(self, frame: SimulationFrame) -> None:
        description_prefix = str(self.binding.config.get("description", frame.simulation_id))
        for name, signal in frame.values.items():
            self._buffer.append({
                "ts": frame.timestamp,
                "tag_name": name,
                "value": "" if signal.value is None else str(signal.value),
                "unit": signal.unit or "",
                "quality": signal.quality,
                "description": str(signal.metadata.get("description") or description_prefix),
            })
        if len(self._buffer) >= int(self.binding.config.get("batch_size", 50)):
            await self._flush()

    async def stop(self) -> None:
        if self._buffer:
            await self._flush()
        self._state = "stopped"

    def status(self) -> TargetRuntimeStatus:
        return TargetRuntimeStatus(
            target_id=self.target_id,
            kind="sql_server",
            state=self._state,  # type: ignore[arg-type]
            endpoint=self._endpoint,
            last_error=self._last_error,
            details={"buffered_rows": len(self._buffer), "rows_written": self._rows_written},
        )

    async def _flush(self) -> None:
        rows, self._buffer = self._buffer, []
        if not rows:
            return
        result = await asyncio.to_thread(run_sql_action, "write", self.binding.config, rows)
        if not result.get("ok"):
            self._buffer = rows + self._buffer
            self._last_error = str(result.get("error") or result.get("stderr") or "SQL Server write failed.")
            raise ValueError(self._last_error)
        self._rows_written += int(result.get("rows_written", len(rows)) or 0)
        self._last_error = None


class HttpTarget:
    """View of the existing FastAPI host as a per-simulation HTTP data target."""

    def __init__(self, binding: TargetBinding):
        self.target_id = binding.target_id
        self.binding = binding
        self._state = "created"
        self._endpoint: str | None = None
        self.last_frame: SimulationFrame | None = None

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None:
        if self.binding.hosting_mode != "shared":
            raise ValueError("HTTP target currently supports shared hosting only.")
        self._endpoint = f"/api/v2/simulations/{simulation_id}/targets/{self.target_id}"
        self._state = "running"

    async def publish(self, frame: SimulationFrame) -> None:
        self.last_frame = frame

    async def stop(self) -> None:
        self._state = "stopped"

    def status(self) -> TargetRuntimeStatus:
        return TargetRuntimeStatus(
            target_id=self.target_id,
            kind="http",
            state=self._state,  # type: ignore[arg-type]
            endpoint=self._endpoint,
            details={"last_sequence": self.last_frame.sequence if self.last_frame else None},
        )


class MemoryTarget:
    """In-process target used for diagnostics, tests, and API-only simulations."""

    def __init__(self, binding: TargetBinding):
        self.target_id = binding.target_id
        self.binding = binding
        self.last_frame: SimulationFrame | None = None
        self._state = "created"

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None:
        self._state = "running"

    async def publish(self, frame: SimulationFrame) -> None:
        self.last_frame = frame

    async def stop(self) -> None:
        self._state = "stopped"

    def status(self) -> TargetRuntimeStatus:
        return TargetRuntimeStatus(
            target_id=self.target_id,
            kind="memory",
            state=self._state,  # type: ignore[arg-type]
            endpoint=f"memory://{self.target_id}",
        )


def create_target(binding: TargetBinding, hosts: InterfaceHostManager) -> SimulationTarget:
    if binding.kind == "opcua":
        return OpcUaTarget(binding, hosts)
    if binding.kind == "mqtt":
        return MqttTarget(binding)
    if binding.kind in {"sql", "sql_server", "mssql"}:
        return SqlServerTarget(binding)
    if binding.kind in {"odata", "sap_odata"}:
        from .odata import ODataTarget

        return ODataTarget(binding)
    if binding.kind in {"http", "http_stream"}:
        return HttpTarget(binding)
    if binding.kind in {"memory", "internal"}:
        return MemoryTarget(binding)
    raise ValueError(f"Unsupported simulation target kind: {binding.kind}")


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
        tags=[_tag_mapping(signal, node_map[signal.name], signal.name) for signal in schema],
    )
