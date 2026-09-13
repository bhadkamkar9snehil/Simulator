# Simulator — Current State, Ponytail and Complexity Baseline

**Baseline repository:** `bhadkamkar9snehil/Simulator`  
**Baseline main commit:** `8fdab87fc6d48d4e906af860618d76358c4bd189`  
**Baseline date:** 2026-09-13  
**Companion specification:** [Unified Multi-Interface Simulator Requirements](UNIFIED_SIMULATOR_REQUIREMENTS.md)

> **Repository policy:** GitHub Actions is not used for this project. Quality/test/complexity validation is local/manual or through an explicitly selected non-GitHub mechanism.

---

## 1. Purpose

This document records the current implementation condition and the technical-debt findings that motivated the target architecture in `UNIFIED_SIMULATOR_REQUIREMENTS.md`.

It is intentionally separate from the permanent requirements specification:

- the requirements document describes **what Simulator must become**;
- this document describes **what exists today, what should be deleted/simplified, and where complexity is concentrated**.

This baseline should be updated or superseded after major cleanup milestones.

---

## 2. Overall Assessment

At the baseline commit, Simulator is feature-rich and already contains many of the capabilities needed for the future product, but the repository is not yet architecturally unified.

High-level condition:

- functional simulation capabilities: good;
- Windows/offline deployment architecture: good;
- domain-generator coverage: good;
- automated tests present: good;
- local validation enforcement: not yet standardized;
- documentation consistency: poor;
- release hygiene: poor;
- protocol/runtime ownership boundaries: mixed;
- multi-simulation architecture: partial and protocol-shaped;
- cyclomatic complexity: concentrated in a limited number of hotspots rather than uniformly high;
- dead/legacy code: significant enough that deletion should precede major refactoring.

The correct response is **not a rewrite**. The preferred sequence is:

1. delete obsolete/legacy surface area;
2. establish repeatable local validation and release hygiene;
3. introduce the canonical simulation/source/target model;
4. migrate working capabilities incrementally.

---

## 3. Current Active Architecture

The current supported runtime is approximately:

```text
RUN_SIMULATOR.bat
   ↓
suite_runtime.py
   ├─ bundled Python runtime / venv bootstrap
   ├─ internal MQTT broker
   ├─ Industrial FastAPI service
   └─ Portal HTTP service
```

Current primary ports/defaults:

```text
Industrial HTTP     8000
Portal              8001
OPC UA              4840
MQTT broker         1883
API Studio          5050 (legacy/disabled)
```

The current launcher explicitly does not start API Studio, but API Studio configuration remains represented in port maps, environment variables, status payloads, and repository code.

This is one of the first cleanup targets.

---

## 4. Current Feature Surface

The baseline implementation includes or advertises:

- 13 industrial domain generators;
- CSV/XLSX ingestion;
- CSV/Parquet/lakehouse-style generation paths;
- dataset registration/preview/scan;
- replay;
- OPC UA output;
- MQTT output;
- an internal MQTT broker;
- HTTP snapshot/NDJSON/SSE/WebSocket support;
- concurrent job/workload concepts;
- SAP PP source simulation;
- LIMS source simulation;
- SQL Server projection via the Portal path;
- synthetic video generation;
- job persistence/status;
- structured logs;
- offline Windows deployment using a bundled Python runtime and wheelhouse.

These should be viewed as capabilities to consolidate into the unified Simulator, not as reasons to preserve the current subsystem boundaries.

---

## 5. Cyclomatic Complexity Baseline

The following is a source-review baseline using conventional McCabe/Radon-style reasoning. Exact values should be generated with local complexity tooling when available.

Suggested interpretation:

- **A: 1–5** — simple;
- **B: 6–10** — manageable;
- **C: 11–20** — review/decompose when modified;
- **D: 21–30** — high complexity;
- **E: 31–40** — very high;
- **F: 41+** — critical.

### 5.1 Primary Hotspots

| Rank | Function / Area | Estimated CC | Grade | Observation |
|---:|---|---:|:---:|---|
| 1 | `opcua_server.py` Python-3.14/asyncua type-repair logic | 45–55 | F | Deep type-repair and monkey-patching logic over third-party serializer internals |
| 2 | `petroleum_pipeline.py::generate()` | 22–28 | D | Source parameters, hydraulic state, scenarios, faults, alarms and row construction combined |
| 3 | `eaf_melting.py::generate()` | 21–25 | D | Phase state machine, faults, dynamics and alarm selection combined |
| 4 | `polyester_fiber.py::_scaled_nominal()` | ~22 | D | Large substring/rule branch ladder hidden inside a small helper |
| 5 | `gas_pipeline.py::generate()` | 17–21 | C/D | Scenario, compressor, flow, pressure and hydrate state combined |
| 6 | `portal_app.py::Handler.do_POST()` | 18–20 | C | Hand-written HTTP route dispatcher |
| 7 | `replay_jobs.py::_run_replay_job()` | 17–20 | C | Pause/resume/stop/completion/failure state machine embedded in one loop |
| 8 | `polyester_fiber.py::iter_rows()` | 16–18 | C | Scenario dispatch plus process/derived-value construction |
| 9 | `workloads.py::start_workload_run()` | 15–18 | C | Multi-job startup and rollback/type dispatch |
| 10 | `source_simulators/jobs.py` worker loop | 14–17 | C | Pause/stop/cycle/query/status/persistence combined |
| 11 | `SimulatorEngine.configure()` | 13–16 | C | Source resolution, validation, cursor/tag setup and publisher configuration |
| 12 | `MultiSimulatorEngine.configure_files()` | 12–15 | C | File-plan normalization mixed with protocol/runtime orchestration |
| 13 | `workloads.py::_control_child_job()` | 12–14 | C | Job-type × action dispatch matrix |
| 14 | `suite_runtime.py::wheel_is_compatible()` | 12–14 | C | Hand-written wheel compatibility evaluation |
| 15 | `SimulatorEngine._loop()` | 12–14 | C | Replay timing, cursor behavior and lifecycle/error handling |
| 16 | `gnfc_chemical_process.py::generate()` | 14–17 | C | Scenario/process effects concentrated in one loop |
| 17 | power/rotary/blast-furnace generators | ~8–12 | B/C | Manageable individually but repeat the monolithic-generator pattern |
| 18 | MQTT broker packet handlers | ~7–10 each | B | Individual methods manageable; protocol implementation itself is maintenance surface |

### 5.2 Complexity Interpretation

The repository is **not generally spaghetti code**.

Complexity is concentrated in:

- protocol compatibility machinery;
- simulation loops;
- lifecycle/state-machine loops;
- manual dispatch code;
- protocol-combination orchestration.

Much of the data/model/registry layer is already straightforward and should not be rewritten without cause.

---

## 6. Highest-Risk Complexity Hotspot: OPC UA Compatibility Layer

`industrial_simulator/app/opcua_server.py` contains a substantial Python 3.14 compatibility repair for asyncua-generated dataclass annotations and serializer/deserializer behavior.

The code performs activities such as:

- traversing generated dataclasses;
- inspecting `Field`, `property`, unions and default factories;
- attempting type reconstruction through several heuristics;
- replacing field types;
- clearing serializer caches;
- monkey-patching asyncua serializer/deserializer helpers.

This is structurally unlike normal Simulator domain code and is fragile because it depends on third-party internal behavior.

Requirement implication:

- keep the workaround isolated;
- test supported Python/asyncua combinations explicitly;
- remove the workaround when a stable runtime/dependency combination makes it unnecessary;
- do not allow this compatibility code to spread into core simulation logic.

---

## 7. Ponytail Audit — Delete / Shrink / Native / YAGNI

The cleanup principle is **delete before refactor**.

### 7.1 P0 — Delete or Retire

#### P0-01 — Legacy API Studio

`api_studio/` is a substantial Flask-based application, but the supported launcher explicitly marks API Studio legacy and does not start it.

Action:

- remove it from active product code or archive it outside the production tree;
- if retained for historical/reference purposes, exclude it from release packaging and clearly label it non-runtime.

#### P0-02 — API Studio Port Plumbing

Even though API Studio is disabled, the application still carries:

- `api_studio_port` in default ports;
- environment-variable mappings;
- portal configuration values;
- status payload fields;
- legacy URL replacement logic.

Action:

- remove this fifth-port concept when API Studio retirement is confirmed.

#### P0-03 — Obsolete Portal UI Patcher

`portal/patch_portal_ui.py` describes patching embedded UI inside `portal_app.py` and intentionally creates `portal_app.py.bak`.

The active Portal now serves `portal/simulator_ui.html` as a separate template, making the patcher obsolete.

Action:

- delete the patcher;
- delete `portal_app.py.bak`;
- ensure backups are excluded by repository/release policy.

#### P0-04 — Scaffolding APIs Presented as Behavior

Examples include job retry/cleanup or dataset conversion paths that currently only update status or immediately report unimplemented behavior.

Action:

- remove or hide them until real behavior exists;
- avoid presenting scaffolding as an implemented product capability.

---

## 8. P1 — High-Value Simplifications

### P1-01 — Replace Manual Portal Routing

`portal_app.py` uses `BaseHTTPRequestHandler` and manually implements:

- request parsing;
- response formatting;
- CORS;
- GET dispatch;
- POST dispatch;
- error handling.

FastAPI is already a core dependency in the same product.

Action:

- migrate the tiny Portal control API to FastAPI unless a documented measurable reason exists not to;
- keep the Portal UI itself independent of this server choice.

Expected benefit:

- eliminates one of the major C-grade branch ladders;
- reduces hand-written web plumbing;
- allows shared exception and validation behavior.

### P1-02 — FastAPI Endpoint Boilerplate

`industrial_simulator/app/api.py` repeats many endpoint-level blocks equivalent to:

```python
try:
    ...
except Exception as exc:
    raise error_response(exc)
```

Action:

- use application/global exception handlers;
- leave route functions focused on request-to-domain translation.

### P1-03 — Duplicate Worker Control

Replay jobs and source-simulator jobs each contain versions of:

- global control dictionaries;
- pause events;
- stop events;
- stale-worker checks;
- background lifecycle bookkeeping.

Action:

- extract a small common `JobControl`/worker-control primitive;
- do not introduce a large general workflow framework.

### P1-04 — Duplicate Generator Execution

Small-file generation and enterprise/background generation both perform generator lookup, scenario validation, `iter_rows` detection and fallback.

Action:

- create one shared generator-row execution function.

### P1-05 — Dead Policy Hook

`is_default_disabled_column()` currently always returns `False`.

Action:

- remove the abstraction until a real disable policy exists;
- use `enabled=True` directly in the mapping creation path.

### P1-06 — Silent Protocol Mock Fallback

Core protocol modules can fall back to mock behavior if dependencies fail to import.

Problem:

- production can appear to be running even when the advertised protocol is not actually available.

Action:

- production runtime should fail clearly for missing required protocol dependencies;
- test fakes/mocks should be explicitly injected or selected.

### P1-07 — Release Packaging by Exclusion

The release builder recursively considers much of the repository and then excludes selected paths/suffixes.

This makes it easy for restored archives, references, backups and documentation dumps to enter release ZIPs.

Action:

- invert the packaging model;
- use an explicit runtime allowlist.

---

## 9. P2 — Further Simplification Opportunities

### P2-01 — Duplicated `get_base_dir()`

Base-directory resolution appears in multiple modules.

Action:

- centralize runtime-path resolution if all branches remain necessary.

### P2-02 — `sys.frozen` Branches

Several modules contain frozen/PyInstaller-style path behavior although the current shipping approach is a bundled Python runtime plus source/wheels.

Action:

- retain only if a frozen distribution is an actual supported product requirement.

### P2-03 — Frontend Job Action Dispatch

The frontend repeats type/state-specific branching for replay, source simulation and generic jobs.

Action:

- make capabilities/action metadata data-driven where practical.

### P2-04 — Generator Fault Logic

Many generators embed scenario/fault logic directly inside a long per-sample loop.

Action:

- separate plain-function stages:

```text
validation
→ initial state
→ phase/state
→ scenario effects
→ integration
→ derived metrics
→ row/frame construction
```

Do not create class-per-fault frameworks.

### P2-05 — Polyester Nominal Scaling

`_scaled_nominal()` contains a branch-heavy series of substring-based scaling rules.

Action:

- convert repetitive rule selection into an ordered data/rule table or smaller predicates.

### P2-06 — Parallel SAP Architectures

The repository has both:

- integrated `source_simulators/sap_pp.py` behavior;
- standalone `sap_api_simulator/` behavior.

They overlap but are not identical.

Action:

- integrate useful behavior into the unified interface architecture;
- or explicitly classify the standalone simulator as reference/development tooling.

---

## 10. What Should Not Be Simplified Away

Ponytail cleanup must not damage useful architecture.

### 10.1 Offline Runtime Verification

The current launcher verifies:

- bundled Python runtime presence/version/platform;
- wheelhouse manifest;
- wheel compatibility;
- wheel hashes and sizes;
- environment fingerprint;
- service readiness.

These checks support the real deployment model and should generally remain.

### 10.2 Domain Generator Abstraction

The repository contains 13 actual domain-generator implementations.

Therefore a common `DomainGenerator` abstraction is justified by real multiplicity.

### 10.3 Source Simulator Abstraction

Multiple source simulator types exist, so a small common source abstraction is also justified.

### 10.4 Structured Logging

Structured logging, rotation, operation IDs and query/filter support correspond to actual operational needs and should remain.

### 10.5 Do Not Rewrite UI Merely for CC

Moving the current Portal to a new frontend framework purely to reduce cyclomatic complexity would not be a good cleanup trade.

UI framework decisions should be driven by product/UI requirements. The immediate cleanup is to simplify the backend control server and reduce duplicated dispatch/state logic.

---

## 11. Core Architectural Smell: Global Protocol Combination State

The current `MultiSimulatorEngine` carries concepts such as:

- `protocol`;
- OPC UA file groups;
- MQTT file groups;
- `both` mode;
- protocol-specific start/stop/configuration paths.

This can work for two protocols but cannot scale cleanly to:

- OPC UA;
- MQTT;
- SQL;
- HTTP;
- OData;
- Modbus;
- Kafka;
- other future interfaces.

This is the strongest reason for the target model documented in `UNIFIED_SIMULATOR_REQUIREMENTS.md`:

```text
SimulationInstance
  └─ targets[]
```

There should eventually be no combinatorial protocol mode.

---

## 12. Ownership Smell: Simulation vs Shared Protocol Host

Current adapter behavior already shows ownership tension:

- per-job/per-channel adapters intentionally avoid stopping shared services;
- the parent multi-simulator layer owns final service shutdown;
- simulations and network listeners are therefore not naturally one-to-one.

This is evidence that the correct future separation is:

```text
SimulationManager
```

and separately:

```text
InterfaceHostManager
```

A simulation owns simulated state/time. A host owns the listener/server/broker.

---

## 13. Generator Complexity Pattern

The generator family is not uniformly bad; rather, many modules repeat one structural pattern:

```text
large generate()/iter_rows()
  ├─ parameter extraction
  ├─ state initialization
  ├─ phase/scenario branches
  ├─ physical/process calculations
  ├─ alarms
  └─ row serialization
```

### Good Direction Already Present

`polyester_fiber.py` already extracts scenario-specific functions such as pressure drop, drive trip, filter fouling and vacuum loss.

This demonstrates the preferred refactoring style: plain functions around real process concepts rather than deep framework abstraction.

---

## 14. Concurrency and Correctness Concerns

These are not pure Ponytail findings but were surfaced during the architecture/complexity review.

### 14.1 Thread Locks Across `await`

Some protocol/multi-simulator paths use `threading.RLock` around operations that include `await`.

A thread lock does not provide the same coroutine scheduling guarantees as `asyncio.Lock` on an event loop.

Action:

- use async synchronization for async critical sections;
- restrict thread locks to short synchronous state mutations where needed.

### 14.2 Broad Exception Swallowing

Several persistence/config/listing paths catch broad exceptions and silently continue, clear state, or return defaults.

Risk:

- corruption or configuration errors can become invisible.

Action:

- log and expose meaningful diagnostics;
- avoid silently erasing state due to parse failures.

### 14.3 Core Dependency Fallback

As noted above, optional import behavior can make missing protocol dependencies look like a running mock service.

Action:

- fail explicitly in production mode.

---

## 15. Security Baseline

At the baseline commit:

- the Industrial FastAPI service is launched on `0.0.0.0`;
- the Portal server binds to `0.0.0.0`;
- Portal responses use wildcard CORS;
- management routes include start/stop/configuration and SQL-related operations;
- no authentication layer was observed in the reviewed Portal control server.

This is acceptable only in a controlled/local environment with appropriate host/network firewalling.

Target direction:

- management/control plane local by default;
- protocol/data-plane listeners explicitly configurable for LAN exposure;
- remote management requires explicit authentication/authorization;
- bind addresses should be configuration, not accidental behavior.

---

## 16. Documentation Baseline

At the baseline commit, internal architecture documentation is stale relative to the restored source.

Examples observed during review include documentation that still describes:

- API Studio as an active service;
- an older Portal UI file as active;
- backup files as deleted even though one exists again;
- an old development branch as the active development branch.

Action:

- rewrite architecture/agent documentation after the requirements baseline is accepted;
- ensure future docs distinguish target architecture from currently implemented state.

---

## 17. Repository and Release Hygiene Baseline

The restored main commit includes development/reference assets alongside runtime source, including examples such as:

- reference simulator trees;
- old/new domain reference material;
- large knowledge-base documentation;
- archived UI ZIP content;
- backup files;
- bundled runtime/wheels.

Bundled runtime/wheels may be intentionally part of distribution, but unrelated reference/development assets should not automatically enter releases.

The release builder should therefore move to an explicit runtime allowlist.

---

## 18. Dependency Rationalization Candidates

If API Studio is retired and repository-wide import checks confirm no other active usage, candidate dependency removals include the Flask stack used by that legacy app.

Dependency removal MUST be verified through local import scans and tests rather than assumed.

Similarly, optional-dependency fallback branches should be reevaluated when dependencies are already mandatory in the bundled runtime.

---

## 19. Recommended Cleanup Sequence

### Phase A — Establish Baseline

- keep `UNIFIED_SIMULATOR_REQUIREMENTS.md` as the product north star;
- keep this document as the current implementation baseline;
- update top-level documentation links.

### Phase B — Safe Deletion

- legacy API Studio;
- API Studio port plumbing;
- obsolete Portal UI patcher and backup;
- clearly unimplemented/scaffolding public API behavior;
- release inclusion of reference/development artifacts.

### Phase C — Local Quality Checks

- pytest;
- compile/syntax validation;
- Radon/Xenon or equivalent local complexity reporting;
- release-build validation;
- reusable local commands/scripts for repeatability;
- no GitHub Actions workflows.

### Phase D — Small Simplifications

- common exception handling;
- common job-control primitive;
- shared generator execution;
- removal of dead policy hooks;
- explicit dependency failure behavior.

### Phase E — Architectural Migration

Follow the migration phases in `UNIFIED_SIMULATOR_REQUIREMENTS.md`:

- canonical frames;
- first-class `SimulationInstance`;
- source/target contracts;
- `SimulationManager`;
- `InterfaceHostManager`;
- removal of global protocol-combination state;
- multi-simulation target isolation;
- optional Worlds.

---

## 20. Proposed Local Complexity Check

When local automated metrics are available:

```text
A/B   accepted normally
C     allowed but reviewed
D+    rejected for new/modified code unless explicitly justified
```

Existing D/F functions should be tracked as known debt rather than forcing an immediate rewrite.

A useful local report should show both:

- absolute current complexity;
- complexity introduced/changed by the current work.

This allows gradual improvement without blocking unrelated work on inherited debt.

---

## 21. Definition of “Improved”

The cleanup/refactor should be considered successful when:

- repository/runtime surface is smaller despite adding capability;
- one simulation can target many interfaces without protocol-combination branches;
- many simulations can run concurrently without shared global cursor/protocol state;
- shared listeners have explicit ownership separate from simulations;
- target failures are isolated;
- generators are easier to modify without framework explosion;
- exact CC metrics can be generated locally and repeatably;
- releases contain only intended runtime assets;
- documentation accurately states both current implementation and future direction;
- no GitHub Actions workflow is present.

---

## 22. Relationship to the Requirements Specification

Where this baseline and `UNIFIED_SIMULATOR_REQUIREMENTS.md` differ, interpret them as follows:

- **Requirements document:** target behavior and architecture to preserve.
- **This baseline:** current debt and migration observations that may disappear once addressed.

The requirements document should remain durable. This baseline should become progressively obsolete as the codebase converges on the target architecture.
