// Mock Sales Pricing Condition Records
// Mirrors SAP SD pricing procedure output as exposed via API_SLSPRICING_SRV / A_PricingConditionRecord
// Two channel records per material (Domestic / Export) to allow price-mix variance analysis

const pricing = [
  { Product: "FG-AMM-FO",  SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 34500, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-AMM-FO",  SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 37800, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-AMM-NG",  SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 27500, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-AMM-NG",  SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 29900, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-UREA",    SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 21500, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-UREA",    SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 23200, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-WNA",     SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 15200, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-WNA",     SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 16100, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-CNA",     SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 19800, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-CNA",     SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 20900, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-ANP",     SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 24000, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-ANP",     SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 25600, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-AA",      SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 39500, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-AA",      SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 42300, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-EA",      SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 43000, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-EA",      SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 45800, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-FA",      SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 33500, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-FA",      SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 35700, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-MEOH",    SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 26800, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-MEOH",    SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 28500, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-TDI-BHR", SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 92000, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-TDI-BHR", SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 97500, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-ANI",     SalesOrg: "1000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 55500, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-ANI",     SalesOrg: "1000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 58900, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },

  { Product: "FG-TDI-DHJ", SalesOrg: "2000", DistrChannel: "10", Channel: "Domestic", ConditionType: "PR00", Amount: 90500, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
  { Product: "FG-TDI-DHJ", SalesOrg: "2000", DistrChannel: "20", Channel: "Export",   ConditionType: "PR00", Amount: 96200, currency: "INR", ValidFrom: "2026-04-01", ValidTo: "2026-09-30" },
];

module.exports = pricing;
