# Purpose

The Industrial MQTT Tag Simulator is a local web-based utility for generating and replaying synthetic industrial process data over MQTT.

It lets users generate domain-plausible CSV data, inspect or upload CSV files, map CSV columns to MQTT tag topics, and replay rows to an MQTT broker at a controlled frequency.

## Intended uses

- Testing MQTT clients, collectors, brokers, historians, dashboards, and IoT ingestion pipelines.
- Creating repeatable industrial tag streams without connecting to a real PLC, SCADA system, or plant historian.
- Demonstrating process scenarios such as petroleum pipeline normal/leak conditions, EAF melting, steel processes, gas pipeline, power plant, and rotary equipment.

## Data flow

```text
Domain Generator -> CSV File -> Replay Engine -> MQTT Publisher -> External MQTT Client
```

Uploaded CSV files follow the same replay path.

## MQTT behavior

The simulator publishes each enabled tag as JSON to:

```text
<topic_prefix>/<topic_suffix>
```

It can also publish the whole row to:

```text
<topic_prefix>/all
```

The default broker target is:

```text
mqtt://localhost:1883/industrial-tag-simulator
```

## Scope

The generated data is synthetic and domain-plausible. It is designed for simulation, demo, testing, and pipeline validation, not for operational control or safety-critical decisions.
