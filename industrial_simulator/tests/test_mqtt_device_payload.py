import asyncio

from app.models import ReplayConfig, TagMapping
from app.mqtt_publisher import MqttTagPublisher


def test_mqtt_all_topic_uses_device_payload_shape():
    async def run():
        publisher = MqttTagPublisher()
        publisher.mock_mode = True
        config = ReplayConfig(
            protocol="mqtt",
            csv_file="demo.csv",
            csv_source="uploaded",
            mqtt_topic_prefix="meters/flow01",
            mqtt_device_id="FlowMeter01",
            tags=[
                TagMapping(csv_column="Flow", tag_name="demo_Flow", node_id="TagSimulator.demo.Flow", data_type="Int64"),
                TagMapping(csv_column="Pressure", tag_name="demo_Pressure", node_id="TagSimulator.demo.Pressure", data_type="Double"),
            ],
        )
        await publisher.configure_tags(config)
        await publisher.update_values(
            {
                "TagSimulator.demo.Flow": (1200, "Int64"),
                "TagSimulator.demo.Pressure": (2.3, "Double"),
            },
            timestamp="2026-05-28T10:15:30Z",
            mqtt_metadata={
                "TagSimulator.demo.Flow": {"tag": "Flow", "unit": "LPH", "quality": "GOOD"},
                "TagSimulator.demo.Pressure": {"tag": "Pressure", "unit": "Bar", "quality": "GOOD"},
            },
        )
        return publisher.last_payloads["meters/flow01/all"]

    assert asyncio.run(run()) == {
        "timestamp": "2026-05-28T10:15:30Z",
        "deviceId": "FlowMeter01",
        "data": [
            {"tag": "Flow", "value": 1200, "unit": "LPH", "quality": "GOOD"},
            {"tag": "Pressure", "value": 2.3, "unit": "Bar", "quality": "GOOD"},
        ],
    }
