# GNFC SAP Simulator — Costing, Pricing, PP & PM

A lightweight REST API that mimics the **shape of real SAP S/4HANA OData services**
so the Historian/DMP analytics use cases (contribution margin, capacity
utilization, equipment health) can be designed, built and tested now, without
a live SAP connection. When SAP connectivity becomes available, point the DMP
connector at the real Gateway URLs — the JSON contract here is modeled on the
actual API structures, so the switch should be mostly a base-URL change.

Covers four SAP areas:
- **CO/SD (Costing & Pricing)** — standard cost estimates, sales pricing, derived contribution margin
- **PP (Production Planning)** — production orders (planned vs actual output), order confirmations (actual RM/utility consumption), derived production variance (volume, capacity utilization, efficiency)
- **PM (Plant Maintenance)** — equipment master (linked to the Bharuch/Dahej asset hierarchy), breakdown/preventive notifications, maintenance work orders, derived equipment reliability (MTBF, MTTR, availability)

## Run it

```bash
npm install
node server.js
# -> GNFC SAP Simulator listening on http://localhost:4000
```

## Products in scope

13 GNFC finished products across Bharuch & Dahej (Ammonia x2 routes, Urea,
Weak/Conc. Nitric Acid, ANP/AN Melt, Acetic Acid, Ethyl Acetate, Formic Acid,
Methanol, TDI x2 sites, Aniline) — matching Annexure-1 of the SoW.

## Endpoints

| Endpoint | Mirrors real SAP service | Purpose |
|---|---|---|
| `GET /` | SAP Gateway service catalog | Lists available entity sets |
| `GET /sap/opu/odata/sap/API_PRODUCT_COST_SRV/A_ProductStdCostEstmt` | `API_PRODUCT_COST_SRV` (CO-PC) | Standard cost per product (header) |
| `GET /sap/opu/odata/sap/API_PRODUCT_COST_SRV/A_ProductStdCostEstmt('FG-UREA')` | same | Single product's standard cost |
| `GET /sap/opu/odata/sap/API_PRODUCT_COST_SRV/A_CostCompItmCostEstmt` | same | Cost component breakdown (raw material, utilities, labor, var/fixed OH) |
| `GET /sap/opu/odata/sap/API_SLSPRICING_SRV/A_PricingConditionRecord` | `API_SLSPRICING_SRV` (SD) | Sales price per product, per channel (Domestic/Export) |
| `GET /sap/opu/odata/sap/ZGNFC_CONTRIB_MARGIN_SRV/A_ContributionMargin` | Custom/derived | Selling price − variable cost = unit contribution margin, per product per channel |
| `GET /sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV/A_ProductionOrder` | `API_PRODUCTION_ORDER_2_SRV` (PP) | Planned vs actual (confirmed yield) output per product per month |
| `GET /sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV/A_ProdOrderConfirmedYield` | Order confirmation (CO11N) | Actual raw material & utilities cost per unit vs standard |
| `GET /sap/opu/odata/sap/ZGNFC_PROD_VARIANCE_SRV/A_ProductionVariance` | Custom/derived | Volume variance, capacity utilization %, and RM/utilities efficiency variance per order |
| `GET /sap/opu/odata/sap/API_EQUIPMENT_SRV/A_Equipment` | `API_EQUIPMENT_SRV` (PM) | Equipment master, linked to the Plant > Unit > Equipment asset hierarchy |
| `GET /sap/opu/odata/sap/API_MAINTNOTIFICATION_SRV/A_MaintenanceNotification` | `API_MAINTNOTIFICATION_SRV` (PM) | Breakdown (M1) and preventive (M2) notifications, with downtime timestamps |
| `GET /sap/opu/odata/sap/API_MAINTENANCEORDER_SRV/A_MaintenanceOrder` | `API_MAINTENANCEORDER` (PM) | Maintenance work orders with planned vs actual cost |
| `GET /sap/opu/odata/sap/ZGNFC_EQUIP_RELIABILITY_SRV/A_EquipmentReliability` | Custom/derived | MTBF, MTTR, availability %, and maintenance cost variance per equipment (Q2-2026 window) |

All list endpoints support a small OData v2 subset:
- `$filter=Field eq 'value'` (single equality filter)
- `$top=N`, `$skip=N`

Example:
```
GET /sap/opu/odata/sap/ZGNFC_CONTRIB_MARGIN_SRV/A_ContributionMargin?$filter=Product eq 'FG-UREA'
```

## Testing hooks (for DMP resilience/SLA testing)

- `?simulate_error=true` → returns `503 SAP_SERVICE_UNAVAILABLE`, useful for
  testing the DMP's error handling and data-freshness alerting.
- `?simulate_latency=<ms>` → delays the response by the given milliseconds,
  useful for testing timeout handling and the data-freshness SLA logic
  described in the SoW (§4.7).

## How PP & PM map to the original analytics use cases

- **Contribution margin — volume & efficiency variance**: join
  `A_ProductionVariance` (this file) to `A_ContributionMargin` (costing/pricing)
  on `Product` to get the full price + volume + efficiency + mix picture.
- **Production capacity utilization**: `A_ProductionVariance.CapacityUtilizationPct`,
  computed directly from `A_ProductionOrder`.
- **Plant/equipment stability & recurring bottlenecks**: `A_MaintenanceNotification`
  gives raw breakdown events per equipment; `A_EquipmentReliability` aggregates
  them into MTBF/MTTR/availability trend metrics.
- **Fuel & energy balance vs norms**: `A_ProdOrderConfirmedYield`'s
  `Standard/ActualUtilitiesPerUnit` fields are the norm-vs-actual comparison
  for specific energy/steam consumption per tonne — the same comparison the
  SoW asks for, just sourced from PP confirmations here instead of the
  Historian directly (in the real system both OT tags and SAP PP actuals
  would typically be reconciled).

## How this maps to the contribution-margin use case

`Unit Contribution Margin = Selling Price − Variable Cost`
(Variable cost = Raw Material + Utilities + Variable Overhead; Labor + Fixed
Overhead are excluded as fixed costs.)

The `/A_ContributionMargin` endpoint pre-computes this per product per sales
channel, which is enough to build:
- **Price variance**: compare `SellingPricePerUnit` across periods/channels
- **Mix variance**: compare `Channel` (Domestic vs Export) contribution %
- **Volume/efficiency variance**: requires actual production & consumption
  quantities from the Historian (not in this simulator) — join on `Product`
  to combine with cost/price data here.

## Data realism notes

- Figures are illustrative placeholders (INR per tonne), not real GNFC costs —
  built only to exercise data shapes and calculation logic.
- Cost/price validity window: 2026-04-01 to 2026-09-30 (mimics an H1
  costing/pricing cycle) to test date-based validity handling.
- Two sales channels (Domestic/Export) per product enable mix-variance testing.

## Swapping in real SAP later

1. Real SAP exposes these same entity sets via SAP Gateway (OData) once
   `API_PRODUCT_COST_SRV` and `API_SLSPRICING_SRV` are activated in
   transaction `/IWFND/MAINT_SERVICE`.
2. Point the DMP connector's base URL to the SAP Gateway host instead of
   `localhost:4000` and add SAP Basic/OAuth auth headers (this simulator has
   no auth by default, to keep local testing simple).
3. The custom `ZGNFC_CONTRIB_MARGIN_SRV` calculation would move into the DMP's
   calculation/analytics layer (as described in the Solution Document's
   "Enrich Data" engine) rather than staying a raw SAP service, since it's a
   derived KPI, not native SAP data.
