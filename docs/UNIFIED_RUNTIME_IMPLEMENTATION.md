# Unified Runtime Implementation Status

**Status:** active migration / alpha architecture  
**Normative requirements:** [UNIFIED_SIMULATOR_REQUIREMENTS.md](UNIFIED_SIMULATOR_REQUIREMENTS.md)

## Purpose

This document records what has actually been built toward the unified Simulator architecture. It is not a second requirements document. When implementation changes, update this file rather than weakening the requirements to match temporary limitations.

## Current runtime shape

```text
SimulationManager
├─ SimulationInstance A
│  ├─ SimulationSource
│  ├─ independent clock/cursor/lifecycle
│  └─ TargetRunner[]
│     ├─ bounded queue → OPC UA target
│     ├─ bounded queue → MQTT target
│     └─ bounded queue → HTTP target
├─ SimulationInstance B
│  └─ ...
├─ World definitions
└─ InterfaceHostManager
   ├─ shared OPC UA host(s)
   └─ dedicated OPC UA host(s)
```

The legacy replay engine remains available while callers are migrated. The unified runtime is additive at this stage, not a flag-day rewrite.

## Implemented first-class models

The new runtime provides explicit models for `SimulationDefinition`, `SourceBinding`, `TargetBinding`, `ClockSpec`, `SimulationFrame`, `SignalValue`, `SignalDefinition`, `SimulationStatus`, `TargetRuntimeStatus`, and `WorldDefinition`.

A Simulation Definition has an independent source, clock, loop mode, world association, and any number of enabled target bindings. There is no `both` protocol mode in the new architecture.

## Implemented sources

### CSV / XLSX / registered CSV dataset

Uses existing `csv_manager` and `dataset_manager` logic. CSV replay uses an extracted random-access index so large CSVs are not loaded fully into memory. XLSX currently uses the existing workbook reader.

### Existing domain generators

`GeneratorSimulationSource` adapts the existing generator registry. Existing domain generators remain the source of process behavior; the unified runtime does not duplicate them.

### Existing source simulators

`SourceSimulatorSimulationSource` adapts the existing SAP PP and LIMS source-simulator registry. Query results become canonical frames and can therefore be served through any new runtime target.

### Inline rows

A deliberately small in-memory source exists for API-driven tests, diagnostics, and lightweight examples. It is not intended to replace file/dataset management.

## Implemented targets

### OPC UA

The adapter reuses `OpcUaTagServer`.

Two hosting modes are represented:

- `shared`: several Simulation Instances are exposed through one OPC UA listener;
- `dedicated`: a simulation target receives its own configured OPC UA port/path.

Temporary migration limitation: the existing OPC UA server API builds one tag tree at configuration time. Therefore changing shared-host membership currently rebuilds that host with the union of member schemas. Publishing and reconfiguration are serialized with an `asyncio.Lock`. A later OPC UA cleanup should add incremental namespace/group mutation so membership changes do not restart the shared listener.

### MQTT

The adapter reuses `MqttTagPublisher`. Each target has its own publisher/client configuration while multiple targets may use the same broker. MQTT-specific topic/device/envelope behavior remains in the MQTT layer.

### HTTP

The existing FastAPI Industrial service acts as a shared HTTP host. An HTTP target exposes the Simulation Instance under `/api/v2/simulations/{simulation_id}/targets/{target_id}` with point-in-time frame access plus NDJSON, SSE, and WebSocket streams. The runtime's last canonical frame remains available after a finite simulation completes.

### Memory/internal

A minimal in-process target exists for tests and diagnostics. It is intentionally not a general plugin mechanism.

## Target isolation and backpressure

Each enabled target gets an independent bounded queue and worker. Target bindings configure:

- queue size;
- overflow policy: `block`, `drop_oldest`, or `drop_newest`;
- failure policy: `continue`, `retry`, or `stop_simulation`;
- retry delay.

A failing target therefore does not automatically stop the Simulation Instance or block other targets. Status exposes queue depth, dropped frames, published frames, endpoint, and last error.

## Timing and lifecycle

Each Simulation Instance owns its own timing state. Supported clock modes are currently fixed rate and source timestamps with speed multiplier and maximum sleep bound.

Supported loop modes are `once`, `loop_forever`, `hold_last`, and `ping_pong`.

Each instance supports start, pause, resume, and stop independently. Multiple instances execute concurrently under one `SimulationManager`.

## Worlds

World definitions group existing Simulation Instances and can start/stop them as a coordinated set. A World does not own protocol implementation and is not required for simple simulations.

World context can be attached to emitted canonical frames so downstream adapters can correlate related simulations.

## Persistence

Definitions and Worlds are stored as JSON in `configs/unified_simulations.json` using an atomic temporary-file replace. Runtime tasks are not blindly resurrected on process start; persisted definitions load in a non-running state.

A persistence error is surfaced in the runtime snapshot rather than silently being treated as a valid empty configuration.

## API

The unified API is namespaced under `/api/v2` so legacy APIs remain available during migration.

Primary routes include:

```text
GET    /api/v2/capabilities
GET    /api/v2/runtime
GET    /api/v2/interfaces
GET    /api/v2/simulations
POST   /api/v2/simulations
GET    /api/v2/simulations/{id}
PUT    /api/v2/simulations/{id}
DELETE /api/v2/simulations/{id}
POST   /api/v2/simulations/{id}/start
POST   /api/v2/simulations/{id}/pause
POST   /api/v2/simulations/{id}/resume
POST   /api/v2/simulations/{id}/stop
GET    /api/v2/simulations/{id}/snapshot
GET    /api/v2/simulations/{id}/targets/{target}
GET    /api/v2/simulations/{id}/targets/{target}/ndjson
GET    /api/v2/simulations/{id}/targets/{target}/sse
WS     /api/v2/simulations/{id}/targets/{target}/ws
GET    /api/v2/worlds
POST   /api/v2/worlds
PUT    /api/v2/worlds/{id}
DELETE /api/v2/worlds/{id}
POST   /api/v2/worlds/{id}/start
POST   /api/v2/worlds/{id}/stop
```

## Example: two simulations at once

Simulation A can use a generated process source and fan out to shared OPC UA and MQTT:

```json
{
  "simulation_id": "plant-a-process",
  "name": "Plant A Process",
  "source": {
    "kind": "generator",
    "config": {
      "domain_id": "petroleum_pipeline",
      "scenario": "normal"
    }
  },
  "clock": {"mode": "fixed_rate", "frequency_hz": 5, "speed": 1},
  "loop_mode": "loop_forever",
  "targets": [
    {
      "target_id": "plant-a-opcua",
      "kind": "opcua",
      "hosting_mode": "shared",
      "config": {"port": 4840, "root_folder": "Simulations"}
    },
    {
      "target_id": "plant-a-mqtt",
      "kind": "mqtt",
      "config": {"host": "localhost", "port": 1883, "topic_prefix": "simulator/plant-a"}
    }
  ]
}
```

At the same time Simulation B can replay a file independently to HTTP:

```json
{
  "simulation_id": "line-b-replay",
  "name": "Line B Replay",
  "source": {
    "kind": "csv",
    "config": {"filename": "line-b.csv", "csv_source": "uploaded"}
  },
  "clock": {"mode": "source_timestamp", "frequency_hz": 1, "speed": 10},
  "loop_mode": "once",
  "targets": [
    {"target_id": "line-b-http", "kind": "http"}
  ]
}
```

Their clocks, positions, errors, queues, targets, and lifecycle are independent.

## Compatibility bridge

The old `SimulatorEngine` still backs legacy replay routes. Its random-access CSV implementation has been moved into the new source layer and imported back into the old engine. This is intentional: migrate behavior toward the new architecture while reducing duplicate code rather than cloning the old engine.

Do not extend `ProtocolMode = opcua|mqtt|both` into new functionality. It exists for legacy compatibility only.

## Next migration work

The architecture is now present, but the migration is not complete. Priorities are:

1. migrate Portal workflow/UI from legacy replay/job concepts to first-class Simulation Definitions;
2. replace shared OPC UA rebuild-on-membership-change with incremental groups/namespaces;
3. adapt SQL Server projection as a real target with a persistent/batched writer rather than per-request Portal scripting;
4. consolidate SAP/OData behavior into a unified interface adapter instead of parallel applications;
5. migrate LIMS/ODBC serving into the same target/host ownership model where applicable;
6. move legacy replay/workload callers onto `SimulationManager`, then delete `MultiSimulatorEngine`, `DualProtocolAdapter`, and protocol-combination models when no callers remain;
7. retire disabled API Studio and its port/UI plumbing;
8. migrate Portal's hand-written HTTP control server to FastAPI;
9. tighten release packaging to an explicit runtime allowlist;
10. continue generator complexity reduction without introducing strategy-class forests.

Every deletion must follow caller migration and tests. The goal is less code and fewer concepts at the end of migration than at the beginning.
