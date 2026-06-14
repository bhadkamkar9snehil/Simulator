# API Simulator Studio

A Windows-friendly Flask utility for creating configurable mock APIs for simulators and demos. It can receive JSON, validate request structure, return configured response structures, store state in SQLite, run rules, create events, and stream live activity.

## What this package provides

- Browser UI at `http://localhost:5050`
- Config-driven API builder
- Dynamic API dispatcher
- SQLite-backed projects, endpoints, data stores, records, logs, and events
- Request schema validation
- Response templates and field mapping
- Rule engine with conditions and actions
- Stateful CRUD simulation
- Static and echo/transform APIs
- Server-sent event stream
- NDJSON tag stream
- Preloaded Steel Shop + SAP PM demo project
- OpenAPI export at `/openapi.json`
- Postman collection export at `/postman_collection.json`
- Portable project JSON export/import

## Quick start on Windows

1. Extract the zip.
2. Double-click `setup_and_run.bat`.
3. Open `http://localhost:5050`.

For later runs, use `run.bat`.

For a more production-like local server, use `run_waitress.bat`.

## Preloaded demo APIs

The default project includes these callable endpoints:

- `GET /api/v1/assets`
- `GET /api/v1/assets/{id}`
- `POST /api/v1/historian/tags`
- `POST /api/v1/asset-health/snapshots`
- `POST /api/v1/downtime/events`
- `POST /api/v1/sap/pm/notifications`
- `GET /api/v1/sap/pm/notifications`
- `GET /api/v1/sap/pm/notifications/{id}`
- `POST /api/v1/mes/workorders`
- `GET /api/v1/stream/events`
- `GET /api/v1/stream/tags`

## Useful sample calls

Health check:

```powershell
Invoke-RestMethod http://localhost:5050/api/studio/health
```

List assets:

```powershell
Invoke-RestMethod http://localhost:5050/api/v1/assets
```

Submit a health snapshot that creates a mock SAP PM notification because score is below 60:

```powershell
Invoke-RestMethod -Method Post http://localhost:5050/api/v1/asset-health/snapshots `
  -ContentType "application/json" `
  -Body '{"assetCode":"EAF_01","healthScore":48,"condition":"CRITICAL"}'
```

Create a manual SAP PM notification:

```powershell
Invoke-RestMethod -Method Post http://localhost:5050/api/v1/sap/pm/notifications `
  -ContentType "application/json" `
  -Body '{"assetCode":"LRF_01","priority":"HIGH","description":"Hydraulic pressure abnormal"}'
```

List created PM notifications:

```powershell
Invoke-RestMethod http://localhost:5050/api/v1/sap/pm/notifications
```

## Endpoint modes

### static
Always returns the configured response template.

### echo_transform
Returns a response built from incoming request, query, path, and headers.

### crud
Uses a configured data store. Supports create, list, read, update, and delete depending on the method and path.

### rule_based
Saves or processes incoming data and runs configured rules. Rules can create records and emit stream events.

## Template tokens

Response templates and rule action templates support these tokens:

- `{{body.fieldName}}`
- `{{query.fieldName}}`
- `{{path.id}}`
- `{{headers.Header-Name}}`
- `{{record.fieldName}}`
- `{{records}}`
- `{{now}}`
- `{{uuid}}`
- `{{seq:PM:6}}`
- `{{random_int:1:100}}`
- `{{random_choice:LOW|MEDIUM|HIGH}}`
- `{{calc:len(records)}}`

## Rule format

Example:

```json
[
  {
    "name": "Create PM notification when health is low",
    "condition": "body.healthScore < 60",
    "actions": [
      {
        "type": "create_record",
        "store": "PMNotifications",
        "data": {
          "id": "PM-{{seq:PM:6}}",
          "assetCode": "{{body.assetCode}}",
          "priority": "HIGH",
          "status": "CREATED",
          "description": "Health score is {{body.healthScore}}",
          "createdAt": "{{now}}"
        }
      },
      {
        "type": "emit_event",
        "event_type": "sap_pm_notification",
        "message": "PM notification created for {{body.assetCode}}"
      }
    ]
  }
]
```

Supported rule actions in this version:

- `create_record`
- `update_record`
- `emit_event`
- `call_internal_api`

## Data store designer

Data stores behave like lightweight simulator tables. Create a store, define fields, add seed records, and point CRUD or rule-based endpoints at the store.

Example stores in the preloaded project:

- Assets
- TagReadings
- HealthSnapshots
- DowntimeEvents
- PMNotifications
- WorkOrders

## Export and import

From the UI, open **Import / Export** and download the active project JSON. This file includes:

- project metadata
- endpoint definitions
- data store schemas
- seed/runtime records

It can be imported on another machine running the same utility.

## Smoke test

After the server is running, double-click `smoke_test.bat`.

The test checks:

- studio health
- asset list
- health snapshot submission
- automatic PM notification creation
- PM notification list
- OpenAPI export

## Reset seed data

Run `reset_database.bat`, then start the app again. The default Steel Shop demo project will be recreated.
