# Simulator Product Backlog

**Purpose:** durable product/engineering backlog for the unified Simulator.  
**Primary objective:** reliably simulate multiple independent sources to multiple independently configured targets, with OPC UA as the primary end-to-end protocol path and REST API simulation as the next major target.  
**Architecture rule:** Ponytail principles always — delete before adding, reuse existing code, prefer direct contracts, avoid speculative frameworks, and keep cyclomatic/architectural complexity low.

This backlog describes missing or incomplete product behavior. It is not a request to implement every conceivable protocol feature.

## Priority order

### P0 — finish and prove OPC UA

OPC UA is the primary acceptance path for the unified runtime.

Required:

- multiple concurrent Simulation Instances on one shared OPC UA listener;
- multiple dedicated OPC UA listeners at the same time;
- shared and dedicated targets coexisting without socket or NodeId collisions;
- stopping/restarting one shared member must not restart or disturb unrelated members;
- exact client-visible configured NodeIds on dedicated endpoints;
- deterministic collision-safe NodeIds on shared endpoints, with explicit prefix control where useful;
- configurable bind host, advertised host, port, endpoint path, namespace URI and root folder;
- OPC UA security-policy configuration using the existing asyncua server rather than a second server implementation;
- anonymous and username/password identity modes suitable for local integration simulation;
- explicit writable-tag semantics;
- useful OPC UA datatype fidelity for common industrial scalar types;
- live endpoint/security/tag/runtime diagnostics in the UI;
- local Windows end-to-end validation with a real OPC UA client.

Acceptance criteria:

1. Two or more simulations can publish different values concurrently through one listener and are independently addressable.
2. Removing one shared target leaves the listener and remaining simulations online.
3. Dedicated targets bind independently and fail clearly before bind on port conflicts.
4. Security and identity settings shown in the UI match the endpoints clients actually discover.
5. Client-visible NodeIds and writable flags match the saved Simulation Definition.
6. Common scalar values retain their configured OPC UA type rather than relying only on Python inference.
7. Backend/interface status is authoritative and the UI never invents stale listener state.
8. The complete path is verified locally on Windows without GitHub Actions or GitHub-hosted CI.

### P1 — simulation workspace UI/UX

The current workspace is functional but requires a rendered product-quality pass.

Required:

- stronger visual distinction between persisted configuration, live backend state and unsaved local edits;
- protocol-specific settings visually dominant over common queue/failure controls;
- progressive disclosure for advanced target settings rather than one uniformly dense form;
- better mapping-table usability for hundreds/thousands of signals;
- robust long endpoint/NodeId/namespace handling;
- clearer degraded/error state at the affected target;
- backend connection-loss/reconnection state;
- common Windows desktop-resolution QA;
- keyboard/focus/accessibility cleanup;
- destructive-action confirmation and consistent empty/loading/error states.

Session behavior is already constrained by one rule: **backend is truth; browser session state is convenience only.** Existing Simulation Definitions and runtime state must always be refreshed from the backend.

### P1 — REST API simulator completion

Implemented baseline already includes configurable method/path, request headers/values, request-driven retained-history lookup, JSON/text/empty response bodies, custom success/error bodies, response headers, latency/jitter, history paging and runtime request metrics.

Remaining only where useful to real integrations:

- `application/x-www-form-urlencoded` request-body parsing;
- repeated query-key handling;
- cookies if a real target integration requires them;
- multipart/form-data or binary payloads only for a concrete integration;
- dedicated HTTP listener/port only when shared-host isolation is insufficient.

Deliberately **not** planned:

- built-in API tester;
- validator workspace;
- generic mock-project subsystem;
- embedded scripting/expression language.

### P2 — source coverage

Potential additions, in priority order only when required:

- SQL source;
- HTTP/API source;
- recorded OPC UA replay source;
- recorded MQTT replay source.

Existing Parquet/file/dataset/generator/SAP/LIMS sources need large-file and concurrency validation, especially concurrent use of the same source-simulator connector.

### P2 — other targets

- MQTT: expose remaining useful QoS/retain/client/auth/TLS controls in the UI and validate concurrency.
- SQL Server: throughput/schema/table behavior validation.
- OData: remain deliberately small; add richer semantics only for concrete consumers.
- HTTP Stream: keep as canonical-frame transport, distinct from REST API simulation.
- Do not implement Modbus TCP, Kafka or another protocol merely to increase protocol count.

### P2 — Worlds / coordinated simulations

Backend World definitions exist. Remaining product work:

- Worlds workspace/UI;
- coordinated start/stop UX;
- define whether tighter start synchronization is required by a real scenario;
- preserve independent Simulation Instance ownership underneath coordination.

### P2 — runtime restart semantics

Simulation Definitions persist. Runtime tasks are intentionally not resurrected from stale process memory.

Still to decide/implement as an explicit product policy:

- whether saved `autostart` definitions should resume automatically after the entire backend process starts;
- whether paused/running execution position should ever be persisted across a full process shutdown.

Do not infer a stale running state from browser session storage.

### P2 — observability

Keep diagnostics operational rather than turning Simulator into a monitoring product.

Useful compact metrics:

- emitted frame rate;
- source position/rate;
- target publish rate;
- queue depth/pressure;
- drops/retries;
- last successful target delivery;
- target publish latency;
- REST request status/latency counters;
- OPC UA listener/security/tag/member state.

### P3 — legacy deletion / complexity reduction

Remaining compatibility code must be migrated caller-by-caller and then deleted:

- legacy `MultiSimulatorEngine`;
- `ProtocolMode = opcua|mqtt|both` orchestration;
- legacy replay/workload runners that duplicate `SimulationManager` behavior;
- duplicate job/background-worker control paths;
- old Portal under `/legacy` once all supported operations have replacements;
- oversized `suite_runtime.py` concerns after supported launcher behavior is separated cleanly.

Known complexity hotspots should be reduced when touched, especially:

- Python 3.14 / asyncua compatibility patch;
- large legacy generator functions;
- growing frontend renderer modules.

Do not create a framework merely to lower line count. Split only around real ownership boundaries.

## Validation policy

GitHub Actions and GitHub-hosted CI are prohibited for this repository.

Validation is local/manual or through a separately selected non-GitHub mechanism. Do not add `.github/workflows/*`.

## Definition of product-ready primary path

The unified Simulator is not product-ready until this scenario is routine:

```text
Source A ─→ Simulation A ─┬─→ shared OPC UA
                          ├─→ REST API
                          └─→ MQTT

Source B ─→ Simulation B ─┬─→ same shared OPC UA listener
                          └─→ SQL Server

Source C ─→ Simulation C ───→ dedicated OPC UA listener
```

Each simulation must have its own source, clock, cursor, mapping, lifecycle and target queues. Any single target or simulation may stop/fail/restart without silently changing unrelated runtime state unless the saved failure policy explicitly requests that behavior.
