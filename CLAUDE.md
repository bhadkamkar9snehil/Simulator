# Simulator — Engineering Knowledge Base

This file is guidance for humans and coding agents working in this repository. It describes the current architecture and the rules for evolving it. It must be updated when those facts change.

## Authoritative product direction

Read these before architectural work:

1. `docs/UNIFIED_SIMULATOR_REQUIREMENTS.md` — normative product and architecture requirements.
2. `docs/CURRENT_STATE_AND_COMPLEXITY_BASELINE.md` — migration/technical-debt baseline; this document is intentionally temporary and should shrink as debt is removed.
3. `docs/UNIFIED_RUNTIME_IMPLEMENTATION.md` — current implementation status for the new runtime.

The product direction is one unified Simulator capable of running many independent or coordinated Simulation Instances concurrently. Each instance owns its source, clock, cursor, mapping, lifecycle, and target bindings. Sources and targets must not be coupled to protocol combinations such as `opcua`, `mqtt`, or `both`.

## Current supported launcher and services

- `RUN_SIMULATOR.bat` is the supported entry point.
- `suite_runtime.py` owns Windows runtime/venv validation, service startup, ports, and health checks.
- Industrial FastAPI service: default port 8000.
- Portal UI/control service: default port 8001.
- OPC UA data plane: default port 4840.
- Local MQTT broker: default port 1883.
- `api_studio/` is legacy/disabled and is not started by the supported launcher.
- Active Portal UI file: `portal/simulator_ui.html`.
- Active Portal server: `portal/portal_app.py` (currently a small stdlib HTTP server; migration to FastAPI is technical debt, not a reason to add more manual routing).

## Unified runtime

New architecture lives under `industrial_simulator/app/simulation/`:

- `models.py` — canonical simulation/source/target/frame/world models.
- `contracts.py` — deliberately small source/target contracts.
- `sources.py` — adapters over existing CSV/dataset managers, domain generators, SAP/LIMS source simulators, and small inline data.
- `targets.py` — adapters over existing OPC UA and MQTT implementations plus shared HTTP data-plane target support.
- `runtime.py` — `SimulationInstance`, target queues, independent clocks, `SimulationManager`, Worlds, persistence, and interface-host ownership.
- `api.py` — `/api/v2` control/data API.

Legacy replay APIs and `SimulatorEngine` remain during migration for compatibility. Do not build new features into the legacy protocol-combination model unless needed to preserve existing behavior. New functionality should use the unified runtime.

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

## Complexity policy

For new or materially modified code:

- A (1–5): preferred.
- B (6–10): normal.
- C (11–20): allowed when the branching is domain/lifecycle logic and the function remains understandable.
- D/E/F (>20): do not introduce; decompose before merge.

CI gates the new unified runtime at C maximum. Do not game the metric with meaningless helper extraction; reduce decisions or use data-driven dispatch where it genuinely clarifies behavior.

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
