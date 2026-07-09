// Mock Standard Cost Estimate data
// Mirrors SAP API_PRODUCT_COST_SRV entities: A_ProductStdCostEstmt (header) + A_CostCompItmCostEstmt (components)
// Cost component structure follows a typical CO-PC costing sheet: Raw Material, Utilities/Energy, Labor, Variable OH, Fixed OH

const costEstimates = {
  "FG-AMM-FO":  { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 18000, Utilities: 9000, Labor: 800, VariableOverhead: 1200, FixedOverhead: 1500 } },
  "FG-AMM-NG":  { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 15000, Utilities: 6000, Labor: 700, VariableOverhead: 1000, FixedOverhead: 1300 } },
  "FG-UREA":    { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 12000, Utilities: 4500, Labor: 600, VariableOverhead: 900,  FixedOverhead: 1100 } },
  "FG-WNA":     { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 8000,  Utilities: 3000, Labor: 400, VariableOverhead: 600,  FixedOverhead: 700 } },
  "FG-CNA":     { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 11000, Utilities: 3800, Labor: 450, VariableOverhead: 650,  FixedOverhead: 750 } },
  "FG-ANP":     { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 13500, Utilities: 4200, Labor: 550, VariableOverhead: 800,  FixedOverhead: 950 } },
  "FG-AA":      { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 22000, Utilities: 7500, Labor: 900, VariableOverhead: 1300, FixedOverhead: 1600 } },
  "FG-EA":      { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 26000, Utilities: 6800, Labor: 850, VariableOverhead: 1250, FixedOverhead: 1500 } },
  "FG-FA":      { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 19000, Utilities: 6200, Labor: 700, VariableOverhead: 1000, FixedOverhead: 1200 } },
  "FG-MEOH":    { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 14500, Utilities: 5200, Labor: 600, VariableOverhead: 900,  FixedOverhead: 1050 } },
  "FG-TDI-BHR": { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 58000, Utilities: 12000, Labor: 1500, VariableOverhead: 2200, FixedOverhead: 2600 } },
  "FG-ANI":     { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 34000, Utilities: 8500, Labor: 950, VariableOverhead: 1400, FixedOverhead: 1650 } },
  "FG-TDI-DHJ": { CostingVariant: "PPC1", CostEstDate: "2026-04-01", ValidTo: "2026-09-30", currency: "INR",
                  components: { RawMaterial: 57000, Utilities: 11500, Labor: 1450, VariableOverhead: 2100, FixedOverhead: 2500 } },
};

module.exports = costEstimates;
