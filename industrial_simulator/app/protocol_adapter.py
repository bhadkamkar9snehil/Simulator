from __future__ import annotations

import threading
from typing import Any

from app.models import ReplayConfig, CurrentValue, ProtocolMode
from app.opcua_server import OpcUaTagServer
from app.mqtt_publisher import MqttTagPublisher


class DualProtocolAdapter:
    def __init__(self) -> None:
        self.opcua = OpcUaTagServer()
        self.mqtt = MqttTagPublisher()
        self.protocol: ProtocolMode = "opcua"
        self._io_lock = threading.RLock()

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
        with self._io_lock:
            await self.mqtt.stop()
            await self.opcua.stop()

    async def configure_tags(self, config: ReplayConfig) -> None:
        with self._io_lock:
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

            # BOTH mode: one shared tag model drives OPC UA and MQTT together.
            # OPC UA is restarted on configure to keep a single clean TagSimulator root.
            await self.opcua.stop()
            await self.opcua.start()
            await self.opcua.configure_tags(config)
            await self.mqtt.start()
            await self.mqtt.configure_tags(config)

    async def configure_channel_tags(self, protocol: str, config: ReplayConfig) -> None:
        if protocol not in ("opcua", "mqtt"):
            raise ValueError("Protocol must be opcua or mqtt.")
        with self._io_lock:
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
        with self._io_lock:
            if protocol in ("opcua", "both"):
                await self.opcua.start()
            if protocol in ("mqtt", "both"):
                await self.mqtt.start()
            self.protocol = self._running_protocol()

    async def stop_channels(self, protocol: str) -> None:
        if protocol not in ("opcua", "mqtt", "both"):
            raise ValueError("Protocol must be opcua, mqtt, or both.")
        with self._io_lock:
            if protocol in ("mqtt", "both"):
                await self.mqtt.stop()
            if protocol in ("opcua", "both"):
                await self.opcua.stop()
            self.protocol = self._running_protocol()

    async def update_values(
        self,
        values: dict[str, tuple[Any, str]],
        timestamp: str | None = None,
        current_values: dict[str, CurrentValue] | None = None,
        mqtt_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        await self.update_channel_values(self.protocol, values, timestamp=timestamp, current_values=current_values, mqtt_metadata=mqtt_metadata)

    async def update_channel_values(
        self,
        protocol: str,
        values: dict[str, tuple[Any, str]],
        timestamp: str | None = None,
        current_values: dict[str, CurrentValue] | None = None,
        mqtt_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        if protocol not in ("opcua", "mqtt", "both"):
            raise ValueError("Protocol must be opcua, mqtt, or both.")
        with self._io_lock:
            if protocol in ("opcua", "both"):
                await self.opcua.update_values(values)
            if protocol in ("mqtt", "both"):
                await self.mqtt.update_values(values, timestamp=timestamp, current_values=current_values, mqtt_metadata=mqtt_metadata)

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
    """Adapter view for one protocol while sharing the same underlying services.

    This lets OPC UA and MQTT run at the same time with different file sets.
    An OPC UA replay engine sends only to OPC UA; an MQTT replay engine sends only
    to MQTT. Both channels still share the same UI status and lifecycle.
    """

    def __init__(self, parent: DualProtocolAdapter, protocol: str) -> None:
        if protocol not in ("opcua", "mqtt"):
            raise ValueError("ProtocolChannelAdapter supports only 'opcua' or 'mqtt'.")
        self.parent = parent
        self.protocol = protocol

    async def start(self) -> None:
        await self.parent.start_channels(self.protocol)

    async def stop(self) -> None:
        # Engines call stop during reconfiguration. Do not stop shared protocol
        # services here; MultiSimulatorEngine owns final service shutdown.
        return None

    async def configure_tags(self, config: ReplayConfig) -> None:
        await self.parent.configure_channel_tags(self.protocol, config)

    async def update_values(
        self,
        values: dict[str, tuple[Any, str]],
        timestamp: str | None = None,
        current_values: dict[str, CurrentValue] | None = None,
        mqtt_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        await self.parent.update_channel_values(self.protocol, values, timestamp=timestamp, current_values=current_values, mqtt_metadata=mqtt_metadata)

    def get_endpoint(self) -> str:
        if self.protocol == "opcua":
            return self.parent.opcua.get_endpoint()
        return self.parent.mqtt.get_endpoint()


class ReplayJobProtocolAdapter:
    """Per-job protocol view over the shared protocol services."""

    def __init__(self, parent: DualProtocolAdapter, protocol: str) -> None:
        if protocol not in ("opcua", "mqtt", "both"):
            raise ValueError("ReplayJobProtocolAdapter supports opcua, mqtt, or both.")
        self.parent = parent
        self.protocol = protocol

    async def configure_tags(self, config: ReplayConfig) -> None:
        # Managed replay jobs reconfigure the shared protocol services with the
        # union of all active job tags. Individual engines should not clear the
        # server/broker tag catalog while another job is running.
        return None

    async def start(self) -> None:
        await self.parent.start_channels(self.protocol)

    async def stop(self) -> None:
        return None

    async def update_values(
        self,
        values: dict[str, tuple[Any, str]],
        timestamp: str | None = None,
        current_values: dict[str, CurrentValue] | None = None,
        mqtt_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        await self.parent.update_channel_values(self.protocol, values, timestamp=timestamp, current_values=current_values, mqtt_metadata=mqtt_metadata)

    def get_endpoint(self) -> str:
        if self.protocol == "opcua":
            return self.parent.opcua.get_endpoint()
        if self.protocol == "mqtt":
            return self.parent.mqtt.get_endpoint()
        return self.parent.get_endpoint()
