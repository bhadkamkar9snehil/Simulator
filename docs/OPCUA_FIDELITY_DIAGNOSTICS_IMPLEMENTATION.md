# OPC UA Fidelity and Diagnostics Implementation

**Branch:** `feature/opcua-fidelity-diagnostics`  
**Status:** Implemented; Ponytail cleanup complete  
**Audit tracker:** `docs/PONYTAIL_OPCUA_AUDIT.md`

## Purpose

This document describes the post-cleanup OPC UA implementation after completing datatype fidelity, replay metadata propagation, live diagnostics and the follow-up Ponytail audit.

It is an implementation-status document. The normative product direction remains in `UNIFIED_SIMULATOR_REQUIREMENTS.md`.

## Ownership model

The implementation now follows a deliberately narrow ownership model:

```text
opcua_types.py
  -> canonical OPC UA datatype, coercion, array, quality and DataValue semantics

OpcUaTagServer
  -> low-level OPC UA host mechanics
     - asyncua lifecycle
     - node creation
     - typed writes
     - diagnostics attachment
     - server loop

UnifiedOpcUaServer
  -> thin specialization
     - security/authentication
     - certificate/key selection
     - unified SignalDefinition -> TagMapping adaptation

InterfaceHostManager
  -> shared and dedicated OPC UA listener ownership

SimulationInstance / Target
  -> canonical simulation lifecycle and target publication
```

The legacy replay API remains a compatibility surface. It no longer owns a separate datatype or unified-node/update implementation.

## Canonical datatype fidelity

`industrial_simulator/app/opcua_types.py` is the single owner for OPC UA datatype semantics.

Supported scalar base types:

- Boolean
- SByte / Byte
- Int16 / UInt16
- Int32 / UInt32
- Int64 / UInt64
- Float / Double
- String
- DateTime
- Guid
- ByteString
- XmlElement
- NodeId
- QualifiedName
- LocalizedText
- StatusCode

Arrays are supported as either:

```text
UInt16[]
Array[UInt16]
```

The canonical layer owns:

- datatype recognition;
- scalar/array splitting;
- array parsing;
- strict signed/unsigned integer range enforcement;
- Boolean parsing;
- UTC DateTime normalization;
- Guid conversion;
- ByteString conversion;
- NodeId / QualifiedName / LocalizedText conversion;
- exact named/numeric StatusCode conversion;
- explicit `ua.VariantType` selection;
- typed `ua.DataValue` construction;
- deterministic defaults for omitted initial values.

Compatibility functions in `opcua_support.py` and `type_inference.py` delegate to this layer instead of carrying separate conversion rules.

## Model-boundary validation

Unified simulation models validate datatype names at construction:

- `SignalValue.data_type`
- `SignalDefinition.data_type`
- `SignalMapping.data_type`

Legacy `TagMapping` also validates its datatype against the canonical registry.

Unknown datatype names therefore fail before publication rather than being silently treated as strings.

## Replay quality and source timestamps

Legacy replay now supports per-tag metadata from either static configuration or configured source columns:

```text
quality
quality_column
source_timestamp
source_timestamp_column
```

Replay emits an enriched protocol value:

```text
(value, data_type, quality, source_timestamp)
```

OPC UA receives all four fields and writes an explicit typed `DataValue`.

The dual-protocol compatibility adapter deliberately projects the enriched payload back to `(value, data_type)` for the existing MQTT publisher while retaining quality/source metadata in MQTT metadata.

Configured metadata columns are validated during replay configuration along with the value column.

## Null semantics

Initial values distinguish two cases without introducing another configuration flag:

```text
initial_value omitted
    -> deterministic type default

initial_value explicitly supplied as null
    -> typed OPC UA null
```

This distinction uses Pydantic's `model_fields_set` and is preserved when unified `SignalDefinition` objects are adapted to `TagMapping` objects.

Runtime writes can also carry `None` as the typed value.

## StatusCode semantics

Quality/status conversion has one implementation.

Supported behavior includes:

- exact named OPC UA status codes such as `BadNoData`;
- common quality aliases;
- numeric status codes;
- hexadecimal numeric status codes;
- rejection of unknown named status codes.

Unknown status names do **not** silently fall back to `Good`.

## Live diagnostics

`industrial_simulator/app/opcua_diagnostics.py` owns lightweight OPC UA observability.

It uses asyncua server callbacks for external read/write activity and maintains only bounded in-memory state.

Reported diagnostics include:

- connected clients when session introspection is available;
- session count;
- session details;
- subscriptions per session when available;
- read request count;
- nodes read;
- write request count;
- nodes written;
- failed writes;
- last read timestamp;
- last write timestamp;
- bounded recent read/write activity.

There is no diagnostics database, independent worker, metrics framework or second runtime.

## asyncua private-introspection boundary

Connected-session and subscription detail currently requires asyncua private/internal fields.

All such access is isolated inside `OpcUaDiagnostics`.

The status payload explicitly reports:

```text
session_introspection_available
subscription_introspection_available
```

If the private session registry is unavailable, client/session counts become `null` rather than incorrectly reporting zero.

This keeps dependency fragility visible and contained.

## Status surfaces

### Legacy compatibility status

`/api/status` includes:

```text
protocol.opcua.diagnostics
```

The legacy frontend consumes this for compatibility.

### Canonical unified host status

`/api/v2/interfaces` exposes diagnostics through each shared or dedicated OPC UA host because `InterfaceHostManager` publishes the host server status.

The Portal OPC UA host view is the canonical UI surface for host-level diagnostics.

## UI behavior

The legacy industrial frontend keeps a compatibility diagnostics panel, but it no longer owns a second network poll.

Current structure:

```text
index.html
  -> static diagnostics markup

opcua-diagnostics.css
  -> diagnostics presentation

opcua-diagnostics.js
  -> render-only behavior
```

The main application status poll remains the single `/api/status` polling loop.

The unified Portal host view displays live diagnostics directly from `/api/v2/interfaces` for both shared and dedicated OPC UA hosts.

## Missing dependency behavior

Production OPC UA startup no longer silently reports a mock server as running if `asyncua` cannot be imported.

Startup raises a clear runtime/dependency error instead.

Unit tests may still explicitly place the server in mock mode to test conversion/state behavior without opening a network listener.

## Focused regression coverage

The branch contains focused tests for the completed work, including:

- `test_opcua_fidelity_diagnostics.py`
  - integer widths/boundaries;
  - arrays;
  - DateTime;
  - Guid;
  - nulls;
  - explicit DataValue type/status/timestamp;
  - diagnostics counters;
  - real asyncua client/server round trip when asyncua is present.

- `test_opcua_support.py`
  - compatibility facade delegates to canonical type behavior;
  - array type overrides;
  - strict integer range behavior.

- `test_opcua_model_validation.py`
  - unified model datatype validation.

- `test_opcua_quality_semantics.py`
  - named/numeric/hex StatusCode parity;
  - invalid status rejection.

- `test_replay_quality_timestamp_columns.py`
  - replay quality/source timestamp column propagation.

- `test_opcua_diagnostics_capabilities.py`
  - explicit degradation when asyncua private session/subscription internals are unavailable.

- `test_opcua_initial_null_semantics.py`
  - omitted initial value versus explicit null.

- `test_opcua_dependency_failure.py`
  - clear failure when asyncua is unavailable.

## Validation policy

This repository intentionally does not use GitHub Actions for routine validation. Tests are committed for local/manual execution under the project's supported runtime.

A green GitHub CI result therefore must not be inferred from the presence of these tests.

## Remaining OPC UA debt outside this audit

The Python 3.14 / asyncua compatibility shim in `app/opcua_server.py` remains a known dependency hotspot:

```text
_prepare_asyncua_python314_type_hints()
```

The Ponytail cleanup reduced duplication around it but did not remove this shim.

It should remain isolated and should be deleted when the supported asyncua/runtime combination no longer requires it. No additional Simulator behavior should be built on top of asyncua serializer internals.

Security policies/certificates/authentication and hierarchy/write-simulation work should continue to use the existing unified target/host architecture rather than creating new protocol-specific runtimes.
