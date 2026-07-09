# CSV-backed SAP API Simulator

This is a separate, narrow simulator for SAP API testing. It does not start the main portal and it does not require Node.js.

## CSV-only version

```powershell
.\runtime\python\python.exe .\sap_api_simulator\create_csv.py
```

The command writes CSV files and `manifest.json` to:

```text
sap_api_simulator\csv
```

## API version for Postman

```powershell
.\runtime\python\python.exe -m sap_api_simulator.app --port 4000
```

Open Postman against:

```text
http://127.0.0.1:4000
```

Import `postman_collection.json` from this folder to get ready-made requests.

## Supported endpoints

- `GET /`
- `GET /health`
- `GET /datasets`
- `GET /csv/{filename}`
- `GET /sap/opu/odata/sap/API_PRODUCT_COST_SRV/A_ProductStdCostEstmt`
- `GET /sap/opu/odata/sap/API_PRODUCT_COST_SRV/A_ProductStdCostEstmt('FG-UREA')`
- `GET /sap/opu/odata/sap/API_PRODUCT_COST_SRV/A_CostCompItmCostEstmt`
- `GET /sap/opu/odata/sap/API_SLSPRICING_SRV/A_PricingConditionRecord`
- `GET /sap/opu/odata/sap/ZGNFC_CONTRIB_MARGIN_SRV/A_ContributionMargin`
- `GET /sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV/A_ProductionOrder`
- `GET /sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV/A_ProdOrderConfirmedYield`
- `GET /sap/opu/odata/sap/ZGNFC_PROD_VARIANCE_SRV/A_ProductionVariance`
- `GET /sap/opu/odata/sap/API_EQUIPMENT_SRV/A_Equipment`
- `GET /sap/opu/odata/sap/API_MAINTNOTIFICATION_SRV/A_MaintenanceNotification`
- `GET /sap/opu/odata/sap/API_MAINTENANCEORDER_SRV/A_MaintenanceOrder`
- `GET /sap/opu/odata/sap/ZGNFC_EQUIP_RELIABILITY_SRV/A_EquipmentReliability`

List endpoints support:

- `$filter=Field eq 'value'`
- `$top=N`
- `$skip=N`
- `simulate_error=true`
- `simulate_latency=<ms>`

Example:

```text
http://127.0.0.1:4000/sap/opu/odata/sap/ZGNFC_CONTRIB_MARGIN_SRV/A_ContributionMargin?$filter=Product eq 'FG-UREA'
```

