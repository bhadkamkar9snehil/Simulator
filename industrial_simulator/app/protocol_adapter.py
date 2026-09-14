from __future__ import annotations

import asyncio
from typing import Any

from app.models import CurrentValue, ProtocolMode, ReplayConfig
from app.mqtt_publisher import MqttTagPublisher
from app.opcua_server import OpcUaTagServer


class DualProtocolAdapter:
    def __init__(self) -> None:
        self.opcua = OpcUaTagServer()
        self.mqtt = MqttTagPublisher()
        self.protocol: ProtocolMode = "opcua"
        self._io_lock = asyncio.Lock()

    def _running_protocol(self) -> ProtocolMode:
        opcua_running = bool(self.opcua.get_status().get("running"))
        mqtt_running = bool(self.mqtt.get_status().get("running"))
        if opcua_running and mqtt_running:
            return "both"
        if mqtt_running:
            return "mqtt"
        return "opcua"

    async def start(self) -> None:
        await self.start_channels(self.protocol)

    async def stop(self) -> None:
        async with self._io_lock:
            await self.mqtt.stop()
            await self.opcua.stop()

    async def configure_tags(self, config: ReplayConfig) -> None:
        async with self._io_lock:
            self.protocol = config.protocol

            if self.protocol == "opcua":
                await self.mqtt.stop()
                await self.opcua.stop()
                await self.opcua.start()
                await self.opcua.configure_tags(config)
                return

            if self.protocol == "mqtt":
                await self.opcua.stop()
                await self.mqtt.start()
                await self.mqtt.configure_tags(config)
                return

            await self.opcua.stop()
            await self.opcua.start()
            await self.opcua.configure_tags(config)
            await self.mqtt.start()
            await self.mqtt.configure_tags(config)

    async def configure_channel_tags(self, protocol: str, config: ReplayConfig) -> None:
        if protocol not in ("opcua", "mqtt"):
            raise ValueError("Protocol must be opcua or mqtt.")
        async with self._io_lock:
            if protocol == "opcua":
                await self.opcua.stop()
                await self.opcua.start()
                await self.opcua.configure_tags(config)
            else:
                await self.mqtt.start()
                await self.mqtt.configure_tags(config)
            self.protocol = self._running_protocol()

    async def start_channels(self, protocol: str) -> None:
        if protocol not in ("opcua", "mqtt", "both"):
            raise ValueError("Protocol must be opcua, mqtt, or both.")
        async with self._io_lock:
            if protocol in ("opcua", "both"):
                await self.opcua.start()
            if protocol in ("mqtt", "both"):
                await self.mqtt.start()
            self.protocol = self._running_protocol()

    async def stop_channels(self, protocol: str) -> None:
        if protocol not in ("opcua", "mqtt", "both"):
            raise ValueError("Protocol must be opcua, mqtt, or both.")
        async with self._io_lock:
            if protocol in ("mqtt", "both"):
                await self.mqtt.stop()
            if protocol in ("opcua", "both"):
                await self.opcua.stop()
            self.protocol = self._running_protocol()

    async def update_values(
        self,
        values: dict[str, Any],
        timestamp: str | None = None,
        current_values: dict[str, CurrentValue] | None = None,
        mqtt_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        await self.update_channel_values(
            self.protocol,
            values,
            timestamp=timestamp,
            current_values=current_values,
            mqtt_metadata=mqtt_metadata,
        )

    @staticmethod
    def _mqtt_values(values: dict[str, Any]) -> dict[str, tuple[Any, str]]:
        result: dict[str, tuple[Any, str]] = {}
        for node_id, payload in values.items():
            if isinstance(payload, dict):
                result[node_id] = (payload.get("value"), str(payload.get("data_type") or "String"))
                continue
            if isinstance(payload, (list, tuple)):
                value = payload[0] if len(payload) > 0 else None
                data_type = str(payload[1]) if len(payload) > 1 and payload[1] else "String"
                result[node_id] = (value, data_type)
                continue
            result[node_id] = (payload, "String")
        return result

    async def update_channel_values(
        self,
        protocol: str,
        values: dict[str, Any],
        timestamp: str | None = None,
        current_values: dict[str, CurrentValue] | None = None,
        mqtt_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        if protocol not in ("opcua", "mqtt", "both"):
            raise ValueError("Protocol must be opcua, mqtt, or both.")
        async with self._io_lock:
            if protocol in ("opcua", "both"):
                await self.opcua.update_values(values)
            if protocol in ("mqtt", "both"):
                await self.mqtt.update_values(
                    self._mqtt_values(values),
                    timestamp=timestamp,
                    current_values=current_values,
                    mqtt_metadata=mqtt_metadata,
                )

    def get_endpoint(self) -> str:
        if self.protocol == "opcua":
            return self.opcua.get_endpoint()
        if self.protocol == "mqtt":
            return self.mqtt.get_endpoint()
        return f"OPC UA: {self.opcua.get_endpoint()} | MQTT: {self.mqtt.get_endpoint()}"

    def get_status(self) -> dict[str, Any]:
        self.protocol = self._running_protocol()
        return {
            "active_protocol": self.protocol,
            "opcua": self.opcua.get_status(),
            "mqtt": self.mqtt.get_status(),
            "endpoint": self.get_endpoint(),
        }


class ProtocolChannelAdapter:
    """Legacy single-protocol view over shared protocol services."""

    def __init__(self, parent: DualProtocolAdapter, protocol: str) -> None:
        if protocol not in ("opcua", "mqtt"):
            raise ValueError("ProtocolChannelAdapter supports only 'opcua' or 'mqtt'.")
        self.parent = parent
        self.protocol = protocol

    async def start(self) -> None:
        await self.parent.start_channels(self.protocol)

    async def stop(self) -> None:
        return None

    async def configure_tags(self, config: ReplayConfig) -> None:
        await self.parent.configure_channel_tags(self.protocol, config)

    async def update_values(
        self,
        values: dict[str, Any],
        timestamp: str | None = None,
        current_values: dict[str, CurrentValue] | None = None,
        mqtt_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        await self.parent.update_channel_values(
            self.protocol,
            values,
            timestamp=timestamp,
            current_values=current_values,
            mqtt_metadata=mqtt_metadata,
        )

    def get_endpoint(self) -> str:
        if self.protocol == "opcua":
            return self.parent.opcua.get_endpoint()
        return self.parent.mqtt.get_endpoint()


class ReplayJobProtocolAdapter:
    """Legacy per-job protocol view over shared protocol services."""

    def __init__(self, parent: DualProtocolAdapter, protocol: str) -> None:
        if protocol not in ("opcua", "mqtt", "both"):
            raise ValueError("ReplayJobProtocolAdapter supports opcua, mqtt, or both.")
        self.parent = parent
        self.protocol = protocol

    async def configure_tags(self, config: ReplayConfig) -> None:
        return None

    async def start(self) -> None:
        await self.parent.start_channels(self.protocol)

    async def stop(self) -> None:
        return None

    async def update_values(
        self,
        values: dict[str, Any],
        timestamp: str | None = None,
        current_values: dict[str, CurrentValue] | None = None,
        mqtt_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        await self.parent.update_channel_values(
            self.protocol,
            values,
            timestamp=timestamp,
            current_values=current_values,
            mqtt_metadata=mqtt_metadata,
        )

    def get_endpoint(self) -> str:
        if self.protocol == "opcua":
            return self.parent.opcua.get_endpoint()
        if self.protocol == "mqtt":
            return self.parent.mqtt.get_endpoint()
        return self.parent.get_endpoint()
