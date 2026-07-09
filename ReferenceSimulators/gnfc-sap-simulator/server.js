/**
 * GNFC SAP Simulator - Costing & Pricing
 * -----------------------------------------------------------------------
 * Mimics the shape of real SAP S/4HANA OData services so that the DMP /
 * Historian integration and contribution-margin analytics can be built and
 * tested BEFORE a live SAP connection is available. Swap the base URL for
 * the real SAP Gateway endpoint later; the JSON contract is designed to
 * look the same.
 *
 * Simulated services (mirroring real SAP API names):
 *   - API_PRODUCT_COST_SRV   -> Standard Cost Estimate (CO-PC)
 *   - API_SLSPRICING_SRV     -> Sales Pricing Condition Records (SD)
 *   - ZGNFC_CONTRIB_MARGIN_SRV -> Custom derived contribution-margin view
 *
 * Supports a subset of OData v2 query options: $filter (eq), $top, $skip,
 * plus two testing hooks: ?simulate_latency=ms and ?simulate_error=true
 * to exercise the DMP's data-freshness / error-handling logic.
 */

const express = require("express");
const materials = require("./data/materials");
const costEstimates = require("./data/standardCost");
const pricing = require("./data/pricing");

const app = express();
const PORT = process.env.PORT || 4000;

// ---------------------------------------------------------------------
// Test hooks: artificial latency / error injection (query params)
// ---------------------------------------------------------------------
app.use((req, res, next) => {
  if (req.query.simulate_error === "true") {
    return res.status(503).json({
      error: {
        code: "SAP_SERVICE_UNAVAILABLE",
        message: "Simulated SAP backend outage (RFC_COMMUNICATION_FAILURE)",
      },
    });
  }
  const delay = parseInt(req.query.simulate_latency, 10);
  if (delay > 0) {
    setTimeout(next, Math.min(delay, 10000));
  } else {
    next();
  }
});

// Helper: OData-style envelope
function odataEnvelope(results) {
  return { d: { results } };
}

// Helper: apply simple $filter (only "Field eq 'value'" supported),
// $top, $skip on an array of plain objects
function applyOData(req, rows) {
  let out = rows;
  const filter = req.query.$filter;
  if (filter) {
    const m = filter.match(/(\w+)\s+eq\s+'?([^']+)'?/i);
    if (m) {
      const [, field, value] = m;
      out = out.filter((r) => String(r[field]) === value);
    }
  }
  const skip = parseInt(req.query.$skip, 10) || 0;
  const top = parseInt(req.query.$top, 10) || out.length;
  return out.slice(skip, skip + top);
}

// ---------------------------------------------------------------------
// Service catalog (like the SAP Gateway root service document)
// ---------------------------------------------------------------------
app.get("/", (req, res) => {
  res.json({
    service: "GNFC SAP Simulator (Costing & Pricing)",
    status: "running",
    entitySets: [
      "/sap/opu/odata/sap/API_PRODUCT_COST_SRV/A_ProductStdCostEstmt",
      "/sap/opu/odata/sap/API_PRODUCT_COST_SRV/A_CostCompItmCostEstmt",
      "/sap/opu/odata/sap/API_SLSPRICING_SRV/A_PricingConditionRecord",
      "/sap/opu/odata/sap/ZGNFC_CONTRIB_MARGIN_SRV/A_ContributionMargin",
    ],
    testHooks: {
      simulate_error: "?simulate_error=true -> returns 503",
      simulate_latency: "?simulate_latency=<ms> -> delays response",
    },
  });
});

// ---------------------------------------------------------------------
// API_PRODUCT_COST_SRV - A_ProductStdCostEstmt (header)
// ---------------------------------------------------------------------
app.get("/sap/opu/odata/sap/API_PRODUCT_COST_SRV/A_ProductStdCostEstmt", (req, res) => {
  const rows = materials.map((m) => {
    const ce = costEstimates[m.Product];
    const total = Object.values(ce.components).reduce((a, b) => a + b, 0);
    return {
      Product: m.Product,
      ProductDescription: m.ProductDescription,
      Plant: m.Plant,
      CostingVariant: ce.CostingVariant,
      CostEstimateDate: ce.CostEstDate,
      ValidToDate: ce.ValidTo,
      Currency: ce.currency,
      StandardCostPerUnit: total,
      BaseUnit: m.BaseUnit,
    };
  });
  res.json(odataEnvelope(applyOData(req, rows)));
});

app.get(/^\/sap\/opu\/odata\/sap\/API_PRODUCT_COST_SRV\/A_ProductStdCostEstmt\('([^']+)'\)$/, (req, res) => {
  const id = req.params[0];
  const m = materials.find((x) => x.Product === id);
  if (!m) return res.status(404).json({ error: { message: "Product not found" } });
  const ce = costEstimates[m.Product];
  const total = Object.values(ce.components).reduce((a, b) => a + b, 0);
  res.json({
    d: {
      Product: m.Product,
      ProductDescription: m.ProductDescription,
      Plant: m.Plant,
      CostingVariant: ce.CostingVariant,
      CostEstimateDate: ce.CostEstDate,
      ValidToDate: ce.ValidTo,
      Currency: ce.currency,
      StandardCostPerUnit: total,
      BaseUnit: m.BaseUnit,
    },
  });
});

// ---------------------------------------------------------------------
// API_PRODUCT_COST_SRV - A_CostCompItmCostEstmt (cost component breakdown)
// ---------------------------------------------------------------------
app.get("/sap/opu/odata/sap/API_PRODUCT_COST_SRV/A_CostCompItmCostEstmt", (req, res) => {
  const rows = [];
  materials.forEach((m) => {
    const ce = costEstimates[m.Product];
    Object.entries(ce.components).forEach(([component, amount]) => {
      rows.push({
        Product: m.Product,
        Plant: m.Plant,
        CostComponent: component,
        Amount: amount,
        Currency: ce.currency,
      });
    });
  });
  res.json(odataEnvelope(applyOData(req, rows)));
});

// ---------------------------------------------------------------------
// API_SLSPRICING_SRV - A_PricingConditionRecord
// ---------------------------------------------------------------------
app.get("/sap/opu/odata/sap/API_SLSPRICING_SRV/A_PricingConditionRecord", (req, res) => {
  res.json(odataEnvelope(applyOData(req, pricing)));
});

// ---------------------------------------------------------------------
// ZGNFC_CONTRIB_MARGIN_SRV - A_ContributionMargin (derived / calculated)
// Combines standard cost (variable portion) + sales price to give
// unit contribution margin per material per channel.
// ---------------------------------------------------------------------
app.get("/sap/opu/odata/sap/ZGNFC_CONTRIB_MARGIN_SRV/A_ContributionMargin", (req, res) => {
  const rows = [];
  pricing.forEach((p) => {
    const ce = costEstimates[p.Product];
    const m = materials.find((x) => x.Product === p.Product);
    const variableCost = ce.components.RawMaterial + ce.components.Utilities + ce.components.VariableOverhead;
    const fixedCost = ce.components.Labor + ce.components.FixedOverhead;
    const totalStdCost = variableCost + fixedCost;
    rows.push({
      Product: p.Product,
      ProductDescription: m.ProductDescription,
      Plant: m.Plant,
      SalesOrg: p.SalesOrg,
      Channel: p.Channel,
      SellingPricePerUnit: p.Amount,
      VariableCostPerUnit: variableCost,
      FixedCostPerUnit: fixedCost,
      StandardCostPerUnit: totalStdCost,
      UnitContributionMargin: p.Amount - variableCost,
      UnitContributionMarginPct: Number((((p.Amount - variableCost) / p.Amount) * 100).toFixed(2)),
      NetUnitMargin: p.Amount - totalStdCost,
      Currency: p.currency,
      ValidFrom: p.ValidFrom,
      ValidTo: p.ValidTo,
    });
  });
  res.json(odataEnvelope(applyOData(req, rows)));
});

app.use((req, res) => {
  res.status(404).json({ error: { message: `Unknown endpoint: ${req.path}` } });
});

app.listen(PORT, () => {
  console.log(`GNFC SAP Simulator listening on http://localhost:${PORT}`);
  console.log(`Service catalog: http://localhost:${PORT}/`);
});
