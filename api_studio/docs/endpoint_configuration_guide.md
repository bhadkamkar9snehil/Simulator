# Endpoint Configuration Guide

## Endpoint path

Use normal API paths and optional path parameters in braces.

Examples:

- `/api/v1/assets`
- `/api/v1/assets/{id}`
- `/api/v1/sap/pm/notifications`
- `/api/v1/sap/pm/notifications/{id}`

## Request schema

Example:

```json
{
  "fields": [
    {"name": "assetCode", "type": "text", "required": true},
    {"name": "healthScore", "type": "number", "required": true},
    {"name": "condition", "type": "text", "default": "AUTO"}
  ]
}
```

Each field can use:

- `name`
- `type`
- `required`
- `default`
- `enum`
- `source`: `body`, `query`, `path`, or `headers`

## Response template

Example:

```json
{
  "success": true,
  "message": "Health snapshot accepted",
  "assetCode": "{{body.assetCode}}",
  "healthScore": "{{body.healthScore}}",
  "timestamp": "{{now}}"
}
```

## Rule condition examples

- `body.healthScore < 60`
- `body.downtimeMinutes > 10`
- `path.id == EAF_01`
- `body.priority == HIGH`

## CRUD endpoint setup

For a CRUD endpoint, set:

- mode: `crud`
- store_name: name of a data store

For `GET /resource`, it returns all records.
For `GET /resource/{id}`, it returns one record.
For `POST /resource`, it creates a record.
For `PATCH /resource/{id}`, it updates a record.
For `DELETE /resource/{id}`, it deletes a record.
