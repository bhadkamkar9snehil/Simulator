# Unified Runtime Implementation Status

**Status:** active migration / alpha architecture  
**Normative requirements:** [UNIFIED_SIMULATOR_REQUIREMENTS.md](UNIFIED_SIMULATOR_REQUIREMENTS.md)  
**Prioritized backlog:** [PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md)

This file records what is actually implemented. It must not describe temporary limitations that no longer exist.

## Runtime shape

```text
SimulationManager
├─ SimulationInstance A
│  ├─ SimulationSource
│  ├─ independent clock / cursor / lifecycle
│  ├─ canonical mapping
│  └─ TargetRunner[]
│     ├─ bounded queue → OPC UA
│     ├─ bounded queue → REST API
│     ├─ bounded queue → MQTT
│     ├─ bounded queue → HTTP Stream
│     ├─ bounded queue → SQL Server
│     └─ bounded queue → OData
├─ SimulationInstance B
│  └─ ...
├─ World definitions
└─ shared/dedicated interface ownership
```

There is no protocol-combination mode in the unified runtime. Each Simulation Definition owns independent target bindings.

## Implemented sources

- CSV with indexed random access;
- XLSX through the existing reader;
- registered datasets;
- Parquet files and Parquet folders using row-group indexing/caching;
- existing industrial domain generators;
- existing SAP PP source simulator;
- existing LIMS/ODBC source simulator;
- inline rows for tests and lightweight API-driven scenarios.

All sources emit the same canonical frame model before target projection.

## Canonical mapping

Simulation Definitions support explicit signal mappings before fan-out:

- source → output name;
- NodeId override;
- data type override;
- unit and quality override;
- linear scale and offset;
- metadata additions;
- optional dropping of unmapped signals.

The mapping runs once per canonical frame. Protocol targets do not repeat source-specific transformation logic.

## OPC UA

OPC UA remains the primary end-to-end product path.

Implemented behavior includes:

- shared listeners for multiple concurrent simulations;
- dedicated endpoints;
- real configurable bind host;
- advertised host, port and endpoint path;
- namespace URI and root folder configuration;
- configurable shared per-target group folder;
- configurable shared per-target NodeId prefix;
- configured client-visible string NodeIds;
- duplicate/empty NodeId validation;
- collision-safe simulation + target identity;
- incremental shared-host group add/remove without restarting unrelated simulations;
- transactional shared-group creation/rollback;
- shared/dedicated socket conflict detection before bind;
- explicit failure when the OPC UA stack is unavailable rather than a production mock-success mode;
- configurable server name and Application URI;
- generated local server certificate/key or explicit certificate/private-key file paths;
- `None`, `Basic256Sha256 Sign`, `Basic256Sha256 SignAndEncrypt`, combined secure modes, and a mixed NoSecurity + secure mode;
- anonymous, username/password, or anonymous-or-username identity modes for simulation fixtures;
- host-level security/identity compatibility checks before a Simulation Instance joins an existing shared listener;
- per-target writable-signal selection;
- per-target OPC UA scalar type overrides without changing the protocol-neutral canonical frame model;
- explicit variable creation/write types for `Double`, `Float`, signed and unsigned 16/32/64-bit integers, `Boolean`, `String`, and `DateTime`;
- live host/member/tag/writable/security/authentication diagnostics.

Shared-host NodeIds are intentionally scoped/prefixed to prevent collisions between simulations unless an explicit per-target prefix is supplied. Dedicated endpoints use configured canonical NodeIds directly.

### Writable-node semantics

Writable nodes are an interface behavior, not a second source of simulation truth.

- only signals explicitly marked writable for that OPC UA target accept client writes;
- a client write changes the live OPC UA variable;
- the next canonical frame emitted by the Simulation Instance writes the simulated value again;
- in `hold_last`, after the finite source is exhausted no additional frame is emitted, so a client write can remain visible until restart/stop or another simulator update.

This deliberately avoids a second write-back state machine. If a future use case requires client writes to alter the source/canonical simulation state, that is a separate product requirement.

### OPC UA validation boundary

The code now has isolated tests for host ownership, conflicts, NodeIds, security configuration, per-target type/writable options, and value coercion. That does **not** replace real protocol validation.

Still required before calling OPC UA product-ready:

- local Windows run with the bundled Python/asyncua environment;
- two or more simultaneous shared Simulation Instances observed from a real OPC UA client;
- simultaneous dedicated endpoints;
- browse/read/subscription behavior against actual configured NodeIds/types;
- secure endpoint discovery/connection for the supported Basic256Sha256 modes;
- username authentication against a real client;
- writable-node behavior from a real client;
- stop/restart/member-removal verification while unrelated shared members remain subscribed.

No GitHub Actions or GitHub-hosted CI is used for this validation.

## REST API simulation

REST API simulation is implemented as a first-class target on the shared Industrial FastAPI host.

Each API target owns one public route under `/sim-api` and supports:

- GET, POST, PUT, PATCH, DELETE, HEAD and OPTIONS;
- arbitrary route paths and named path parameters;
- query and request-body values available to response templates;
- exact required request headers and declarative required path/query/body values;
- response headers with request/simulation template values;
- fixed response delay plus optional jitter;
- configurable success/no-data/not-found/request-rejection status codes;
- current values, canonical frame, flat record, retained history or custom JSON response modes;
- JSON, text/XML/custom-text and explicitly empty success bodies;
- configurable default/custom JSON/custom text/empty error bodies;
- field selection, context/system-field inclusion and response envelopes;
- typed template references to values/context/path/query/body/frame metadata plus error status/message;
- request-driven retained-history lookup without moving the Simulation cursor;
- bounded retained history with offset/limit paging and oldest/newest ordering;
- request count, status-class counters, last status, last request time and latency metrics.

See [API_SIMULATION.md](API_SIMULATION.md).

Requests do not advance a source. API, OPC UA, MQTT, SQL and OData attached to one Simulation Instance therefore observe one shared simulated timeline.

The API simulator intentionally does not include a built-in tester, validator workspace, generic mock-project subsystem or embedded scripting language.

## Other implemented targets

### MQTT

Reuses the existing `MqttTagPublisher`. Each target owns its own publisher/client configuration while several targets may share one broker.

### HTTP Stream

The shared Industrial FastAPI host exposes point-in-time snapshot plus NDJSON, SSE and WebSocket views under `/api/v2/simulations/{simulation_id}/targets/{target_id}`.

This remains distinct from REST API simulation: HTTP Stream exposes canonical frame transport; REST API simulation models request/response contracts.

### SQL Server

SQL Server is a real batched target. Portal and simulations share one Industrial-owned System.Data/PowerShell execution path rather than duplicating SQL process code.

### OData

OData targets expose service document, `$metadata`, entity set data, `$top`, `$skip`, `$select` and simple equality `$filter` over bounded retained canonical rows.

### Memory/internal

A small in-process target remains for tests and diagnostics only.

## Target isolation and backpressure

Each enabled target has an independent bounded queue and worker.

Configurable behavior:

- queue size;
- `block`, `drop_oldest`, `drop_newest` overflow;
- `continue`, `retry`, `stop_simulation` failure policy;
- retry delay.

Runtime target status includes:

- queue depth;
- emitted/published frames;
- dropped frames;
- retry count;
- last successful delivery time;
- last publish latency;
- last error.

One unhealthy target therefore does not inherently stop healthy siblings.

## Lifecycle and timing

Implemented per-simulation controls:

- start;
- pause;
- resume;
- stop;
- restart;
- reset cursor;
- seek while paused.

Clock modes:

- fixed rate;
- source timestamps with speed multiplier and maximum delay.

Loop modes:

- once;
- loop forever;
- hold last;
- ping-pong.

`hold_last` keeps targets/interfaces alive after a finite source is exhausted without continuously re-emitting duplicate copies of the final frame.

Cursor changes drain target queues first and use a source-generation guard so a frame read before a seek cannot leak after resume.

## Persistence

Simulation Definitions and Worlds are persisted to `configs/unified_simulations.json` with atomic replacement.

Persisted definitions load as configured runtime objects; tasks are not blindly resurrected from stale process state.

The Portal workspace separately remembers navigation/editor state and unsaved work. Backend state remains authoritative whenever the UI reconnects.

## Portal/UI

The simulation-centric workspace is served at the Portal root. The old UI remains temporarily under `/legacy` during migration.

Implemented workspace behavior includes:

- create/edit/save/duplicate/delete simulations;
- start/pause/resume/stop/restart;
- reset/seek cursor controls;
- source configuration and source preview;
- large signal-mapping editor;
- detailed shared/dedicated OPC UA configuration;
- REST API target configuration;
- MQTT, HTTP Stream, SQL Server and OData target configuration;
- target/runtime health and current values;
- remembered navigation, selected simulation, filters, tabs and scroll positions;
- recovery of genuinely unsaved local work without allowing stale browser state to override backend truth.

## Portal/backend cleanup completed

- Portal control server migrated to FastAPI;
- API Studio retired and its code/dependencies/port contract removed;
- obsolete Portal patcher/backups removed;
- fake retry/cleanup/convert and status-only job control routes removed;
- legacy async `RLock`-across-`await` misuse corrected;
- release packaging converted to an explicit runtime allowlist;
- SQL execution moved out of Portal ownership into the Industrial runtime.

## Validation policy

GitHub Actions and GitHub-hosted CI are not used for this repository.

Validation is local/manual or through a separately selected non-GitHub mechanism. Do not add `.github/workflows/*`.

## Compatibility bridge still present

Legacy replay/workload code still exists while callers are migrated. Do not add new behavior to `ProtocolMode = opcua|mqtt|both`, `MultiSimulatorEngine`, `DualProtocolAdapter`, or other protocol-combination paths.

The migration strategy is caller migration followed by deletion, not parallel feature development in both architectures.

## Current known work

The authoritative prioritized list is [PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md). Immediate remaining work is intentionally narrower than the earlier alpha list:

1. complete local Windows end-to-end validation of concurrent shared/dedicated OPC UA with a real client, including security/auth/writes;
2. complete rendered UI/UX QA and refinement of the simulation/target workspace;
3. stress target isolation/backpressure and large-source behavior locally;
4. migrate remaining legacy replay/workload callers to `SimulationManager` and delete protocol-combination layers;
5. reduce or eliminate the Python 3.14/asyncua compatibility patch once real-runtime validation identifies what the bundled asyncua version actually still requires;
6. add additional protocols/sources only for concrete integration needs.

Every migration should reduce duplicate code or concepts. New abstractions must earn their existence through more than one real implementation or a clear reduction in complexity.
