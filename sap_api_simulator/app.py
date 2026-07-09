from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

try:
    from .sap_data import DATA_DIR, ENTITY_FILES, ensure_csv_files, read_entity
except ImportError:
    from sap_data import DATA_DIR, ENTITY_FILES, ensure_csv_files, read_entity

SERVICE_ENTITY_SETS = {
    "API_PRODUCT_COST_SRV": ["A_ProductStdCostEstmt", "A_CostCompItmCostEstmt"],
    "API_SLSPRICING_SRV": ["A_PricingConditionRecord"],
    "ZGNFC_CONTRIB_MARGIN_SRV": ["A_ContributionMargin"],
    "API_PRODUCTION_ORDER_2_SRV": ["A_ProductionOrder", "A_ProdOrderConfirmedYield"],
    "ZGNFC_PROD_VARIANCE_SRV": ["A_ProductionVariance"],
    "API_EQUIPMENT_SRV": ["A_Equipment"],
    "API_MAINTNOTIFICATION_SRV": ["A_MaintenanceNotification"],
    "API_MAINTENANCEORDER_SRV": ["A_MaintenanceOrder"],
    "ZGNFC_EQUIP_RELIABILITY_SRV": ["A_EquipmentReliability"],
}

ENTITY_SERVICE = {
    entity_set: service
    for service, entity_sets in SERVICE_ENTITY_SETS.items()
    for entity_set in entity_sets
}

app = FastAPI(title="CSV-backed SAP API Simulator", version="1.0.0")


@app.middleware("http")
async def test_hooks(request: Request, call_next):
    if request.query_params.get("simulate_error") == "true":
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "SAP_SERVICE_UNAVAILABLE",
                    "message": "Simulated SAP backend outage",
                }
            },
        )
    raw_latency = request.query_params.get("simulate_latency", "")
    if raw_latency.isdigit():
        await asyncio.sleep(min(int(raw_latency), 10000) / 1000)
    return await call_next(request)


@app.middleware("http")
async def cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=_cors())
    response = await call_next(request)
    for key, value in _cors().items():
        response.headers[key] = value
    return response


def _cors() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }


def odata_envelope(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"d": {"results": rows}}


def apply_odata(query: dict[str, str], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = rows
    filter_expr = query.get("$filter")
    if filter_expr:
        match = re.match(r"(\w+)\s+eq\s+'?([^']+)'?", filter_expr, flags=re.IGNORECASE)
        if match:
            field, value = match.groups()
            out = [row for row in out if str(row.get(field)) == value]
        else:
            raise HTTPException(status_code=400, detail="Only simple OData filters are supported: Field eq 'value'")
    skip = _query_int(query, "$skip", 0)
    top = _query_int(query, "$top", len(out))
    return out[skip : skip + top]


def _query_int(query: dict[str, str], key: str, default: int) -> int:
    raw = query.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{key} must be an integer") from exc
    if value < 0:
        raise HTTPException(status_code=400, detail=f"{key} must be >= 0")
    return value


@app.get("/")
def service_catalog() -> dict[str, Any]:
    ensure_csv_files()
    entity_sets = [
        f"/sap/opu/odata/sap/{service}/{entity_set}"
        for service, entity_sets_for_service in SERVICE_ENTITY_SETS.items()
        for entity_set in entity_sets_for_service
    ]
    return {
        "service": "CSV-backed SAP API Simulator",
        "status": "running",
        "entitySets": entity_sets,
        "csvManifest": "/datasets",
        "testHooks": {
            "simulate_error": "?simulate_error=true returns 503",
            "simulate_latency": "?simulate_latency=<ms> delays response",
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    ensure_csv_files()
    return {"status": "ok"}


@app.get("/datasets")
def datasets() -> dict[str, Any]:
    ensure_csv_files()
    return {
        "datasets": {
            entity_set: {
                "service": ENTITY_SERVICE[entity_set],
                "csv": f"/csv/{filename}",
                "api": f"/sap/opu/odata/sap/{ENTITY_SERVICE[entity_set]}/{entity_set}",
                "rows": len(read_entity(entity_set)),
            }
            for entity_set, filename in ENTITY_FILES.items()
        }
    }


@app.get("/csv/{filename}")
def csv_file(filename: str):
    ensure_csv_files()
    allowed = set(ENTITY_FILES.values()) | {"manifest.json"}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="CSV file not found")
    path = DATA_DIR / filename
    media_type = "application/json" if filename.endswith(".json") else "text/csv"
    return FileResponse(path, media_type=media_type, filename=filename)


@app.get("/sap/opu/odata/sap/{service}/{entity_set}")
def entity_collection(service: str, entity_set: str, request: Request) -> dict[str, Any]:
    single_product = re.fullmatch(r"A_ProductStdCostEstmt\('([^']+)'\)", entity_set)
    if service == "API_PRODUCT_COST_SRV" and single_product:
        return _product_standard_cost_payload(single_product.group(1))
    _validate_entity(service, entity_set)
    rows = read_entity(entity_set)
    filtered = apply_odata(dict(request.query_params), rows)
    return odata_envelope(filtered)


@app.get("/sap/opu/odata/sap/API_PRODUCT_COST_SRV/A_ProductStdCostEstmt('{product}')")
def product_standard_cost(product: str) -> dict[str, Any]:
    return _product_standard_cost_payload(product)


def _product_standard_cost_payload(product: str) -> dict[str, Any]:
    rows = read_entity("A_ProductStdCostEstmt")
    for row in rows:
        if row.get("Product") == product:
            return {"d": row}
    raise HTTPException(status_code=404, detail="Product not found")


def _validate_entity(service: str, entity_set: str) -> None:
    if entity_set not in ENTITY_FILES:
        raise HTTPException(status_code=404, detail=f"Unknown entity set: {entity_set}")
    expected_service = ENTITY_SERVICE[entity_set]
    if expected_service != service:
        raise HTTPException(status_code=404, detail=f"{entity_set} belongs to {expected_service}, not {service}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the CSV-backed SAP API simulator.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4000)
    args = parser.parse_args()

    ensure_csv_files(Path(DATA_DIR))
    uvicorn.run("sap_api_simulator.app:app", host=args.host, port=args.port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
