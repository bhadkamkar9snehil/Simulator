# Simulator — Engineering Knowledge Base

This file is guidance for humans and coding agents working in this repository. It describes the current architecture and the rules for evolving it. It must be updated when those facts change.

## Authoritative product direction

Read these before architectural work:

1. `docs/UNIFIED_SIMULATOR_REQUIREMENTS.md` — normative product and architecture requirements.
2. `docs/CURRENT_STATE_AND_COMPLEXITY_BASELINE.md` — migration/technical-debt baseline; this document is intentionally temporary and should shrink as debt is removed.
3. `docs/UNIFIED_RUNTIME_IMPLEMENTATION.md` — current implementation status for the new runtime.

The product direction is one unified Simulator capable of running many independent or coordinated Simulation Instances concurrently. Each instance owns its source, clock, cursor, mapping, lifecycle, and target bindings. Sources and targets must not be coupled to protocol combinations such as `opcua`, `mqtt`, or `both`.

### Primary product focus

The primary product objective is **end-to-end OPC UA simulation of many concurrent simulations serving many targets**.

The most important user workflow is:

```text
Source / Generator / Dataset
        ↓
Simulation Instance
        ↓
Per-simulation timing, replay, scenario and mapping
        ↓
OPC UA target (shared or dedicated)
        ↓
Optional additional targets: MQTT / HTTP / OData / SQL / others
```

Requirements implied by this priority:

- many simulations must run concurrently without sharing cursor, clock, lifecycle, source state, or target state;
- OPC UA must support multiple simulations through shared hosts and dedicated endpoints;
- every simulation must be independently configurable from the UI;
- secondary targets must attach to the same Simulation Definition rather than create parallel workflows;
- the UI is a first-class part of the product, not an administrative afterthought;
- advanced OPC UA configuration must remain accessible without making simple configuration difficult;
- runtime architecture and UI object model must use the same source → simulation → mapping → targets model.

Do not optimize secondary features at the expense of the multi-simulation OPC UA path or the simulation-centric UI.

## Current supported launcher and services

- `RUN_SIMULATOR.bat` is the supported entry point.
- `suite_runtime.py` owns Windows runtime/venv validation, service startup, ports, and health checks.
- Industrial FastAPI service: default port 8000.
- Portal UI/control service: default port 8001.
- OPC UA data plane: default port 4840.
- Local MQTT broker: default port 1883.
- API Studio has been retired from the active tree and is not started or packaged.
- Active Portal UI file: `portal/simulator_ui.html`.
- Active Portal server: `portal/portal_app.py`, now FastAPI-based.

## Unified runtime

New architecture lives under `industrial_simulator/app/simulation/`:

- `models.py` — canonical simulation/source/target/frame/world models.
- `contracts.py` — deliberately small source/target contracts.
- `sources.py` — adapters over existing CSV/XLSX/Parquet/dataset managers, domain generators, SAP/LIMS source simulators, and small inline data.
- `mapping.py` — pure protocol-neutral schema/frame transformations.
- `interfaces/` — real target implementations split by interface responsibility.
- `targets.py` — compatibility facade over the interface modules; do not put new protocol implementation here.
- `runtime.py` — `SimulationInstance`, target queues, independent clocks, `SimulationManager`, Worlds, persistence, and interface-host ownership.
- `api.py` — `/api/v2` control/data API.

Legacy replay APIs and `SimulatorEngine` remain during migration for compatibility. Do not build new features into the legacy protocol-combination model unless needed to preserve existing behavior. New functionality should use the unified runtime.

## UI rules

The UI must be simulation-centric and visually/interaction-wise production quality.

The primary workspace must make it easy to:

- see all running/stopped/degraded simulations;
- create a simulation;
- duplicate a simulation;
- start/pause/resume/stop one or many simulations;
- inspect source progress and simulated time;
- fine-tune source, timing, mappings, scenarios and targets per simulation;
- configure OPC UA shared/dedicated hosting, port/path, namespace, root folder and NodeId mapping;
- inspect every target's independent state, endpoint, queue depth, dropped frames, publish count and errors;
- add secondary targets without leaving the simulation workflow;
- distinguish simple settings from advanced settings without hiding advanced capability.

Do not create separate protocol-centric pages that force users to configure the same simulation repeatedly. Protocol-specific controls belong inside the target editor for that Simulation Definition.

Prefer progressive disclosure over dense forms. Keep persistent identity/name/source/state visible while editing detailed settings. Use large, legible typography and stable layouts; missing values must not shift unrelated controls.

## Architecture rules

- Simulation lifecycle and interface-host lifecycle are different. Stopping one simulation must not shut down a shared listener used by another simulation.
- A Simulation Instance may have any number of target bindings. Never add `both`, `opcua+sql`, or other protocol-combination branches to the new runtime.
- Canonical frames must remain protocol-neutral. MQTT topics/payloads, OPC UA node layout, SQL schemas, OData entities, etc. belong in target adapters.
- Source adapters own ingestion semantics. Targets do not know whether values came from CSV, a generator, SAP/LIMS simulation, or another source.
- Shared hosts and dedicated hosts are explicit target configuration, not hidden consequences of source/protocol choice.
- Slow or failing targets must not stall unrelated targets unless the configured overflow/failure policy explicitly requests blocking/stopping.
- Worlds coordinate related Simulation Instances; simple simulations must never require a World.
- Reuse existing generator, data-manager, protocol-server, publisher, logging, and runtime-validation code when it is sound. Wrap before rewriting.

## Ponytail rules — always apply

Use this ladder for every addition/refactor:

1. Does this code need to exist?
2. Can existing repository code already do it?
3. Can the Python standard library do it?
4. Can an already-installed dependency do it?
5. Is the abstraction backed by more than one real implementation/use case?
6. Can the same behavior be expressed with fewer moving parts?

Specific rules:

- Delete dead/legacy paths before designing around them.
- Do not create speculative plugin frameworks, factories, base classes, or indirection for one implementation.
- Prefer plain functions/data composition over strategy-class hierarchies.
- Do not expose placeholder APIs that only say “planned” or immediately fail as if they were implemented behavior.
- Avoid compatibility fallbacks for dependencies that the supported bundled runtime guarantees; tests may inject fakes explicitly.
- Do not carry a branch, option, config key, or layer merely because it might be useful later.
- When a repeated mechanism is real (for example many source adapters or many target adapters), keep the shared contract as small as possible.
- UI abstractions must also pass the same test: reusable components only when real repetition exists; avoid component forests and generic form engines.

## Complexity policy

For new or materially modified code:

- A (1–5): preferred.
- B (6–10): normal.
- C (11–20): allowed when the branching is domain/lifecycle logic and the function remains understandable.
- D/E/F (>20): do not introduce; decompose before merge.

Do not game complexity metrics with meaningless helper extraction. Reduce decisions, separate responsibilities, or use data-driven dispatch where it genuinely clarifies behavior.

## Validation policy — no GitHub Actions

**Never use GitHub Actions for this repository.**

- Do not create `.github/workflows/*`.
- Do not add GitHub-hosted CI, workflow runs, CI badges, required Actions checks, or documentation that instructs future work to add them.
- Automated or scripted validation, when useful, must run locally/manual from the repository or through an explicitly chosen non-GitHub mechanism.
- Keep pytest, syntax checks, complexity checks and release validation available as local commands/scripts rather than GitHub workflows.

This is a permanent repository constraint unless the repository owner explicitly reverses it.

## Async/concurrency rules

- Use `asyncio.Lock` for coroutine coordination. Never hold `threading.Lock`/`threading.RLock` across `await`.
- Each Simulation Instance owns its own clock/cursor/state.
- Each target has an independent bounded queue and explicit overflow/failure policy.
- Target failures are isolated by default.
- Shared listener mutation/publishing must be serialized at the host boundary.
- Shutdown must be deterministic and release tasks/listeners cleanly.

## Tests and behavior preservation

- Existing tests are assets; do not delete them to make a refactor pass.
- Add tests for new concurrency/lifecycle behavior.
- Preserve legacy routes until their callers/UI have migrated.
- Prefer compatibility adapters over duplicate implementations.
- A cleanup that changes behavior must be explicit and tested.
- Run tests locally/manual; do not wire them to GitHub Actions.

## Deployment rules

- Windows/offline deployment is a core supported constraint.
- Preserve bundled runtime/wheel integrity validation in `suite_runtime.py` and release building.
- Do not make normal runtime startup depend on internet access.
- Release packaging must contain only runtime-required files; reference material/backups/dev artifacts must stay out.

## External-product boundary

Simulator is a standalone product. It must not contain application-specific knowledge, imports, paths, ports, or configuration for downstream products that consume Simulator. Integration belongs on the consuming side through Simulator's supported interfaces.

## Repository hygiene

- No `.bak` files, editor backups, generated outputs, test caches, unrelated knowledge bases, or obsolete ZIPs in releases.
- Do not hard-code an “active development branch” in documentation.
- Keep target architecture, current implementation, and migration debt clearly distinguished.
- No GitHub Actions workflow files.