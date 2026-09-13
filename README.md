# Simulator

Windows/offline industrial simulation suite for generating and replaying process data through OPC UA and other integration interfaces.

## Product direction

The primary product path is a **simulation-centric, concurrent OPC UA simulator**:

- run many independent simulations at once;
- source each simulation from files, registered datasets, industrial generators, or enterprise source simulators;
- tune timing, replay, mappings and targets independently per simulation;
- serve simulations through shared or dedicated OPC UA endpoints;
- attach optional MQTT, HTTP, SQL Server and OData targets to the same canonical simulation stream;
- manage the normal workflow from the Portal UI rather than protocol-specific replay pages.

Detailed product and architecture documents:

- [`docs/UNIFIED_SIMULATOR_REQUIREMENTS.md`](docs/UNIFIED_SIMULATOR_REQUIREMENTS.md)
- [`docs/CURRENT_STATE_AND_COMPLEXITY_BASELINE.md`](docs/CURRENT_STATE_AND_COMPLEXITY_BASELINE.md)
- [`docs/UNIFIED_RUNTIME_IMPLEMENTATION.md`](docs/UNIFIED_RUNTIME_IMPLEMENTATION.md)

## Start

On the supported Windows/offline distribution, run:

```bat
RUN_SIMULATOR.bat
```

Default services:

- Portal: `http://localhost:8001`
- Industrial API: `http://localhost:8000`
- OPC UA: `opc.tcp://localhost:4840/simulator`
- MQTT broker: `localhost:1883`

The Portal root is the new simulation workspace. The previous Portal surface remains temporarily available at `/legacy` during migration.

## Runtime model

The suite preserves the bundled Python runtime/wheelhouse deployment model. `suite_runtime.py` validates the runtime and wheelhouse, prepares the local environment, starts the suite services, and opens the Portal.

The unified runtime is under:

```text
industrial_simulator/app/simulation/
```

Its central model is:

```text
Source
  ↓
Simulation Instance
  ↓
Canonical Frame + Mapping
  ↓
Target Bindings
  ↓
Shared / Dedicated Interface Hosts
```

A simulation owns its source, clock, cursor, mappings and lifecycle. Interface hosts own network listeners. A simulation can publish one canonical state stream to multiple independent targets.

## Current source families

- CSV / Excel
- registered datasets
- Parquet / Parquet folders
- industrial domain generators
- SAP PP source simulator
- LIMS source simulator
- inline rows for diagnostics/tests

## Current target families

- OPC UA — shared or dedicated hosting
- MQTT
- HTTP snapshot / NDJSON / SSE / WebSocket
- SQL Server
- OData
- internal/memory diagnostics

## Validation policy

**GitHub Actions is not used for this repository.** Do not add `.github/workflows/*`, required Actions checks, CI badges, or GitHub-hosted CI.

Tests, syntax checks, complexity checks and release validation are run locally/manual or through an explicitly selected non-GitHub mechanism.

## Repository boundary

Simulator is standalone. Downstream applications consume Simulator through its supported interfaces; downstream-product-specific knowledge does not belong in this repository.
