# GNFC SAP Simulator — Costing & Pricing

A lightweight REST API that mimics the **shape of real SAP S/4HANA OData services**
so the Historian/DMP contribution-margin analytics can be designed, built and
tested now, without a live SAP connection. When SAP connectivity becomes
available, point the DMP's connector at the real Gateway URLs — the JSON
contract here is modeled on the actual API structures, so the switch should be
mostly a base-URL change.

Covers **costing & pricing only** (per scope agreed): standard cost estimates,
sales pricing conditions, and a derived contribution-margin view. Production
volumes, actuals, and mix quantities are expected to come from the
Historian/DMP itself, not from this simulator.

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
