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
| P1-01 | P1 | FIXED | `quality_column` and `source_timestamp_column` were configuration without complete replay behavior | Replay now validates and emits configured quality/source-timestamp columns to OPC UA while preserving MQTT compatibility. |
| P1-02 | P1 | FIXED | Diagnostics UI created a second `/api/status` polling loop | Diagnostics renders from the main status payload; no independent network polling remains. |
| P1-03 | P1 | FIXED | Diagnostics JS dynamically manufactured markup and CSS | Diagnostics markup is static HTML, presentation is static CSS, and JS is render-only. |
| P1-04 | P1 | FIXED | Rich diagnostics were attached only to the legacy UI/status surface | Unified `/api/v2/interfaces` host cards now render diagnostics for shared and dedicated OPC UA listeners. |
| P1-05 | P1 | FIXED | Session diagnostics depended on asyncua private fields without explicit capability reporting | Private introspection remains isolated and snapshots explicitly report session/subscription introspection availability. |
| P2-01 | P2 | FIXED | OPC UA datatype constants were duplicated across modules | `models.py` now exports the canonical registry from `opcua_types.py` rather than maintaining another list. |
| P2-02 | P2 | FIXED | Initial `None` could not distinguish unspecified value from explicit typed null | `model_fields_set` preserves omitted-vs-explicit intent with no new configuration switch; unified adaptation preserves that intent. |
| P2-03 | P2 | FIXED | Legacy server silently entered mock mode when asyncua was unavailable | OPC UA startup now fails clearly when asyncua is unavailable; tests can still explicitly exercise mock internals without reporting a running network server. |

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

### P1-01 — make replay metadata real — `66d5f19`, `a28dd11`, `0359518`

- Replay now validates configured quality/source-timestamp columns with the value column.
- Replay payloads carry value, datatype, quality and source timestamp into OPC UA.
- The dual-protocol adapter deliberately strips enriched tuples back to value/datatype for MQTT while retaining MQTT metadata.
- Added focused regression coverage proving configured metadata reaches the publisher.

### P1-02 — one status poll — `e0519e7`

- Removed the diagnostics module's independent `/api/status` fetch and timer.
- Diagnostics now renders whenever the main raw status payload changes.

### P1-03 — static diagnostics UI — `15325f8`, `145e6a0`, `9a507f2`

- Moved diagnostics cards/tables into `index.html`.
- Moved diagnostics presentation into `opcua-diagnostics.css`.
- Reduced `opcua-diagnostics.js` to data rendering and status observation.

### P1-04 — canonical unified host diagnostics — `4117e33`

- Added live diagnostics blocks to the Portal's shared and dedicated OPC UA host cards.
- The canonical interface-host view now exposes clients, sessions, reads, writes, failures and recent activity from `/api/v2/interfaces`.

### P1-05 — explicit private-introspection capability — `bcad0ec`, `935e653`

- Kept all asyncua private session/subscription access inside `OpcUaDiagnostics`.
- Added explicit session/subscription introspection capability flags.
- Unavailable session internals now produce null client/session counts rather than misleading zeros.
- Added focused degradation tests.

### P2-01 — one datatype registry — `54c2830`

- Removed the duplicate datatype literal set from `models.py`.
- The compatibility export now points to `opcua_types.SCALAR_TYPES`.

### P2-02 — explicit typed-null semantics — `2e7a312`, `af68077`, `b6a6be2`

- Initial value selection now uses Pydantic's existing `model_fields_set` rather than testing `value is None`.
- Omitted initial values still receive a deterministic type default.
- Explicit `initial_value=None` remains a typed null.
- Unified signal-to-tag adaptation preserves whether the initial value field was actually supplied.
- Added regression coverage for both legacy and unified adapters.

### P2-03 — no silent OPC UA mock startup — `4048075`, `5744380`

- Removed the production behavior that reported OPC UA as running when `asyncua` could not be imported.
- Startup now raises a clear dependency/runtime error and `diagnostics_available` remains false.
- Added focused regression coverage for the missing-dependency path.

## Final audit state

All issues identified by the 2026-09-14 OPC UA Ponytail audit are resolved on this branch. The intended ownership after cleanup is:

```text
opcua_types.py
  -> the only OPC UA datatype/coercion/quality implementation

OpcUaTagServer
  -> low-level OPC UA host mechanics, nodes, writes, diagnostics and server loop

UnifiedOpcUaServer
  -> security/auth specialization + unified-model adaptation only

InterfaceHostManager
  -> shared/dedicated listener lifecycle

SimulationInstance / targets[]
  -> canonical simulation ownership
```

The legacy replay API remains a compatibility surface, but new OPC UA host behavior is no longer implemented as a separate parallel type/node/update stack.
