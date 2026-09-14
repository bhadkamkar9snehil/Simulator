# OPC UA Ponytail Audit

Branch: `feature/opcua-fidelity-diagnostics`

Purpose: track the architectural cleanup required after the comprehensive OPC UA datatype-fidelity and diagnostics work. Each issue is fixed independently and committed separately. This document is updated as work progresses.

## Status legend

- OPEN — identified and not yet fixed.
- IN PROGRESS — current issue being changed.
- FIXED — code change committed; validation notes recorded.
- DEFERRED — intentionally left for a later architectural milestone with reason documented.

## Issues

| ID | Priority | Status | Issue | Required outcome |
|---|---|---|---|---|
| P0-01 | P0 | FIXED | Duplicate OPC UA datatype implementations (`opcua_types.py` and datatype logic in `opcua_support.py`) | `opcua_types.py` is the single canonical OPC UA coercion/Variant/StatusCode/default implementation. `opcua_support.py` retains compatibility facades only. |
| P0-02 | P0 | FIXED | Legacy and unified OPC UA server implementations had overlapping node/update ownership | `OpcUaTagServer` owns low-level node/update behavior; `UnifiedOpcUaServer` is a thin security/auth + unified-model adapter. |
| P0-03 | P0 | FIXED | `DataType = str` weakened validation outside `TagMapping` | Unified signal models validate scalar/array datatypes against the canonical registry at construction. |
| P0-04 | P0 | FIXED | `type_inference.convert_value()` was an independent execution-time conversion path | Compatibility callers delegate coercion to `opcua_types.py`; type inference owns inference only. |
| P0-05 | P0 | FIXED | StatusCode semantics differed between legacy and unified runtimes | Both surfaces delegate exact named/numeric quality semantics to the canonical StatusCode conversion. |
| P1-01 | P1 | FIXED | `quality_column` and `source_timestamp_column` were configuration without complete replay behavior | Replay validates and emits configured quality/source-timestamp columns to OPC UA while preserving MQTT compatibility. |
| P1-02 | P1 | FIXED | Diagnostics UI had an independent/indirect status-update path | One `/api/status` poll in `app.js` feeds the base status UI and OPC UA diagnostics renderer directly. |
| P1-03 | P1 | OPEN | Diagnostics JS still owns presentation markup generation for tables and depends on diagnostics-specific DOM structure | Keep static layout/styles in HTML/CSS and make diagnostics JS render data only into existing elements. |
| P1-04 | P1 | OPEN | Rich diagnostics are attached to the legacy UI/status surface rather than unified interface-host view | Unified `/api/v2/interfaces` and Portal host UI become the canonical diagnostics surface. |
| P1-05 | P1 | OPEN | Session diagnostics depend on asyncua private fields without explicit capability reporting | Keep introspection isolated and expose availability/degradation explicitly. |
| P2-01 | P2 | OPEN | OPC UA datatype constants are duplicated across modules | One canonical datatype registry. |
| P2-02 | P2 | OPEN | Initial `None` cannot distinguish unspecified value from explicit typed null | Define explicit initial-null semantics without adding redundant switches. |
| P2-03 | P2 | OPEN | Legacy server silently enters mock mode when asyncua is unavailable | Production paths fail clearly; mocks remain explicit test behavior. |

## Working rules

1. One issue per code commit whenever practical.
2. Do not introduce a new framework to solve cleanup problems.
3. Delete duplicate behavior before adding abstractions.
4. Prefer existing unified runtime ownership: `SimulationInstance -> Target -> InterfaceHostManager`.
5. Preserve compatibility at API boundaries while shrinking internal duplication.
6. Every fixed issue records the commit and the resulting ownership rule here.
7. Tracker state must reflect commits actually present on this branch; do not pre-mark planned work as fixed.

## Change log

### Audit initialization — `aab9dc6`

- Recorded the issues found during the 2026-09-14 Ponytail audit.
- P0-01 selected first because datatype semantics must have exactly one owner before subsequent replay/model fixes are safe.

### P0-01 — canonical OPC UA datatype layer — `5f2652a`, `9f69cf5`

- Removed the independent datatype registry and coercion/Variant/StatusCode/default implementations from `opcua_support.py`.
- `opcua_support.py` now delegates datatype behavior to `opcua_types.py` while retaining old signatures as a compatibility facade.
- Unified type overrides use the canonical scalar/array rules.
- Ownership rule: OPC UA datatype semantics have one owner: `app/opcua_types.py`.

### P0-02 — shrink unified OPC UA server specialization — `53c2d42`

- Removed duplicate unified-runtime node creation and value-update implementations.
- `UnifiedOpcUaServer` delegates node/update mechanics to `OpcUaTagServer` and retains only security/auth plus unified-model adaptation.
- Ownership rule: `OpcUaTagServer` owns node/update mechanics; `InterfaceHostManager` owns listener lifecycle.

### P0-03 — validate unified datatype boundaries — `05fe725`, `df9d970`

- Added canonical datatype validation to unified signal values, signal definitions and mapping overrides.
- Unknown datatype names now fail at model construction.

### P0-04 — one coercion implementation — `fc51672`

- Removed the old conversion ladder from `type_inference.py`.
- `convert_value()` remains temporarily as a compatibility facade but delegates to `opcua_types.coerce_value()`.

### P0-05 — shared quality semantics — `1e1c833`

- Added parity tests for named and numeric StatusCodes and invalid-name rejection across compatibility/canonical surfaces.

### P1-01 — make replay metadata real — `66d5f19`, `a28dd11`, `0359518`

- Replay validates configured quality/source-timestamp columns.
- Replay payloads carry value, datatype, quality and source timestamp into OPC UA.
- The dual-protocol adapter strips enriched tuples back to value/datatype for MQTT while preserving MQTT metadata.
- Added focused regression coverage.

### P1-02 — one status transport path — `998525f`, `f722b7b`

- `app.js` now passes the parsed `/api/status` payload directly to `window.renderOpcUaDiagnostics()`.
- Removed diagnostics-side network polling and the MutationObserver/raw-JSON DOM relay.
- Ownership rule: `app.js` owns status transport/polling; diagnostics JS is a renderer only.

### Documentation reconciliation

- Removed stale/future issue statuses and commit references that were not represented by the current branch head.
- P1-03 is the next open issue.
