# MQTT Conversion Notes

This package is converted from the original local industrial tag simulator to publish replayed values over MQTT.

## Main changes

- Replaced `app/opcua_server.py` with `app/mqtt_publisher.py`.
- Updated `SimulatorEngine` so replayed rows are sent to the MQTT publisher.
- Updated `/api/status` to report MQTT broker/topic status.
- Added MQTT broker settings to the replay UI.
- Changed tag mapping labels from node-centric terminology to MQTT topic terminology.
- Replaced `asyncua` with `paho-mqtt` in `requirements.txt`.
- Updated tests to use MQTT mock mode.

## Publish contract

Per-tag topic:

```text
<topic_prefix>/<topic_suffix>
```

Per-tag JSON payload:

```json
{
  "tag_name": "Flow Rate",
  "node_id": "TagSimulator.Flow_Rate",
  "value": 124.7,
  "data_type": "Double",
  "timestamp": "2026-01-01T00:00:00Z"
}
```

Aggregate topic:

```text
<topic_prefix>/all
```

Aggregate JSON payload:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "values": {
    "TagSimulator.Flow_Rate": 124.7
  },
  "tags": []
}
```

## Test command

```bash
PYTHONPATH=. pytest -q
```
