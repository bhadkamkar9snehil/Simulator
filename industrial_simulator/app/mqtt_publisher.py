from __future__ import annotations

import json
import os
import time
from typing import Any

from app.models import ReplayConfig, CurrentValue

try:
    import paho.mqtt.client as mqtt  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without paho-mqtt
    mqtt = None


class MqttTagPublisher:
    """Publishes replayed tag values to an MQTT broker.

    The class mirrors the publisher interface used by SimulatorEngine:
    start(), stop(), configure_tags(), update_values(), get_endpoint(), get_status().
    This keeps the replay engine mostly protocol-agnostic.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        topic_prefix: str = "industrial-tag-simulator",
        client_id: str = "industrial-tag-simulator",
    ):
        self.host = os.environ.get("MQTT_HOST", host)
        raw_port = str(os.environ.get("MQTT_BROKER_PORT", os.environ.get("MQTT_PORT", str(port)))).strip()
        try:
            self.port = int(raw_port or str(port))
        except ValueError:
            self.port = int(port)
        self.topic_prefix = topic_prefix.strip("/") or "industrial-tag-simulator"
        self.client_id = client_id
        self.device_id = "FlowMeter01"
        self.default_quality = "GOOD"
        self.username: str | None = None
        self.password: str | None = None
        self.qos = 0
        self.retain = False
        self.publish_individual_tags = True
        self.publish_aggregate = True
        self.client: Any = None
        self.running = False
        self.connected = False
        self.mock_mode = mqtt is None
        self.last_error: str | None = None
        self.tags: dict[str, Any] = {}
        self.last_payloads: dict[str, Any] = {}

    async def start(self) -> None:
        # Startup should not fail the whole web app if a broker is not running yet.
        # A real connection is attempted when replay is configured.
        if self.running:
            return
        self.running = True
        self.last_error = None

    async def stop(self) -> None:
        if self.client is not None:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception as exc:  # pragma: no cover - defensive shutdown
                self.last_error = str(exc)
        self.client = None
        self.connected = False
        self.running = False
        self.tags.clear()
        self.last_payloads.clear()

    async def configure_tags(self, config: ReplayConfig) -> None:
        self.host = config.mqtt_host
        self.port = int(config.mqtt_port)
        self.topic_prefix = config.mqtt_topic_prefix.strip("/") or "industrial-tag-simulator"
        self.device_id = (getattr(config, "mqtt_device_id", None) or "FlowMeter01").strip() or "FlowMeter01"
        self.client_id = config.mqtt_client_id or "industrial-tag-simulator"
        self.username = config.mqtt_username or None
        self.password = config.mqtt_password or None
        self.qos = int(config.mqtt_qos)
        self.retain = bool(config.mqtt_retain)
        self.publish_individual_tags = bool(config.publish_individual_tags)
        self.publish_aggregate = bool(config.publish_aggregate)
        self.tags = {tag.node_id: tag for tag in config.tags if tag.enabled}
        self.last_payloads.clear()
        await self._connect()

    async def update_values(
        self,
        values: dict[str, tuple[Any, str]],
        timestamp: str | None = None,
        current_values: dict[str, CurrentValue] | None = None,
        mqtt_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        if not self.running:
            await self.start()
        if not self.mock_mode and not self.connected:
            await self._connect()

        metadata = mqtt_metadata or {}

        for node_id, (value, data_type) in values.items():
            tag = self.tags.get(node_id)
            item = self._build_data_item(node_id, value, metadata.get(node_id, {}))
            tag_name = tag.tag_name if tag is not None else node_id
            topic_suffix = self._topic_safe(node_id)
            payload = {
                "timestamp": timestamp,
                "deviceId": self.device_id,
                "tag": item["tag"],
                "value": item["value"],
                "unit": item["unit"],
                "quality": item["quality"],
                "tag_name": tag_name,
                "node_id": node_id,
                "data_type": data_type,
            }
            if self.publish_individual_tags:
                await self._publish(f"{self.topic_prefix}/{topic_suffix}", payload)

        if self.publish_aggregate:
            aggregate_payload = self._build_device_payload(values, timestamp, metadata)
            await self._publish(f"{self.topic_prefix}/all", aggregate_payload)

            # StreamPipes and many dashboard tools work best with a flat JSON object.
            # /all publishes the requested device JSON envelope; /flat and
            # /streampipes publish the same row as simple top-level fields.
            flat_payload = self._build_flat_payload(values, timestamp)
            await self._publish(f"{self.topic_prefix}/flat", flat_payload)
            await self._publish(f"{self.topic_prefix}/streampipes", flat_payload)

    def get_endpoint(self) -> str:
        return f"mqtt://{self.host}:{self.port}/{self.topic_prefix}"

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "connected": self.connected,
            "endpoint": self.get_endpoint(),
            "host": self.host,
            "port": self.port,
            "topic_prefix": self.topic_prefix,
            "device_id": self.device_id,
            "client_id": self.client_id,
            "qos": self.qos,
            "retain": self.retain,
            "mock_mode": self.mock_mode,
            "last_error": self.last_error,
        }

    async def _connect(self) -> None:
        if self.mock_mode:
            self.running = True
            self.connected = False
            if mqtt is None:
                self.last_error = "paho-mqtt is not installed; running in mock mode."
            return

        if mqtt is None:
            self.mock_mode = True
            self.running = True
            self.connected = False
            self.last_error = "paho-mqtt is not installed; running in mock mode."
            return

        if self.client is not None and self.connected:
            return

        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id)
        except AttributeError:  # pragma: no cover - paho-mqtt 1.x compatibility
            self.client = mqtt.Client(client_id=self.client_id)

        if self.username:
            self.client.username_pw_set(self.username, self.password)

        def on_connect(client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
            try:
                self.connected = int(reason_code) == 0
            except Exception:
                self.connected = str(reason_code) in ("Success", "0")

        def on_disconnect(client: Any, userdata: Any, flags: Any = None, reason_code: Any = None, properties: Any = None) -> None:
            self.connected = False

        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect

        try:
            self.client.connect(self.host, self.port, keepalive=60)
            self.client.loop_start()
            deadline = time.time() + 2.0
            while not self.connected and time.time() < deadline:
                time.sleep(0.05)
            if not self.connected:
                raise ConnectionError(f"Could not connect to MQTT broker at {self.host}:{self.port}.")
            self.running = True
            self.mock_mode = False
            self.last_error = None
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            raise ValueError(str(exc))


    def _build_device_payload(
        self,
        values: dict[str, tuple[Any, str]],
        timestamp: str | None,
        metadata: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Build the requested aggregate MQTT JSON message for /all.

        Output shape:
        {
          "timestamp": "2026-05-28T10:15:30Z",
          "deviceId": "FlowMeter01",
          "data": [
            {"tag": "Flow", "value": 1200, "unit": "LPH", "quality": "GOOD"}
          ]
        }
        """
        return {
            "timestamp": timestamp,
            "deviceId": self.device_id,
            "data": [
                self._build_data_item(node_id, value, metadata.get(node_id, {}))
                for node_id, (value, _data_type) in values.items()
            ],
        }

    def _build_data_item(self, node_id: str, value: Any, metadata: dict[str, Any]) -> dict[str, Any]:
        tag = self.tags.get(node_id)
        tag_label = metadata.get("tag")
        if not tag_label and tag is not None:
            # Use the original CSV/XLSX column name in MQTT. Protocol plans may
            # prefix tag_name/node_id to avoid collisions, but MQTT consumers
            # normally want the clean process tag name such as Flow or Pressure.
            tag_label = tag.csv_column or tag.tag_name
        if not tag_label:
            tag_label = node_id

        unit = metadata.get("unit")
        if unit is None or str(unit).strip() == "":
            unit = self._infer_unit(str(tag_label))

        quality = metadata.get("quality")
        if quality is None or str(quality).strip() == "":
            quality = self.default_quality

        return {
            "tag": str(tag_label),
            "value": value,
            "unit": str(unit),
            "quality": str(quality),
        }

    def _infer_unit(self, tag_name: str) -> str:
        name = tag_name.strip().lower().replace(" ", "_")
        unit_rules = [
            (("flow", "flowrate", "flow_rate"), "LPH"),
            (("pressure", "press", "bar"), "Bar"),
            (("temperature", "temp"), "C"),
            (("level", "percent", "percentage", "opening", "position"), "%"),
            (("speed", "rpm"), "RPM"),
            (("vibration",), "mm/s"),
            (("current", "amp"), "A"),
            (("voltage", "volt"), "V"),
            (("power",), "kW"),
            (("energy",), "kWh"),
            (("frequency",), "Hz"),
            (("torque",), "Nm"),
            (("density",), "kg/m3"),
            (("mass", "weight"), "kg"),
        ]
        for keys, unit in unit_rules:
            if any(key in name for key in keys):
                return unit
        return ""

    def _build_flat_payload(self, values: dict[str, tuple[Any, str]], timestamp: str | None) -> dict[str, Any]:
        """Build a StreamPipes-friendly flat MQTT message.

        StreamPipes maps fields by exact JSON key. In protocol-plan mode this
        simulator may prefix tag names with the source file name to keep OPC UA
        node IDs unique. That is useful for OPC UA, but it can leave an existing
        StreamPipes adapter showing "no data" if the adapter was created with
        the original CSV column names.

        To make MQTT stable for StreamPipes, publish both forms when they differ:
        - the configured tag name, e.g. eaf_melting_arc_stability_index
        - the original CSV column alias, e.g. arc_stability_index

        The payload remains a simple top-level JSON object; no nested values/tags
        are used on /flat or /streampipes.
        """
        payload: dict[str, Any] = {}
        if timestamp:
            payload["published_at"] = timestamp

        def add_field(name: str, value: Any, overwrite: bool = True) -> None:
            field = self._field_safe(name)
            if field.lower() == "timestamp":
                field = "csv_timestamp"
            if overwrite or field not in payload:
                payload[field] = value

        for node_id, (value, _data_type) in values.items():
            tag = self.tags.get(node_id)

            primary_name = tag.tag_name if tag is not None else node_id
            primary_field = self._field_safe(primary_name)
            if primary_field.lower() == "timestamp":
                primary_field = "csv_timestamp"
            if primary_field in payload:
                add_field(node_id, value, overwrite=True)
            add_field(primary_name, value, overwrite=True)

            # Add the original CSV/XLSX column name as an alias. This is the key
            # StreamPipes users normally see while creating the adapter.
            if tag is not None:
                add_field(tag.csv_column, value, overwrite=False)

        return payload

    def _field_safe(self, name: str) -> str:
        cleaned = str(name).strip().replace(" ", "_").replace(".", "_").replace("/", "_")
        cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in cleaned)
        while "__" in cleaned:
            cleaned = cleaned.replace("__", "_")
        return cleaned.strip("_") or "field"

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.last_payloads[topic] = payload
        if self.mock_mode:
            return
        if self.client is None or not self.connected:
            raise ValueError("MQTT client is not connected.")
        result = self.client.publish(topic, json.dumps(payload, default=str), qos=self.qos, retain=self.retain)
        if getattr(result, "rc", 0) != 0:
            raise ValueError(f"MQTT publish failed for topic {topic}: rc={result.rc}")

    def _topic_safe(self, node_id: str) -> str:
        cleaned = str(node_id).strip().replace(" ", "_")
        cleaned = cleaned.replace("//", "/").strip("/")
        return cleaned or "tag"
