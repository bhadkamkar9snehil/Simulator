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

An API and an OPC UA endpoint attached to the same Simulation Instance therefore observe the same simulated state at the same point in simulated time.

## Public endpoint model

Each REST API target represents one independently configurable public endpoint.

Example:

```text
POST /sim-api/orders/{order_id}
```

If a simulated system needs five independent routes, add five API targets. This intentionally avoids a nested API-project/route framework. Each route remains independently configurable, observable, and removable while still consuming the same canonical simulation stream.

All simulated REST endpoints are served by the existing Industrial FastAPI process under:

```text
/sim-api
```

The configured target path is appended to that prefix. Internal simulation IDs do not have to appear in the public URL.

## Request contract

A REST API target supports:

- `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, and `OPTIONS`;
- arbitrary relative public paths;
- named path parameters such as `/orders/{order_id}`;
- query parameters;
- JSON request bodies;
- text request bodies;
- exact required request headers;
- required path/query/body values;
- configurable rejection status for missing or incorrect request values;
- fixed response latency;
- optional latency jitter.

Required headers are configured one per line:

```text
X-Api-Key: demo-key
Authorization: Bearer demo-token
```

Required request values are also declarative. A line without `=` requires presence; a line with `=` requires the exact value:

```text
query.site
query.site=plant-a
body.sample_id
body.type=result
path.order_id
```

These controls simulate an external contract. They are not intended to become an embedded request-validation language.

## Data selection

API requests do not drive simulation time. A target selects from state that its parent Simulation Instance has already produced.

### Latest frame

The default mode answers from the current canonical frame.

### Match retained history

A request can select a previously produced frame by matching one request value against one simulated value.

Example route:

```text
GET /sim-api/orders/{order_id}
```

Configuration:

```text
Simulated field: values.OrderId
Request value:   path.order_id
```

A request for `/orders/A-100` searches the API target's bounded retained frames from newest to oldest and returns the latest matching simulated record. The Simulation Instance cursor is not moved and other targets are unaffected.

Supported simulated lookup roots are the normal template roots such as `values`, `context`, and `meta`. Request lookup roots are `path`, `query`, and `body`.

## History responses

Each API target owns a bounded retained-frame deque. History retention is configured per target.

History responses support:

- oldest-first or newest-first ordering;
- a configured default page size;
- a configured maximum page size;
- `?offset=`;
- `?limit=`.

This is deliberately simple offset/limit paging rather than a generic query engine.

## Response body formats

A target can return:

### JSON

JSON response shapes are:

- flat canonical record;
- canonical values only;
- complete `SimulationFrame`;
- retained history;
- custom JSON template.

### Text / XML / textual formats

A target can return an arbitrary text template with a configured media type, for example:

```text
application/xml
text/plain
text/csv
application/custom+xml
```

The same template tokens available to JSON are available to textual bodies.

### Empty body

A route can deliberately return no body. Status codes that are bodyless by HTTP semantics such as `204` are also returned without a body.

## Template values

Templates can use simulation state and the incoming request:

```text
${values.TagName}
${context.BatchId}
${meta.sequence}
${meta.timestamp}
${meta.source_timestamp}
${meta.simulation_id}
${path.order_id}
${query.mode}
${body.quantity}
```

When a JSON value consists entirely of one token, the resolved value keeps its JSON type rather than being converted to text.

Example:

```json
{
  "temperature": "${values.Temperature}",
  "quantity": "${body.quantity}"
}
```

may return numeric JSON values.

## Response headers

Response headers are configured one per line:

```text
X-Simulated: yes
Location: /orders/${path.order_id}
ETag: seq-${meta.sequence}
```

Header values use the same request/simulation template scope as response bodies. When history-match selection is used, header tokens and body tokens are resolved from the same selected retained frame.

## Status codes

The target currently separates:

- success status;
- no-data status;
- history-match not-found status;
- request-contract rejection status.

This allows common integration behavior such as `201`, `204`, `400`, `401`, `404`, `422`, and `503` without embedding application logic in the simulation engine.

## Latency

Each API target can configure:

- a fixed base latency in milliseconds;
- an optional random `0..N` millisecond jitter.

Latency is applied per request and is reflected in live request metrics.

## Runtime observability

The API target reports live request behavior, including:

- request count;
- successful `2xx/3xx` count;
- `4xx` count;
- `5xx` count;
- last request time;
- last response status;
- last response latency;
- retained history count;
- active method/path/body mode/selection mode.

Active REST routes also appear in the **Interface hosts** workspace beside active OPC UA hosts. That view is populated from the backend registry and therefore represents routes that are actually registered now, not remembered browser state.

## Lifecycle

The public API route exists while the API target is running.

Requests never advance the source cursor. The Simulation Instance owns source progression, timing, replay and mappings. API requests only inspect current or already-retained canonical state.

For a continuously available simulated API, use an appropriate ongoing replay mode such as `loop_forever` or `hold_last` rather than a finite `once` replay whose Simulation Instance completes and tears down its targets.

## Failure and queue behavior

The REST API target uses the same `TargetBinding` delivery controls as other targets:

- bounded target queue;
- overflow policy;
- retry delay;
- failure policy;
- independent target health.

Publishing canonical frames into the API projection and serving external API requests remain separate concerns.

## UI

The Simulation workspace exposes the entire ordinary REST API target contract from the same **Targets** tab used by OPC UA and other interfaces.

It covers:

- method and public route;
- latency and jitter;
- required headers;
- required path/query/body values;
- request rejection status;
- current-frame or retained-frame selection;
- match paths;
- retained history and paging;
- body format and media type;
- JSON response shape;
- success/no-data/not-found status codes;
- field selection;
- history ordering;
- response envelope;
- context/system-field inclusion;
- dynamic response headers;
- JSON response template;
- text/XML response template;
- target queue/failure behavior;
- live request metrics.

Normal API simulation does not require editing raw Simulation Definition JSON.

There is deliberately **no built-in API tester or separate validator workspace**. The product surface defines the external contract and shows actual live runtime state; the simulated endpoint itself is what external software calls.

## Current deliberate boundaries

The implementation is currently request/response HTTP simulation on the shared Industrial FastAPI listener. It does not create a separate HTTP process per endpoint and it does not embed a general-purpose scripting/expression language.

Binary payloads, dedicated listener/port ownership, advanced authentication protocols, or another query language should be added only for concrete integration requirements.

## Ponytail rules

When extending API simulation:

1. Keep source, clock and mapping logic in the Simulation Instance; do not duplicate them in the API adapter.
2. Add configuration only when it changes observable external API behavior.
3. Prefer small declarative controls over a scripting runtime.
4. Reuse the shared FastAPI host unless a concrete integration requires another listener.
5. Keep one endpoint as one ordinary target binding rather than introducing an API-project framework.
6. Reuse the same bounded retained frames for history and request lookup.
7. Keep runtime truth in the backend; the UI renders it rather than manufacturing target state.
8. Avoid tester, validator, mock-project, or plugin subsystems that do not contribute to serving the simulated API.
