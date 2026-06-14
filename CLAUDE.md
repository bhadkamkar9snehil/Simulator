# Simulator — Codebase Knowledge Base

> Maintained for future agents. Update this file whenever you learn something new about the codebase.

---

## Quick Start
- Single entrypoint: `RUN_SIMULATOR.bat` (double-click or run from terminal)
- Portal UI: http://localhost:8001
- Bundled Python runtime: `runtime/python/python.exe` (ships in git, no separate install)
- Setup: `irm https://raw.githubusercontent.com/bhadkamkar9snehil/Simulator/main/setup_simulator.ps1 | iex`

---

## Architecture

Three services, started together by `suite_runtime.py`:

| Service | Port | Role |
|---|---|---|
| `industrial_simulator` | 8000 | Tag data replay — reads CSV, publishes over MQTT + OPC UA |
| `api_studio` | 5050 | REST API — simulator control and data access |
| `portal` | 8001 | Web UI — the ONLY user-facing surface |

`suite_runtime.py` orchestrates startup, port assignment, environment setup, and health checks.

---

## Key Files

| File | Role |
|---|---|
| `suite_runtime.py` | Orchestrator — `ensure-env`, `start-hidden`, `save-ports-from-env` subcommands; DEFAULT_PORTS has 5 keys |
| `portal/portal_app.py` | FastAPI serving portal at port 8001; manages start/stop via suite_runtime imports |
| `portal/simulator_proto.html` | Monolithic 85 KB single-page UI; served at `/` by the FastAPI frontend |
| `industrial_simulator/` | Tag replay engine |
| `api_studio/` | REST control API |
| `RUN_SIMULATOR.bat` | Single entrypoint — do not create alternatives |
| `setup_simulator.ps1` | One-command installer: installs Git, clones, validates bundled runtime, runs ensure-env |

---

## Bundled Python Runtime

- Path: `runtime/python/python.exe`
- Ships **in git** (not gitignored, not downloaded separately)
- `runtime_pids.json` IS gitignored (runtime artifact)
- `suite_runtime.py ensure-env` creates the venv using this bundled Python + offline wheels — no internet required after clone

---

## OPC UA Server

- Endpoint: `opc.tcp://localhost:4840/simulator`
- Namespace URI: `http://local/industrial-tag-simulator`
- Node layout: `Objects / TagSimulator / <tag variables>` (one variable per tag)
- The Simulator publishes here continuously during replay — this is how ACM reads it

---

## MQTT

- Topic: `industrial-tag-simulator/flat`
- Payload: `{"published_at": "...", "tag1": 1.23, "tag2": 4.56, ...}` (flat wide JSON per tick)

---

## Hard Constraints

- **Simulator has zero knowledge of ACM.** Never add ACM references, imports, or configuration to this repo. All integration lives in ACM.
- `RUN_SIMULATOR.bat` is the single entrypoint — no alternate launchers.
- Portal UI is the only user-facing surface — no alternate UIs.
- `suite_runtime.py` owns startup orchestration — do not bypass it.

---

## Port Assignment

`DEFAULT_PORTS` in `suite_runtime.py` has exactly 5 keys:
- `industrial_web_port`
- `api_studio_port`
- `portal_port`
- `opcua_port`
- `mqtt_broker_port`

---

## ACM Integration (read-only reference — implement in ACM, not here)

ACM connects to the Simulator via OPC UA as a historian source:
1. ACM's `acm_opcua_bridge.py` polls `opc.tcp://localhost:4840/simulator` every 1 s
2. Bridge buffers tag rows into `data_cache/opcua_buffer.db`
3. ACM's pipeline reads from that SQLite file — Simulator never knows ACM exists

To register the Simulator as an ACM asset (run from the ACM directory):
```bash
python scripts/acm_seed_demo.py --opcua opc.tcp://localhost:4840/simulator --db acm_results.db
```

---

## Development Rules

- Read code before proposing changes
- Fix root causes; avoid fallback hacks
- Keep startup, API, and UI concerns separated
- Validate UI changes against the portal (http://localhost:8001)
- Keep generated files and runtime artifacts out of git (see `.gitignore`)
- No destructive git operations without explicit approval

---

## Development Branch

Active development branch: `claude/upbeat-hopper-m39epw`. Merge to `main` after each task.
