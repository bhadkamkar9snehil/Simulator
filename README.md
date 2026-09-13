# Simulator

A central, multi-protocol industrial simulator. It generates domain-specific
process data (13 industrial domains) and synthetic camera video, then replays
or streams that data concurrently over OPC UA, MQTT, and HTTP (NDJSON/SSE/
WebSocket), with SAP PP and LIMS ODBC source simulators and SQL Server
projection on top. Everything is driven from one web portal.

## Product direction and requirements

The long-term product direction is a unified, concurrent, multi-source,
multi-target simulator in which independent Simulation Instances can run at
the same time and serve one or more shared or dedicated interface targets.

- [Unified Multi-Interface Simulator — Product and Architecture Requirements](docs/UNIFIED_SIMULATOR_REQUIREMENTS.md)
- [Current State, Ponytail and Complexity Baseline](docs/CURRENT_STATE_AND_COMPLEXITY_BASELINE.md)

The requirements document is the architectural north star. The current-state
baseline records implementation debt and migration findings at the documented
baseline commit; it is expected to become obsolete as those findings are
addressed.

> Maintain this section list as features change. Architecture/agent documentation
> must distinguish current implementation from target architecture.

## Quick start

- Single entrypoint: `RUN_SIMULATOR.bat` (double-click or run from terminal)
- Portal UI: http://localhost:8001 — the only user-facing surface
- Bundled Python runtime: `runtime/python/python.exe` (ships in git, no separate install)
- Setup: `irm https://raw.githubusercontent.com/bhadkamkar9snehil/Simulator/main/setup_simulator.ps1 | iex`

What `RUN_SIMULATOR.bat` does:

- uses the bundled Python runtime in `runtime/python`
- validates or recreates `.venv`, installing only from the bundled offline wheelhouse
- starts the internal MQTT broker, Industrial service, and Portal hidden, orchestrated by `suite_runtime.py`
- leaves legacy API Studio disabled
- opens the portal automatically

## Architecture

| Service | Port | Role |
|---|---|---|
| `industrial_simulator` | 8000 | All simulation logic — generation, replay, jobs, streaming, source simulators, video |
| `api_studio` | 5050 | Legacy/reserved — currently disabled, not started by the suite |
| `portal` | 8001 | Web UI + service lifecycle control (start/stop/ports) |
| internal MQTT broker | 1883 | Local MQTT data-plane endpoint for simulator publishing/testing |
| OPC UA | 4840 | Local OPC UA data-plane endpoint |

`suite_runtime.py` owns startup orchestration, port assignment, and health checks in the current implementation.

## Feature set

**Data generation** (Generate tab, Files subtab)
- 13 domain generators: petroleum pipeline, EAF melting, gas/LPG pipeline,
  rotary equipment, power plant, polyester fiber, GNFC chemical process, and
  steel-plant stages including blast furnace, coke oven, DRI, LRF, CCM, and rolling mill
- Output as small CSV, large Parquet, or local partitioned Lakehouse
- Target by row count, physical/logical bytes, or duration; configurable
  batch size, compression, and speed mode

**Synthetic video generation** (Generate tab, Video subtab)
- Multi-camera synthetic frame generation (PPM segments + manifest today;
  MJPEG/HLS/MP4/RTSP planned)
- Configurable camera count, FPS, resolution, duration, segment length, and
  visual mode; can link a video job to a dataset

**Replay & streaming** (Replay, Streams tabs)
- Replay CSV/registered datasets over OPC UA, MQTT, or both in the current implementation
- HTTP streaming: NDJSON, Server-Sent Events, WebSocket, plus a point-in-time snapshot
- OPC UA endpoint: `opc.tcp://localhost:4840/simulator`; MQTT topic:
  `industrial-tag-simulator/flat`

**Source simulators** (Sources tab)
- SAP PP OData connector (query mode)
- LIMS ODBC connector (query or cycling mode, with watermarking and
  configurable excursion probability)

**Concurrent multi-export runs** (Jobs tab)
- Build mixes of independent exports — e.g. one dataset over OPC UA,
  another over MQTT, a separate SAP PP feed, a separate LIMS feed, and a
  video job — each with its own settings, launched together as one run
- Every job (individually) and every run (as a group) supports pause,
  resume, and stop; global Pause All / Resume All / Stop All lives in the
  command bar

**Datasets & SQL** (Datasets, SQL Server tabs)
- Upload, register, preview, scan, and delete datasets
- Project current tag values into SQL Server

**Full API reference** — every route the simulator serves is listed in the
Overview tab of the portal, grouped by category.

## Notes

- Stop the suite from the portal UI (Settings tab)
- Startup logs are written to `launcher.log`; structured logs are in the Logs tab
- Saved ports live in `simulator_ports.json`
