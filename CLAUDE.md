# Development Guidelines

## Quick Start
- Entrypoint: `RUN_SIMULATOR.bat`
- Portal runs at http://localhost:8001
- Bundled Python runtime in `runtime/python`

## Architecture

Three main services:
1. **industrial_simulator** — Tag data replay via MQTT
2. **api_studio** — REST API for simulator control and data access
3. **portal** — Web UI for management (primary user-facing surface)

## Rules

- Keep `RUN_SIMULATOR.bat` as the single entrypoint
- Portal UI is the only user-facing surface
- Do not add alternate launchers or entry points
- Runtime startup is orchestrated by `suite_runtime.py`

## Development Workflow

- Read code before proposing changes
- Fix root causes; avoid fallback hacks
- Keep startup, API, and UI concerns separated
- Validate changes against the portal (http://localhost:8001)

## File Hygiene

- Keep generated files and runtime artifacts out of git (see `.gitignore`)
- No destructive git operations without explicit approval
- Use focused validation tied to changed surfaces
