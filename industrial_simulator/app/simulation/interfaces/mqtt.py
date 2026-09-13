from __future__ import annotations

from app.models import ReplayConfig
from app.mqtt_publisher import MqttTagPublisher

from ..models import SignalDefinition, SimulationFrame, TargetBinding, TargetRuntimeStatus
from .common import safe_name, tag_mapping


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
            signal.name: f"{safe_name(simulation_id)}.{safe_name(signal.node_id or signal.name)}"
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
            tags=[tag_mapping(signal, self._node_map[signal.name], signal.name) for signal in schema],
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
        publisher, self._publisher = self._publisher, None
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
