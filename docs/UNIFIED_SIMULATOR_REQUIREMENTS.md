# Unified Multi-Interface Simulator

## Product and Architecture Requirements

**Status:** Draft baseline requirements  
**Applies to:** Simulator repository  
**Purpose:** Define the target product architecture and functional/non-functional requirements for evolving Simulator into a unified, concurrent, multi-source, multi-protocol industrial simulation platform.

---

## 1. Executive Summary

Simulator shall evolve from a collection of protocol- and workload-specific simulation paths into a **single unified simulation platform** capable of running **many independent or coordinated simulations concurrently**.

The primary product focus is **end-to-end OPC UA simulation of multiple independent simulations at the same time, each able to serve one or more targets and each fully configurable from a simulation-centric UI**. Other protocols and targets must fit the same model, but they must not complicate or distract from making the multi-simulation OPC UA path excellent first.

Each simulation instance shall be able to:

- obtain data from a file, generated domain model, database, external interface, recorded stream, or another supported source;
- run with its own independent clock, cursor, speed, loop policy, fault/scenario configuration, state, mappings, and lifecycle;
- publish the resulting simulated state concurrently to one or more protocol/interface targets;
- share protocol listeners with other simulations when appropriate, or expose a dedicated listener/endpoint when required for integration realism;
- continue serving healthy targets even when another target is unavailable or degraded;
- participate optionally in a larger coordinated simulated **World** where multiple interface simulations represent the same plant, process, order, batch, equipment, or integration landscape;
- be created, tuned, inspected and controlled without requiring users to understand internal runtime ownership or protocol-combination mechanics.

The desired product is therefore not merely a data generator or replay tool. It is a **systems and interface simulator** for industrial integration, OT/IT testing, development, demonstrations, digital-twin-like scenarios, performance testing, and end-to-end validation.

The architectural north star is:

```text
Sources
   ↓
Simulation Instances
   ↓
Canonical State / Events
   ↓
Mappings / Transformations
   ↓
Target Bindings
   ↓
Shared or Dedicated Interface Hosts
```

The primary user-facing form of that model is:

```text
Simulation Workspace
   ↓
Simulation A ── Source / Clock / Mapping ── OPC UA + optional targets
Simulation B ── Source / Clock / Mapping ── OPC UA + optional targets
Simulation C ── Source / Clock / Mapping ── dedicated OPC UA endpoint
...
```

The platform must support the simple case:

> Play this CSV to OPC UA at 5 Hz.

and scale to cases such as:

> Run dozens of simultaneous simulated assets from multiple files and generators, expose some through shared OPC UA, others as dedicated OPC UA or Modbus devices, publish selected values to MQTT and HTTP, mirror data into SQL, simulate SAP/LIMS interfaces, and coordinate several simulations as one plant.

---

## 2. Requirement Language

The keywords **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are normative:

- **MUST / MUST NOT**: required for the target architecture.
- **SHOULD / SHOULD NOT**: strongly preferred unless there is a documented reason otherwise.
- **MAY**: optional capability or future extension point.

---

## 3. Product Goals

### G-001 — One Simulator Product

The repository MUST represent one coherent Simulator product rather than separate protocol-specific or source-specific simulator products.

Protocol implementations, source simulators, generators, replay capabilities, SQL exposure, SAP/OData behavior, LIMS behavior, HTTP streaming, and future interfaces MUST be presented as capabilities of the unified platform.

### G-002 — Concurrent Simulations

The runtime MUST support multiple simulation instances executing simultaneously in the same installation.

Simulation instances MUST NOT rely on one global cursor, one global replay state, one global protocol choice, or one global source.

### G-003 — Source/Simulation/Target Separation

The architecture MUST treat the following as separate concerns:

1. **Source** — where input data or generated state originates.
2. **Simulation Instance** — how data evolves through simulated time.
3. **Mapping / Transformation** — how canonical simulation data is projected for a target.
4. **Target** — where/how the simulation is exposed.
5. **Interface Host** — the actual shared or dedicated network listener/server/broker when a protocol requires one.

### G-004 — Protocol Independence

The simulation engine MUST NOT contain protocol combinations such as `opcua`, `mqtt`, `both`, `opcua+sql`, etc.

A simulation SHALL instead own zero or more target bindings.

Adding a new target type MUST NOT require modifications to combinatorial protocol-mode logic in the simulation engine.

### G-005 — Coherent Multi-Interface Worlds

The platform SHOULD support coordinated simulations where several interfaces expose different views of the same underlying simulated world.

Example:

```text
Pump trip
   ↓
OPC UA pressure and flow values change
   ↓
MQTT alarm emitted
   ↓
Historian/SQL records degraded throughput
   ↓
SAP production confirmation falls below target
   ↓
LIMS quality values may subsequently change
```

### G-006 — OPC UA End-to-End Priority

The first-class product path MUST make multi-simulation OPC UA operation excellent before secondary interface work is considered complete.

This includes:

- many concurrent simulations;
- independent sources and clocks;
- shared OPC UA hosting;
- dedicated OPC UA endpoints;
- per-simulation namespace/root/NodeId configuration;
- collision-safe multi-simulation node exposure;
- independent lifecycle and health;
- live values and publish metrics;
- full UI configuration without requiring raw JSON editing;
- optional secondary targets attached to the same simulation.

### G-007 — UI as a Primary Product Surface

The UI MUST be treated as part of the product architecture, not as a thin administrative shell.

Users MUST be able to perform the normal simulation lifecycle and configuration visually. Advanced configuration MAY expose raw structures for diagnostics/import/export, but ordinary operation MUST NOT require hand-editing JSON.

---

## 4. Core Domain Concepts

### 4.1 Simulation Source

A **Source** provides data or state to a simulation instance.

A source MUST be independently configurable and MUST NOT know which protocol targets will consume its data.

Initial and future source types include:

- CSV
- Excel/XLSX
- Parquet
- JSONL / NDJSON
- generated industrial domain model
- SQL query/database source
- HTTP/API source
- SAP/OData fixture/source
- LIMS/ODBC fixture/source
- recorded OPC UA data
- recorded MQTT data
- imported historian data
- generated video or image data where applicable
- other plugins/adapters added later

A single source MAY be used by multiple simulation instances simultaneously. Each instance MUST maintain its own independent cursor and time state unless explicitly configured to share state.

### 4.2 Simulation Instance

A **Simulation Instance** is the primary runtime object and the primary UI editing object.

Each simulation instance MUST have a stable identifier and SHOULD have a human-friendly name.

A simulation instance owns or references:

- source binding;
- clock configuration;
- cursor/replay position;
- speed/time scaling;
- loop/replay policy;
- scenario/fault configuration;
- transformations/mappings;
- target bindings;
- current canonical state;
- lifecycle state;
- health/degradation state;
- metrics;
- errors;
- checkpoints/persistence metadata.

Conceptual model:

```python
SimulationInstance(
    id="sim_001",
    name="Plant 1 Petroleum Replay",
    source=SourceBinding(...),
    clock=SimulationClock(...),
    replay=ReplayPolicy(...),
    mappings=[...],
    targets=[...],
)
```

### 4.3 Canonical Frame / Event Model

All simulations MUST produce protocol-neutral canonical state before target-specific translation.

The current concept of passing protocol-specific metadata such as MQTT metadata through a generic publisher interface SHOULD be removed over time.

A canonical sample/frame SHOULD contain at minimum:

```python
Frame(
    simulation_id="sim_001",
    timestamp="...",
    sequence=12405,
    values={
        "pressure": SignalValue(
            value=21.7,
            data_type="double",
            quality="GOOD",
            unit="bar",
            metadata={}
        )
    },
    context={
        "batch_id": "B123",
        "order_id": "PO92832"
    }
)
```

Canonical signal values SHOULD support:

- stable identity/key;
- value;
- data type;
- timestamp;
- quality;
- engineering unit;
- optional description;
- optional source identity;
- optional metadata;
- optional alarm/event semantics.

### 4.4 Target Binding

A **Target Binding** associates a simulation instance with an output interface.

A target binding MUST contain its own configuration and runtime state.

Examples:

- OPC UA namespace/root binding;
- MQTT broker/topic binding;
- HTTP endpoint/stream binding;
- SQL Server table/projection binding;
- OData entity projection;
- Kafka topic binding;
- Modbus TCP device binding.

A simulation MAY have any number of target bindings.

### 4.5 Interface Host

An **Interface Host** owns a network listener/server/broker and MUST be separated conceptually from a simulation instance.

This distinction is required because many simulation instances may share one network listener.

Examples:

- one OPC UA server hosting several simulation namespaces;
- one MQTT broker serving multiple simulation topic trees;
- one HTTP server exposing many simulation endpoints;
- one OData host exposing several entity sets or worlds.

Stopping one simulation MUST NOT automatically terminate a shared interface host used by other simulations.

### 4.6 World

A **World** is an optional coordination layer grouping simulations that represent one coherent environment.

A World MAY define shared identities and state such as:

- plant;
- production order;
- batch;
- product;
- equipment;
- material;
- simulated clock;
- scenario events;
- common fault/event timeline.

A World MUST NOT be required for simple single-source replay.

---

## 5. Multi-Simulation Requirements

### SIM-001 — Independent Execution

Every simulation instance MUST maintain independent:

- lifecycle state;
- cursor;
- clock;
- speed;
- source binding;
- errors;
- metrics;
- target list.

### SIM-002 — Simultaneous Execution

The runtime MUST permit many simulations to execute concurrently.

The implementation SHOULD avoid a design where each simulation requires a separate process unless isolation is explicitly requested.

### SIM-003 — Same Source, Multiple Simulations

The same file/dataset/generator MAY back multiple independent simulation instances.

Example:

```text
petroleum.csv
  ├─ Simulation A: 1× real-time → OPC UA
  ├─ Simulation B: 50× → OPC UA + MQTT
  └─ Simulation C: fixed 10 Hz → dedicated OPC UA + SQL
```

### SIM-004 — Multiple Targets per Simulation

A simulation MUST be able to publish one canonical state stream simultaneously to multiple target bindings.

### SIM-005 — Dynamic Target Lifecycle

Where technically safe for a target type, the system SHOULD allow targets to be added, stopped, restarted, or removed without stopping the parent simulation.

### SIM-006 — Per-Simulation Control

Each simulation MUST support at least:

- configure;
- start;
- pause;
- resume;
- stop;
- restart;
- inspect status;
- inspect errors;
- inspect metrics;
- reset/seek cursor where supported.

### SIM-007 — Group Control

The UI/API SHOULD support selecting several simulations and performing group operations such as start, pause, resume, and stop.

### SIM-008 — Runtime Isolation

Failure in one simulation MUST NOT crash unrelated simulations.

### SIM-009 — Per-Simulation Fine Tuning

Every simulation MUST be independently configurable without mutating unrelated simulations.

The UI and API SHOULD expose, as applicable:

- source selection and source-specific options;
- start/end position;
- timing mode;
- fixed frequency;
- source timestamp speed multiplier;
- loop policy;
- context fields;
- signal inclusion/exclusion;
- signal rename/type/unit/quality/scale/offset mapping;
- scenario/fault options for generator-backed sources;
- target queue/failure policy;
- OPC UA shared/dedicated mode and endpoint details;
- target-specific settings for additional protocols.

---

## 6. Clock and Replay Requirements

### CLK-001 — Independent Clocks

Each simulation MUST own or reference an independent simulation clock.

### CLK-002 — Clock Modes

The platform SHOULD support:

- wall-clock fixed-rate playback;
- source timestamp playback;
- source timestamp playback at a time multiplier;
- maximum-throughput playback;
- step/manual advancement;
- coordinated World clock.

### CLK-003 — Time Scaling

Simulations SHOULD support acceleration and deceleration such as 0.5×, 1×, 5×, 50×, etc., subject to target throughput constraints.

### CLK-004 — Replay Policies

Replay policies SHOULD include:

- once;
- loop forever;
- hold last;
- ping-pong where meaningful;
- finite repeat count;
- start row/offset;
- optional end row/offset.

### CLK-005 — Determinism

Generated simulations SHOULD support deterministic replay through explicit seeds and stable scenario parameters where practical.

---

## 7. Source Requirements

### SRC-001 — Common Source Contract

Source implementations SHOULD conform to a deliberately small contract similar to:

```python
class SimulationSource:
    async def open(self): ...
    async def next(self) -> Frame: ...
    async def seek(self, position): ...
    async def close(self): ...
```

Not every source must support seeking. Unsupported operations MUST be explicit.

### SRC-002 — File Sources

The platform MUST continue supporting CSV and SHOULD support Excel and Parquet consistently through the common source model.

### SRC-003 — Generator Sources

Industrial domain generators MUST be usable as first-class simulation sources and MUST NOT need protocol-specific logic.

### SRC-004 — External Sources

The architecture MUST leave room for database/API/protocol sources without requiring changes to the simulation engine.

### SRC-005 — Source Metadata

Sources SHOULD expose schema/type metadata, row/sample counts where known, seek capability, and source identity.

---

## 8. Target and Protocol Requirements

### TGT-001 — Common Target Contract

Targets SHOULD conform to a small contract similar to:

```python
class SimulationTarget:
    async def start(self): ...
    async def publish(self, frame: Frame): ...
    async def stop(self): ...
    async def status(self): ...
```

Protocol-specific behavior MUST remain inside the target/host implementation.

### TGT-002 — Initial Target Families

The architecture MUST accommodate at least:

- OPC UA;
- MQTT;
- HTTP REST/snapshot;
- HTTP NDJSON;
- Server-Sent Events;
- WebSocket;
- SQL Server;
- OData/SAP-style HTTP APIs;
- file export (CSV/Parquet).

Future target families MAY include:

- Modbus TCP;
- Kafka;
- S7;
- EtherNet/IP;
- AMQP;
- other industrial/enterprise interfaces.

### TGT-003 — No Protocol Combination Enumeration

There MUST NOT be a growing enumeration of combinations such as `both` or `opcua_mqtt_sql`.

Targets MUST be represented as a collection.

### TGT-004 — Target-Specific Mapping

Each target MAY define protocol-specific mapping configuration, but such configuration MUST NOT pollute the canonical simulation model.

Examples:

- OPC UA NodeIds, namespace and hierarchy;
- MQTT topics and message envelopes;
- SQL table/column mappings;
- OData entity/property mappings.

---

## 9. Shared and Dedicated Interface Hosting

### HOST-001 — Shared Host Mode

Protocols that support multiplexing SHOULD support a shared-host mode.

Examples:

```text
OPC UA :4840
  Objects/PlantA/...
  Objects/PlantB/...
  Objects/FurnaceTest/...
```

```text
MQTT :1883
  simulator/plantA/...
  simulator/plantB/...
  simulator/test1/...
```

### HOST-002 — Dedicated Host Mode

The platform MUST allow dedicated endpoints where an integration test needs realistic separation.

Example:

```text
Simulation A → OPC UA :4840
Simulation B → OPC UA :4841
Simulation C → OPC UA :4842
```

### HOST-003 — Hosting Mode

Target configuration SHOULD support:

```text
hosting_mode = shared | dedicated
```

### HOST-004 — Reference Counting / Ownership

Shared hosts MUST remain active while any active target binding depends on them.

Simulation shutdown MUST release only its own binding, not globally stop shared services.

### HOST-005 — Listener Lifecycle

The runtime SHOULD manage listener lifecycle through a dedicated `InterfaceHostManager` or equivalent responsibility.

---

## 10. Failure Isolation and Degraded Operation

### FLT-001 — Per-Target Health

Each target MUST expose independent health/state.

Example:

```text
OPC UA  RUNNING
MQTT    RUNNING
SQL     ERROR / RETRYING
HTTP    RUNNING
```

### FLT-002 — Simulation Degraded State

A simulation MAY remain running when one target fails.

The simulation SHOULD expose an aggregate state such as `RUNNING`, `DEGRADED`, `PAUSED`, `STOPPED`, `COMPLETED`, or `ERROR`.

### FLT-003 — Target Failure Policy

A target binding SHOULD support configurable behavior such as:

- continue;
- retry;
- stop target only;
- stop parent simulation.

The default for ordinary network target failures SHOULD normally be continue + retry.

### FLT-004 — Explicit Mock/Test Behavior

Missing core protocol dependencies MUST NOT silently switch production runtime into a mock mode.

Mock/fake interfaces SHOULD be explicitly selected for tests.

---

## 11. Backpressure and Throughput

### BPR-001 — Target Independence

A slow target MUST NOT automatically block unrelated healthy targets.

### BPR-002 — Per-Target Queues

The runtime SHOULD use bounded per-target delivery queues or equivalent isolation.

Conceptually:

```text
                    ┌→ queue → OPC UA worker
Simulation Frames ──┼→ queue → MQTT worker
                    ├→ queue → SQL worker
                    └→ queue → HTTP worker
```

### BPR-003 — Backpressure Policy

Target bindings SHOULD support explicit policies such as:

- block;
- batch;
- sample;
- drop oldest;
- drop newest.

The selected policy MUST be visible in configuration/status.

### BPR-004 — Metrics

Targets SHOULD report:

- queue depth;
- frames/messages delivered;
- frames/messages dropped;
- throughput;
- retry count;
- latest error;
- latest successful publish time;
- latency where measurable.

---

## 12. Mapping and Transformation Requirements

### MAP-001 — Protocol-Neutral Canonical State

Transformations SHOULD generally operate on canonical frames before target translation.

### MAP-002 — Mapping Scope

Mappings MAY define:

- rename;
- include/exclude;
- type coercion;
- scaling;
- unit conversion;
- hierarchy/path mapping;
- topic mapping;
- SQL/OData field mapping;
- derived values;
- static context fields.

### MAP-003 — Reusability

Mapping profiles SHOULD be reusable across simulation instances.

### MAP-004 — Validation

Mappings MUST be validated before a simulation is started where validation can be performed statically.

### MAP-005 — UI Mapping Editor

The normal UI SHOULD provide a tabular mapping editor with stable rows and clear columns for source signal, enabled state, target name/NodeId, datatype, unit, quality override, scale and offset.

Bulk enable/disable, search/filter and sensible defaults SHOULD reduce repetitive editing for large tag sets.

---

## 13. World / Coordinated Environment Requirements

### WRLD-001 — Optional Worlds

A World MUST remain optional.

Simple replay and generation workflows MUST NOT require users to define a World.

### WRLD-002 — Shared Identity

World simulations SHOULD be able to share identifiers such as:

- Plant;
- Equipment;
- Product;
- OrderID;
- BatchID;
- Material;
- sample/quality identity.

### WRLD-003 — Shared Clock

A World MAY supply a coordinated clock to member simulations.

### WRLD-004 — World Events

World-level scenario events SHOULD be able to influence multiple simulations.

Example:

```text
World event: compressor_trip at T+01:43:20
  → process generator changes pressure and flow
  → OPC UA reflects changed tags
  → MQTT emits trip alarm
  → SQL historian receives the degraded values
  → SAP projection reflects reduced output
```

### WRLD-005 — Independent Overrides

Member simulations SHOULD still permit local target configuration and, where safe, local scenario overrides.

---

## 14. Job and Runtime Management

### JOB-001 — Unified Job Control Primitive

Replay jobs, generated simulations, source-simulator jobs, video jobs, and future long-running simulations SHOULD share a small common lifecycle/control mechanism rather than duplicating pause/stop event dictionaries and stale-worker logic.

### JOB-002 — Avoid Over-Generalization

The common mechanism MUST remain small. The architecture MUST NOT introduce a large generic workflow framework merely to remove a small amount of duplication.

### JOB-003 — Persisted State

Runtime state SHOULD be persisted sufficiently to support:

- inspection after restart;
- identification of stale workers;
- configuration restoration;
- explicit recovery/restart behavior.

### JOB-004 — Error Visibility

Persistence errors and corrupt records SHOULD be visible through logs/status. Core state loaders SHOULD NOT silently erase or ignore failures without diagnostics.

---

## 15. API Requirements

### API-001 — Simulation-Centric API

The primary control API SHOULD be simulation-centric rather than protocol-centric.

Expected resource model:

```text
/simulations
/simulations/{id}
/simulations/{id}/start
/simulations/{id}/pause
/simulations/{id}/resume
/simulations/{id}/stop
/simulations/{id}/targets
/simulations/{id}/metrics
/sources
/targets or /interface-hosts
/worlds
```

Exact routes may evolve, but the object model MUST remain source/simulation/target oriented.

### API-002 — Global Exception Handling

The FastAPI application SHOULD use shared exception handlers rather than repetitive endpoint-level `try/except Exception` wrappers.

### API-003 — Capability Discovery

The API SHOULD expose supported:

- source types;
- target types;
- host modes;
- clock modes;
- mapping capabilities;
- domain generators.

---

## 16. User Interface Requirements

### UI-000 — Quality Bar

The UI MUST be treated as a production product surface with a consistently high visual and interaction quality bar.

It SHOULD be:

- simulation-centric rather than protocol-page-centric;
- legible at normal desktop viewing distances;
- stable in geometry so values appearing/disappearing do not move unrelated controls;
- visually restrained, using hierarchy and spacing instead of excessive decorative elements;
- fast to scan when many simulations are active;
- explicit about running/degraded/error state without relying only on color;
- progressively disclosed so common workflows stay simple and advanced controls remain available;
- keyboard- and form-friendly for users configuring many tags/targets;
- consistent across create, edit, inspect and live-operation states.

Normal product usage MUST NOT require raw JSON editing.

### UI-001 — Simulation Workspace

The primary UI MUST center on running and configured Simulation Instances rather than one global Replay screen.

The first-class workspace SHOULD provide:

- search and filtering;
- status grouping;
- multi-select/group controls;
- create and duplicate actions;
- clear separation between configured, running, paused, degraded, completed and errored instances;
- direct access to per-simulation configuration and diagnostics.

A simulation card/row SHOULD display at minimum:

- simulation name/id;
- source;
- lifecycle state;
- degraded state if applicable;
- clock mode/speed;
- cursor/progress where meaningful;
- target list and individual target health;
- OPC UA endpoint summary when present;
- throughput/basic metrics;
- pause/stop/inspect/edit actions.

Example concept:

```text
Plant A Line 1                                  Running
petroleum.csv • 5× • Loop

Source             Targets
CSV                OPC UA :4840 / PlantA      Running
                   MQTT simulator/plant-a     Running
                   SQL Historian01            Retrying

12,482 frames • 5.0 fps • cursor 23.1%
                            [Pause] [Stop] [Inspect]
```

### UI-002 — New Simulation Flow

Creating a simulation SHOULD follow a straightforward workflow:

1. identity and source;
2. timing/replay/scenario;
3. signal mappings;
4. OPC UA target configuration;
5. optional additional targets;
6. review;
7. save/start.

The flow SHOULD preserve the current draft while moving between sections. Validation SHOULD appear next to the affected field/section rather than only after submission.

### UI-003 — Simple Mode

The UI MUST keep simple workflows simple.

A user wanting “CSV → OPC UA at 5 Hz” SHOULD NOT need to understand Worlds, host managers, queue internals, or advanced architecture concepts.

A sensible default OPC UA target SHOULD be easy to add in one action and then optionally customize.

### UI-004 — Advanced Mode

Advanced configuration SHOULD expose shared/dedicated listeners, bind/advertised host, port/path, namespace URI, root folder, NodeId mapping, queue/backpressure policy, target failure policy, coordinated Worlds, and performance settings.

Advanced controls SHOULD be grouped by concern rather than presented as one dense form.

### UI-005 — Live Target Management

Where supported, the UI SHOULD allow target add/remove/restart while a simulation remains active.

### UI-006 — Per-Simulation Inspector/Editor

Opening a simulation SHOULD present one coherent inspector/editor with persistent simulation identity/status and sections equivalent to:

- Overview;
- Source;
- Timing & Replay;
- Scenario/Faults where applicable;
- Signals & Mapping;
- Targets;
- OPC UA details;
- Metrics;
- Errors/Logs.

Editing one section MUST NOT discard unsaved work in another section.

### UI-007 — OPC UA Configuration Experience

For OPC UA targets, the UI MUST expose at least:

- shared vs dedicated hosting;
- bind/advertised endpoint information;
- port;
- path;
- namespace URI;
- root folder;
- generated or configured NodeIds;
- tag count;
- current server/target state;
- endpoint copy action;
- validation/collision errors;
- live publish counters and latest error.

The UI SHOULD make the hierarchy understandable before start, including a preview of the resulting NodeId/root layout where practical.

### UI-008 — Large Mapping Usability

For simulations with many signals, the UI SHOULD support:

- search;
- filtering;
- bulk enable/disable;
- bulk prefix/root changes where safe;
- sticky headers;
- fixed important columns;
- clear changed/invalid states;
- avoiding full-page reflow during edits.

### UI-009 — No Duplicate Protocol Workflows

The product SHOULD NOT maintain separate user workflows such as “OPC UA Replay”, “MQTT Replay”, and “SQL Replay” for the same underlying simulation concept.

A user configures the Simulation once and attaches target bindings to it.

---

## 17. Interface-Specific Requirements

### 17.1 OPC UA

- MUST support existing OPC UA simulation behavior.
- MUST be the primary end-to-end multi-simulation implementation path.
- SHOULD support multiple simulations under one shared server without restarting unrelated simulations when membership changes.
- MUST support dedicated OPC UA endpoints/ports when requested.
- Each binding MUST have a collision-safe namespace/root/NodeId strategy.
- Server lifecycle MUST be owned by the host layer, not by one arbitrary simulation engine.
- Python/runtime compatibility workarounds SHOULD be isolated from domain/runtime logic.
- The target SHOULD expose endpoint, host mode, namespace/root, active tag count, publish counts and errors through runtime status.
- The UI MUST allow per-simulation fine tuning of OPC UA target settings.
- Shared-host membership changes SHOULD eventually use incremental namespace/group mutation rather than stop/rebuild of the listener.

### 17.2 MQTT

- MUST support multiple simulation topic trees concurrently.
- SHOULD allow shared broker and external broker modes.
- MAY allow dedicated broker processes/ports where needed.
- MQTT-specific envelopes, metadata, topic rules, quality fields, and aliases MUST remain in MQTT target code.
- A target queue SHOULD prevent a slow/disconnected MQTT path from blocking other targets.

### 17.3 HTTP / Streams

- SHOULD expose snapshots and streaming transports such as NDJSON, SSE and WebSocket.
- Routes SHOULD be simulation-aware.
- Shared HTTP hosting is the default model.

### 17.4 SQL Server

- SHOULD support mapping canonical simulation values/events to configured tables.
- SHOULD support batching for throughput.
- SQL failure MUST be independently observable and SHOULD NOT stop other targets by default.

### 17.5 SAP / OData

- SAP/OData simulation SHOULD be an interface capability of the unified Simulator rather than a separate product architecture.
- Existing useful standalone SAP simulator behavior SHOULD be either integrated or explicitly classified as reference/development tooling.
- SAP entities SHOULD be capable of sharing World identity with process simulations.

### 17.6 LIMS / ODBC

- LIMS simulation SHOULD follow the same unified source/target/World concepts rather than existing as an unrelated subsystem.

---

## 18. Architecture Requirements

### ARCH-001 — Target Structure

The long-term package structure SHOULD converge toward responsibilities similar to:

```text
industrial_simulator/
    core/
        runtime.py
        simulation.py
        clock.py
        models.py
        jobs.py

    domains/
        petroleum/
        steel/
        polyester/
        gnfc/
        ...

    sources/
        files/
        generators/
        sql/
        http/
        ...

    interfaces/
        base.py
        opcua/
        mqtt/
        http/
        odata/
        sql/
        files/
        ...

    mappings/

    datasets/

    api/
        routes/
        app.py
```

The exact physical structure MAY differ, but responsibility boundaries MUST remain clear.

### ARCH-002 — Runtime Managers

The runtime SHOULD contain responsibilities equivalent to:

```text
Runtime
  ├─ SimulationManager
  │    ├─ Simulation A
  │    ├─ Simulation B
  │    └─ Simulation C
  │
  └─ InterfaceHostManager
       ├─ shared OPC UA host(s)
       ├─ shared MQTT host(s)
       ├─ HTTP/OData host(s)
       └─ dedicated hosts as requested
```

### ARCH-003 — No Global Protocol State

There MUST NOT be one global active protocol value representing the whole application.

### ARCH-004 — No Simulation-Owned Shared Listener

Simulation instances MUST NOT exclusively own protocol listeners that may be shared by other simulations.

### ARCH-005 — Extensibility

Adding a new source or target SHOULD require implementing its source/target contract and registration metadata, not editing every runtime control path.

### ARCH-006 — UI Mirrors Runtime Concepts

The UI data model SHOULD map directly to persisted/runtime `SimulationDefinition`, source, mapping and target concepts.

Do not build a second UI-only configuration model that then requires complex translation into the runtime model.

---

## 19. Generator Design Requirements

### GEN-001 — Domain Generators Remain First-Class

Existing industrial domain generators are strategically useful and MUST remain supported.

### GEN-002 — Decompose Large Generate Loops

Generator implementations SHOULD progressively separate:

```text
parameter validation
  → initial state
  → phase/state determination
  → scenario/fault effects
  → process integration
  → derived metrics
  → canonical row/frame construction
```

### GEN-003 — Avoid Framework Explosion

The codebase SHOULD NOT create a class/interface for every scenario or fault solely to reduce cyclomatic-complexity metrics.

Plain functions and data-driven rules are preferred when sufficient.

### GEN-004 — Shared Generator Execution Path

Generator lookup, scenario validation, iterator fallback, and row production SHOULD be centralized instead of duplicated between small-file generation and enterprise/background generation paths.

---

## 20. Code Quality and Complexity Requirements

The earlier whole-repository review identified that complexity is concentrated rather than uniformly poor.

### CQ-001 — Complexity Policy

New or materially modified Python functions SHOULD target:

- McCabe/Radon A or B grade for normal code;
- C only when complexity is inherent and reviewed;
- D/E/F SHOULD be decomposed before acceptance unless explicitly grandfathered with justification.

The same principle applies to frontend code: avoid giant event-handler functions, protocol/state switch ladders, and duplicated form logic.

### CQ-002 — Delete Before Refactor

Dead, legacy, obsolete, and scaffolding code SHOULD be removed before introducing new abstraction layers.

### CQ-003 — Known Cleanup Priorities

The following are architectural cleanup requirements unless intentionally reactivated and documented:

1. retire/remove the legacy `api_studio` application from the active product path;
2. remove disabled API Studio port/status/config plumbing;
3. remove obsolete `portal/patch_portal_ui.py` and generated `portal_app.py.bak` artifacts;
4. remove or hide API operations that only report “not implemented” until real behavior exists;
5. unify duplicated job-control primitives;
6. centralize generator execution/validation;
7. remove dead always-false policy hooks such as default-disabled-column logic unless a real rule is introduced;
8. stop silent dependency-to-mock fallback for advertised production protocols;
9. use an explicit runtime release allowlist;
10. keep reference/development artifacts out of production release packages;
11. keep current documentation synchronized with actual architecture;
12. migrate user-facing replay workflows to Simulation Definitions and delete protocol-combination UI/backend paths once no callers remain.

### CQ-004 — Portal Server Simplification

The Portal control backend SHOULD use the already-adopted FastAPI stack rather than hand-written HTTP dispatch unless a measurable reason exists otherwise.

### CQ-005 — Async Concurrency Correctness

Coroutine-level synchronization MUST use appropriate async primitives where required. Threading locks MUST NOT be assumed to provide coroutine mutual exclusion across `await` boundaries.

### CQ-006 — Ponytail as a Continuous Rule

For each addition or refactor, prefer in this order:

1. delete if unnecessary;
2. reuse existing repository behavior;
3. use the standard library;
4. use an already-installed dependency;
5. add the smallest abstraction justified by more than one real use;
6. express repeated branching as clear data/configuration where that genuinely reduces decisions.

A UI component library or generic form framework MUST NOT be introduced merely because future reuse is imaginable.

---

## 21. Dependency and Runtime Requirements

### DEP-001 — Offline Windows Distribution

The existing ability to distribute a bundled Windows Python runtime and offline wheelhouse is valuable and SHOULD be preserved.

### DEP-002 — Runtime Integrity

Runtime manifest checks, wheel hashes, environment fingerprints, and readiness probes SHOULD be retained.

### DEP-003 — Compatibility Complexity

Large compatibility monkey patches SHOULD be isolated and periodically reevaluated against runtime/dependency versions.

In particular, the Python 3.14 / asyncua compatibility layer SHOULD be treated as technical debt to remove if a stable supported runtime/dependency combination allows it.

### DEP-004 — Minimize Parallel Web Stacks

The product SHOULD avoid carrying Flask, FastAPI, and a hand-written HTTP server simultaneously unless each has a documented active requirement.

---

## 22. Release and Repository Hygiene

### REL-001 — Explicit Release Allowlist

Release packaging SHOULD include only required runtime files/directories through an explicit allowlist.

### REL-002 — Exclude Development Material

Production releases MUST NOT accidentally include:

- backups;
- patch scripts used only during past UI work;
- old ZIPs;
- unrelated knowledge-base documents;
- reference simulator source trees not used at runtime;
- development notes;
- generated output;
- test caches;
- local runtime state.

### REL-003 — Local Quality Validation Only

GitHub Actions MUST NOT be used for this repository.

The repository SHOULD keep local/manual commands or scripts for at least:

- syntax/compile validation;
- unit/integration tests;
- cyclomatic-complexity inspection;
- release packaging validation;
- runtime-required-file verification.

No `.github/workflows/*`, GitHub-hosted CI, required Actions checks, CI badges, or documentation instructing future agents to add GitHub Actions SHOULD be present.

### REL-004 — Tagged Releases

Stable distributable versions MAY eventually be represented by GitHub Releases with clear versioning and release notes. This does not imply use of GitHub Actions or automated GitHub CI.

---

## 23. Security Requirements

### SEC-001 — Control Plane Exposure

Management/control endpoints SHOULD bind to localhost by default unless remote control is explicitly enabled.

### SEC-002 — Data Plane vs Control Plane

The product SHOULD distinguish network-accessible simulation interfaces (OPC UA, MQTT, etc.) from administrative/control APIs.

A protocol endpoint may intentionally be LAN-accessible while the management plane remains local or authenticated.

### SEC-003 — Remote Management

If remote management is supported, it MUST use an explicit authentication/authorization design rather than relying on wildcard CORS and LAN obscurity.

### SEC-004 — Configurable Binding

Shared and dedicated hosts SHOULD have explicit bind-address configuration.

---

## 24. Observability Requirements

### OBS-001 — Per-Simulation Metrics

Each simulation SHOULD report:

- lifecycle state;
- source state;
- current cursor/position where applicable;
- frames generated/read;
- simulation rate;
- wall-clock rate;
- current simulated timestamp;
- error count;
- latest error;
- target summary.

### OBS-002 — Per-Target Metrics

See backpressure metrics in BPR-004.

### OBS-003 — Host Metrics

Shared/dedicated interface hosts SHOULD expose:

- listener address/port;
- active bindings;
- active clients where available;
- messages/frames served;
- errors;
- uptime.

### OBS-004 — Structured Logs

Structured logging SHOULD be retained and extended with `simulation_id`, `target_id`, `source_id`, and `world_id` context where applicable.

---

## 25. Persistence and Configuration

### CFG-001 — Stable IDs

Sources, simulations, targets, mappings, hosts, and Worlds SHOULD use stable IDs separate from display names.

### CFG-002 — Reusable Definitions

Users SHOULD be able to save reusable:

- source definitions;
- target definitions;
- mapping profiles;
- simulation definitions;
- World definitions.

### CFG-003 — Secrets

Credentials MUST NOT be embedded into exported configuration artifacts without an explicit secure mechanism.

### CFG-004 — Import/Export

Configuration import/export SHOULD eventually support moving complete test environments between machines.

---

## 26. Performance and Scalability

### PERF-001 — Concurrent Instance Scale

The architecture MUST avoid assumptions that only one or two simulations are active.

### PERF-002 — Efficient Fan-Out

One canonical frame SHOULD be produced once and fanned out to multiple targets rather than regenerating domain state separately per protocol.

### PERF-003 — Batching

High-throughput targets such as SQL and file outputs SHOULD support batching.

### PERF-004 — Resource Limits

The runtime SHOULD support configurable limits for:

- concurrent simulations;
- queue sizes;
- target workers;
- generated rows/frames;
- memory consumption;
- file output size.

### PERF-005 — No Unbounded Queues

Target delivery queues MUST NOT grow without bound.

---

## 27. Testing Requirements

### TEST-001 — Source Contract Tests

Every source implementation SHOULD pass a shared contract-test suite where applicable.

### TEST-002 — Target Contract Tests

Every target SHOULD pass shared lifecycle and publish-contract tests.

### TEST-003 — Multi-Simulation Isolation

Tests MUST verify that simultaneous simulations maintain independent cursors, clocks, source state, and lifecycle.

### TEST-004 — Shared Host Tests

Tests MUST verify that stopping one simulation does not terminate shared hosts required by another simulation.

### TEST-005 — Target Failure Isolation

Tests MUST verify that failure of one target does not stop healthy targets unless configured failure policy explicitly requires it.

### TEST-006 — Backpressure Tests

Tests SHOULD verify behavior of bounded queues and configured drop/batch/block policies.

### TEST-007 — Coordinated World Tests

When Worlds are implemented, tests SHOULD verify identity and event propagation across multiple interface projections.

### TEST-008 — Compatibility Tests

OPC UA, MQTT, HTTP, SQL, and other protocol adapters SHOULD have realistic integration tests against representative clients where practical.

### TEST-009 — OPC UA Multi-Simulation Acceptance Tests

Local/manual automated tests MUST cover at minimum:

- two or more simultaneous simulations publishing different values through one shared OPC UA host;
- stopping one shared-host simulation while another continues;
- two or more dedicated OPC UA simulations on separate ports;
- namespace/root/NodeId collision prevention;
- independent clocks/cursors;
- one simulation publishing to OPC UA plus another target concurrently.

Testing requirements do not imply GitHub Actions.

---

## 28. Migration Requirements from Current Architecture

Migration SHOULD be incremental and preserve working behavior.

### Phase 1 — Documentation and Cleanup

- establish this requirements document as the architectural north star;
- remove clearly dead/legacy artifacts;
- correct stale architecture documentation;
- fix release packaging hygiene;
- keep local/manual test and complexity commands available;
- ensure GitHub Actions workflow files are absent.

### Phase 2 — Introduce Canonical Runtime Model

- define canonical `Frame`/`SignalValue` types;
- define source and target contracts;
- define `SimulationInstance` and `SimulationManager`;
- retain compatibility adapters around existing replay paths during migration.

### Phase 3 — OPC UA Multi-Simulation Foundation

- separate OPC UA listener ownership into `InterfaceHostManager` responsibility;
- support shared and dedicated OPC UA target bindings;
- permit arbitrary concurrent Simulation Instances;
- guarantee collision-safe node layout;
- avoid restarting unrelated shared-host simulations when membership changes;
- surface per-simulation OPC UA endpoint/config/status to the UI.

### Phase 4 — Simulation-Centric UI

- make the Simulations workspace the primary product workspace;
- build create/edit/duplicate/start/pause/resume/stop flows around `SimulationDefinition`;
- provide per-simulation source, timing, mapping and OPC UA target configuration;
- provide strong mapping usability for large signal sets;
- expose health, progress, throughput and errors clearly;
- preserve advanced controls through progressive disclosure.

### Phase 5 — Multi-Target Runtime

- add independent target bindings beyond OPC UA;
- add per-target health and failure policies;
- add target worker queues/backpressure;
- migrate HTTP streams, MQTT, SQL, OData and other interfaces into the same simulation workflow.

### Phase 6 — Remove Legacy Protocol Combination Paths

- move legacy replay/workload callers onto `SimulationManager`;
- delete global protocol state and `both` mode when no callers remain;
- delete duplicate protocol-centric UI paths after feature parity exists in the Simulations workspace.

### Phase 7 — Worlds

- add optional shared World identity/state/clock/event coordination;
- allow OT and enterprise interfaces to expose coherent views of one simulated environment.

---

## 29. Explicit Non-Goals / Guardrails

The following guardrails are important:

1. The platform MUST NOT become a giant generic workflow engine.
2. New abstractions MUST correspond to real multiplicity: multiple sources, multiple simulations, multiple targets, or multiple hosts.
3. A class/interface MUST NOT be introduced merely to reduce a complexity metric.
4. Simple workflows MUST remain easy.
5. Worlds MUST remain optional.
6. Protocol-specific concerns MUST NOT leak back into the simulation core.
7. Simulator MUST remain independent of downstream consuming applications. Integration-specific logic belonging to another product MUST remain outside Simulator unless it is a generic interface capability.
8. Existing useful offline Windows deployment behavior SHOULD not be sacrificed without a replacement of equal or better usability.
9. GitHub Actions MUST NOT be used.
10. Secondary target/protocol work SHOULD NOT delay making the multi-simulation OPC UA path and simulation-centric UI complete.
11. UI sophistication MUST NOT be implemented through unnecessary frontend architectural complexity; use the smallest clear component/data model that supports real reuse.

---

## 30. Example Target Scenarios

### Scenario A — Simple OPC UA Replay

```text
Source: CSV
Clock: fixed 5 Hz
Simulation: one instance
Target: OPC UA shared :4840 / LineA
```

### Scenario B — One Source, Multiple Targets

```text
Source: petroleum.csv
Clock: source timestamps at 5×
Targets:
  - OPC UA shared :4840 / PetroleumLine
  - MQTT shared :1883 simulator/petroleum
  - HTTP SSE /simulations/{id}/stream
  - SQL historian
```

### Scenario C — Same Source, Independent Simulations

```text
petroleum.csv
  ├─ sim-A: 1× → shared OPC UA / SimA
  ├─ sim-B: 50× → shared OPC UA / SimB + MQTT
  └─ sim-C: fixed 10 Hz → dedicated OPC UA :4842 + SQL
```

All three have independent cursors and lifecycle.

### Scenario D — Multiple Dedicated Devices

```text
sim-A → OPC UA :4840
sim-B → OPC UA :4841
sim-C → OPC UA :4842
sim-D → Modbus TCP :5020
```

Used when the test target expects multiple physically distinct endpoints.

### Scenario E — Coordinated Plant World

```text
World: GNFC Test Plant

Process Simulation
  → OPC UA
  → MQTT

SAP Simulation
  → OData

LIMS Simulation
  → ODBC/API

Historian Simulation
  → SQL

Shared:
  Plant
  Product
  OrderID
  BatchID
  simulation clock
  scenario event timeline
```

A process fault can consistently affect all relevant projections.

### Scenario F — High-Concurrency Integration Test

```text
40 active simulated assets
12 source files
5 generated domain models
15 shared OPC UA bindings
8 dedicated OPC UA endpoints
20 MQTT bindings
selected SQL mirroring
selected HTTP streams
several simulations coordinated into Worlds
```

The architecture MUST be capable of evolving toward this type of workload without combinatorial protocol branching.

---

## 31. Acceptance Criteria for the Architectural Foundation

The first major architectural milestone should be considered achieved when all of the following are true:

1. `SimulationInstance` is a first-class persisted/runtime object.
2. Two or more simulations can run concurrently with independent cursors and clocks.
3. One simulation can publish to OPC UA and one or more additional targets without a `both` protocol mode.
4. OPC UA host lifecycle is separated from simulation lifecycle.
5. Two simulations can share one OPC UA host without interfering with each other.
6. Dedicated OPC UA simulations can run concurrently on different endpoints.
7. At least one target can fail while the parent simulation and another target continue running.
8. Canonical frames do not contain MQTT-, OPC-UA-, SQL-, or OData-specific fields.
9. Source and target implementations use small contracts.
10. The primary UI can create, edit, duplicate, start, pause, resume and stop independent simulations.
11. The UI can fully configure a simulation's source, timing, mappings and OPC UA target without raw JSON editing.
12. The UI can display independent simulation and target state, endpoint, progress, throughput and errors.
13. Existing single-file replay remains straightforward for users.
14. Local/manual automated tests cover multi-simulation isolation and shared OPC UA ownership.
15. Legacy protocol-combination branches are no longer the central runtime or UI model.
16. No GitHub Actions workflow is present.

---

## 32. Architectural Decision Summary

The intended direction is:

```text
                           Unified Simulator Runtime

                 ┌─────────────────────────────────┐
                 │       SimulationManager         │
                 │                                 │
                 │  sim-A   sim-B   sim-C   ...   │
                 └──────────────┬──────────────────┘
                                │
                     Canonical Frames / Events
                                │
            ┌───────────────────┼────────────────────┐
            │                   │                    │
       Target Binding      Target Binding       Target Binding
            │                   │                    │
            ▼                   ▼                    ▼
        OPC UA Host          MQTT Host          HTTP/SQL/etc.

                 Optional World Coordination Layer
```

The fundamental design rule is:

> **Simulations own simulated state and time. Interface hosts own network endpoints. Target bindings connect the two.**

The product-priority rule is:

> **Make multi-simulation OPC UA operation and its simulation-centric UI impeccable first; make every other interface fit the same simple model rather than creating parallel workflows.**

These rules should guide future refactoring and prevent protocol lifecycle, simulation lifecycle, network listener lifecycle and UI workflow from becoming entangled again.
