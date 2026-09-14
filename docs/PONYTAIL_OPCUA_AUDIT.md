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
| P0-01 | P0 | IN PROGRESS | Duplicate OPC UA datatype implementations (`opcua_types.py` and datatype logic in `opcua_support.py`) | `opcua_types.py` becomes the single canonical OPC UA coercion/Variant/StatusCode/DataValue implementation used by legacy and unified runtimes. |
| P0-02 | P0 | OPEN | Legacy and unified OPC UA server implementations have overlapping ownership | Unified runtime/InterfaceHostManager becomes canonical; legacy replay becomes compatibility-facing rather than an equal implementation. |
| P0-03 | P0 | OPEN | `DataType = str` weakens validation outside `TagMapping` | Validate supported scalar/array OPC UA types at shared model boundaries. |
| P0-04 | P0 | OPEN | `type_inference.convert_value()` is still an execution-time conversion path | Type inference remains inference-only; OPC UA execution uses the canonical type layer. |
| P0-05 | P0 | OPEN | StatusCode semantics differ between legacy and unified runtimes | Exact named/numeric quality semantics are shared; invalid quality never silently becomes Good. |
| P1-01 | P1 | OPEN | `quality_column` and `source_timestamp_column` are configuration without complete replay behavior | Wire both through replay or remove them. |
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

### Audit initialization

- Recorded the issues found during the 2026-09-14 Ponytail audit.
- P0-01 selected as the first cleanup item because datatype semantics must have exactly one owner before subsequent replay/model fixes are safe.
