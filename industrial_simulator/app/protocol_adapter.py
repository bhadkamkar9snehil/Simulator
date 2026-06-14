from __future__ import annotations

from typing import Any

from app.models import ReplayConfig, CurrentValue, ProtocolMode
from app.opcua_server import OpcUaTagServer
from app.mqtt_publisher import MqttTagPublisher


class DualProtocolAdapter:
    def __init__(self) -> None:
        self.opcua = OpcUaTagServer()
        self.mqtt = MqttTagPublisher()
        self.protocol: ProtocolMode = "opcua"

    async def start(self) -> None:
        if self.protocol in ("opcua", "both"):
            await self.opcua.start()
        if self.protocol in ("mqtt", "both"):
            await self.mqtt.start()

    async def stop(self) -> None:
        await self.mqtt.stop()
        await self.opcua.stop()

    async def configure_tags(self, config: ReplayConfig) -> None:
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

    async def update_values(
        self,
        values: dict[str, tuple[Any, str]],
        timestamp: str | None = None,
        current_values: dict[str, CurrentValue] | None = None,
        mqtt_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        if self.protocol in ("opcua", "both"):
            await self.opcua.update_values(values)
        if self.protocol in ("mqtt", "both"):
            await self.mqtt.update_values(values, timestamp=timestamp, current_values=current_values, mqtt_metadata=mqtt_metadata)

    def get_endpoint(self) -> str:
        if self.protocol == "opcua":
            return self.opcua.get_endpoint()
        if self.protocol == "mqtt":
            return self.mqtt.get_endpoint()
        return f"OPC UA: {self.opcua.get_endpoint()} | MQTT: {self.mqtt.get_endpoint()}"

    def get_status(self) -> dict[str, Any]:
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
        self.parent.protocol = "both"
        if self.protocol == "opcua":
            await self.parent.opcua.start()
        else:
            await self.parent.mqtt.start()

    async def stop(self) -> None:
        # Engines call stop during reconfiguration. Do not stop shared protocol
        # services here; MultiSimulatorEngine owns final service shutdown.
        return None

    async def configure_tags(self, config: ReplayConfig) -> None:
        self.parent.protocol = "both"
        if self.protocol == "opcua":
            await self.parent.opcua.stop()
            await self.parent.opcua.start()
            await self.parent.opcua.configure_tags(config)
        else:
            await self.parent.mqtt.start()
            await self.parent.mqtt.configure_tags(config)

    async def update_values(
        self,
        values: dict[str, tuple[Any, str]],
        timestamp: str | None = None,
        current_values: dict[str, CurrentValue] | None = None,
        mqtt_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        if self.protocol == "opcua":
            await self.parent.opcua.update_values(values)
        else:
            await self.parent.mqtt.update_values(values, timestamp=timestamp, current_values=current_values, mqtt_metadata=mqtt_metadata)

    def get_endpoint(self) -> str:
        if self.protocol == "opcua":
            return self.parent.opcua.get_endpoint()
        return self.parent.mqtt.get_endpoint()
