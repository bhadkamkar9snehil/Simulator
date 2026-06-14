# Architecture

API Simulator Studio is built around a config-driven runtime.

## Request pipeline

1. Receive API call.
2. Match method and path against configured endpoints.
3. Extract path parameters.
4. Parse JSON body.
5. Validate configured request schema.
6. Execute endpoint behavior mode.
7. Read or write configured data stores.
8. Execute rules.
9. Emit events.
10. Render response template.
11. Log request and response.
12. Return JSON response.

## Key objects

- Project: top-level simulator workspace.
- Endpoint: method/path/mode/schema/response/rule definition.
- Data Store: lightweight SQLite-backed record table.
- Rule: condition plus actions.
- Event: live event stream payload.
- API Log: full request/response audit trail.

## Why config-driven

The Flask app does not generate Python files for each API. A single dynamic dispatcher serves all configured APIs. This keeps simulator creation fast and avoids restarts during demos.
