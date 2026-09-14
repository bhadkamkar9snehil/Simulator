# REST API Simulation

## Purpose

REST API simulation is a first-class **target binding** in the unified Simulator. It does not have its own source, clock, cursor, mapping engine, or lifecycle.

The data path is the same as OPC UA and every other target:

```text
Source
  ↓
Simulation Instance
  ↓
Canonical mapping
  ↓
Canonical frame
  ├─ OPC UA
  ├─ REST API
  ├─ MQTT
  ├─ SQL Server
  └─ OData
```

This means an API and an OPC UA endpoint attached to the same Simulation Instance expose the same simulated state at the same point in simulated time.

## Public endpoint model

Each REST API target represents one independently configurable public endpoint.

Example target:

```text
POST /sim-api/orders/{order_id}
```

If a simulation needs five API endpoints, add five API targets. This intentionally avoids a nested API-project/route framework inside the Simulator. Each target remains independently observable and independently configurable.

All simulated REST endpoints are served by the existing Industrial FastAPI process under:

```text
/sim-api
```

The configured target path is appended to that prefix. Internal simulation IDs do not have to appear in the public URL.

## Configurable request behavior

A REST API target currently supports:

- method: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`;
- arbitrary relative public path;
- named path parameters such as `/orders/{order_id}`;
- query parameters available to custom response templates;
- JSON or text request bodies available to custom response templates;
- required exact request headers, one per line as `Header: value`;
- configurable simulated response delay in milliseconds.

Required headers can simulate simple API-key or bearer-token checks. These values are simulation fixtures, not a secrets-management system.

## Configurable response behavior

Response modes:

### Flat live record

Returns canonical signal values as a flat JSON object. It can optionally include frame context and system fields.

### Live values only

Returns only canonical signal names and their current values.

### Full canonical frame

Returns the complete current `SimulationFrame` including signal metadata.

### Retained history

Returns a bounded history of canonical records. History size is configured per API target.

### Custom JSON template

Returns a user-defined JSON document. Template tokens can reference the live simulation and the incoming request.

Supported token scopes:

```text
${values.TagName}
${context.BatchId}
${meta.sequence}
${meta.timestamp}
${path.order_id}
${query.mode}
${body.quantity}
```

When a JSON value consists entirely of one token, the resolved value keeps its JSON type. For example:

```json
{
  "temperature": "${values.Temperature}",
  "quantity": "${body.quantity}"
}
```

can return numeric values rather than forced strings.

Other response configuration includes:

- success status code;
- status code returned before the first simulation frame is published;
- response headers;
- optional top-level envelope property;
- optional signal field selection;
- optional frame context;
- optional system fields;
- retained-history size.

## Lifecycle

The public API route exists while the API target is running.

Requests do **not** advance the source cursor. The Simulation Instance owns time and source progression. The API target answers from the latest canonical frame produced by that Simulation Instance.

This is important when multiple targets are attached to one simulation: API requests cannot move OPC UA, MQTT, SQL, or OData to a different simulated point in time.

## Failure and queue behavior

The REST API target uses the same `TargetBinding` delivery controls as other targets:

- bounded target queue;
- overflow policy;
- retry delay;
- failure policy;
- independent target health.

The API target also exposes live target details such as request count, last request time, and retained-history count.

## UI

The Simulation workspace exposes REST API configuration in the same **Targets** tab used by OPC UA and other interfaces.

Users can configure:

- method;
- public route;
- latency;
- request-header requirements;
- response headers;
- response shape;
- status codes;
- field selection;
- history retention;
- response envelope;
- context/system-field inclusion;
- custom JSON response template;
- ordinary target queue/failure behavior.

No raw Simulation Definition JSON is required for normal API setup.

## Current deliberate boundary

The first implementation is JSON/REST-focused and uses the shared Industrial HTTP host. It does not yet create a dedicated per-target HTTP listener/port, simulate arbitrary binary payloads, or provide a general-purpose expression/scripting language.

Those capabilities should be added only for concrete integration requirements. The current template mechanism covers common request/response simulation without introducing an embedded scripting runtime.

## Ponytail rules

When extending API simulation:

1. Keep source, clock and mapping logic in the Simulation Instance; do not duplicate them in the API adapter.
2. Add configuration to the API target only when it changes observable API behavior.
3. Prefer declarative fields over a scripting framework.
4. Reuse the shared FastAPI host unless a real dedicated-port requirement exists.
5. A new API feature must be testable independently and through the full Source → Simulation → API path.
6. Do not add route-builder/plugin abstractions until there are multiple real implementations that require them.
