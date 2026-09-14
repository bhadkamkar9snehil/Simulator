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
| P0-01 | P0 | FIXED | Duplicate OPC UA datatype implementations (`opcua_types.py` and datatype logic in `opcua_support.py`) | `opcua_types.py` is now the single canonical OPC UA coercion/Variant/StatusCode/default implementation. `opcua_support.py` retains compatibility facades only. |
| P0-02 | P0 | FIXED | Legacy and unified OPC UA server implementations had overlapping node/update ownership | `OpcUaTagServer` is the low-level host primitive. `UnifiedOpcUaServer` is now a thin security/auth + unified-model adapter; it no longer duplicates node creation/update/type behavior. |
| P0-03 | P0 | FIXED | `DataType = str` weakened validation outside `TagMapping` | Unified `SignalValue`, `SignalDefinition`, and `SignalMapping` now validate scalar/array datatypes against the canonical registry at construction. |
| P0-04 | P0 | FIXED | `type_inference.convert_value()` was an independent execution-time conversion path | Compatibility callers may still use the function, but it delegates all coercion semantics to `opcua_types.py`; type inference owns inference only. |
| P0-05 | P0 | FIXED | StatusCode semantics differed between legacy and unified runtimes | Both surfaces now delegate to the canonical StatusCode conversion; tests cover exact named/numeric values and invalid-name rejection. |
| P1-01 | P1 | IN PROGRESS | `quality_column` and `source_timestamp_column` are configuration without complete replay behavior | Wire both through replay or remove them. |
| P1-02 | P1 | OPEN | Diagnostics UI creates a second `/api/status` polling loop | One status poll feeds all renderers. |
| P1-03 | P1 | OPEN | Diagnostics JS dynamically manufactures markup and CSS | Static markup/styles; diagnostics module renders data only. |
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

## Change log

### Audit initialization — `aab9dc6`

- Recorded the issues found during the 2026-09-14 Ponytail audit.
- P0-01 selected as the first cleanup item because datatype semantics must have exactly one owner before subsequent replay/model fixes are safe.

### P0-01 — canonical OPC UA datatype layer — `5f2652a`, `9f69cf5`

- Removed the independent datatype registry and coercion/Variant/StatusCode/default implementations from `opcua_support.py`.
- `opcua_support.py` now delegates datatype behavior to `opcua_types.py` while retaining the old function signatures as a compatibility facade.
- Unified type overrides now accept the same scalar and array syntax as the canonical layer.
- Updated support tests to exercise canonical array and strict integer-range behavior through the compatibility facade.
- Ownership rule: OPC UA datatype semantics have one owner: `app/opcua_types.py`.

### P0-02 — shrink unified OPC UA server specialization — `53c2d42`

- Removed duplicate unified-runtime node creation and value-update implementations.
- `UnifiedOpcUaServer.configure_signals()` now translates unified signal definitions into the canonical `ReplayConfig`/`TagMapping` path owned by `OpcUaTagServer`.
- `UnifiedOpcUaServer.update_signals()` now delegates directly to the canonical host update path.
- Retained only behavior that is genuinely specific to the unified host: per-target security/auth configuration and translation from unified models.
- Attached the common diagnostics component in the secured unified start path as well.
- Ownership rule: `OpcUaTagServer` owns OPC UA node/update mechanics; `InterfaceHostManager` owns shared/dedicated host lifecycle; `UnifiedOpcUaServer` is a narrow specialization rather than a parallel implementation.

### P0-03 — validate unified datatype boundaries — `05fe725`, `df9d970`

- Added canonical datatype validation to unified signal values, signal definitions and mapping overrides.
- Unknown datatype names now fail while the definition/frame is being constructed instead of surfacing later inside an interface target.
- Added focused coverage for scalar, array and invalid unified datatype values.

### P0-04 — one coercion implementation — `fc51672`

- Removed the old Double/Int64/Boolean/String conversion ladder from `type_inference.py`.
- `convert_value()` remains temporarily as a compatibility facade but delegates to `opcua_types.coerce_value()`.
- Ownership rule: inference determines a type name; the canonical OPC UA type layer performs conversion.

### P0-05 — shared quality semantics — `1e1c833`

- Added parity tests proving the support/unified compatibility surface and canonical layer resolve the same named StatusCodes.
- Added exact numeric/hex StatusCode preservation tests.
- Added regression tests proving unknown status names raise rather than becoming Good.
