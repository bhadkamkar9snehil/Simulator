// Mock Production Order Confirmation - actual consumption data
// Mirrors SAP PP order confirmation (CO11N) as exposed via
// API_PROD_ORDER_CONFIRMATION_2_SRV. Captures ACTUAL raw material and
// utilities cost per unit of output, to be compared against the STANDARD
// cost estimate (data/standardCost.js) for efficiency-variance analysis.
//
// varianceFactor > 0 means actual cost per unit was HIGHER than standard
// (unfavorable / less efficient); < 0 means favorable (more efficient).

const costEstimates = require("./standardCost");

const varianceByPeriod = {
  "FG-AMM-FO":  { "2026-04": { rm: 0.04,  ut: 0.06 },  "2026-05": { rm: 0.01,  ut: 0.02 } },
  "FG-AMM-NG":  { "2026-04": { rm: -0.02, ut: -0.01 }, "2026-05": { rm: 0.03,  ut: 0.04 } },
  "FG-UREA":    { "2026-04": { rm: 0.06,  ut: 0.08 },  "2026-05": { rm: 0.01,  ut: 0.01 } },
  "FG-WNA":     { "2026-04": { rm: -0.01, ut: 0.02 },  "2026-05": { rm: 0.05,  ut: 0.07 } },
  "FG-CNA":     { "2026-04": { rm: 0.02,  ut: 0.01 },  "2026-05": { rm: 0.00,  ut: 0.01 } },
  "FG-ANP":     { "2026-04": { rm: 0.07,  ut: 0.05 },  "2026-05": { rm: 0.01,  ut: 0.02 } },
  "FG-AA":      { "2026-04": { rm: -0.02, ut: -0.03 }, "2026-05": { rm: 0.04,  ut: 0.03 } },
  "FG-EA":      { "2026-04": { rm: 0.03,  ut: 0.02 },  "2026-05": { rm: 0.00,  ut: 0.01 } },
  "FG-FA":      { "2026-04": { rm: 0.01,  ut: 0.02 },  "2026-05": { rm: 0.00,  ut: 0.00 } },
  "FG-MEOH":    { "2026-04": { rm: 0.05,  ut: 0.06 },  "2026-05": { rm: 0.02,  ut: 0.02 } },
  "FG-TDI-BHR": { "2026-04": { rm: 0.08,  ut: 0.05 },  "2026-05": { rm: 0.02,  ut: 0.03 } },
  "FG-ANI":     { "2026-04": { rm: 0.02,  ut: 0.01 },  "2026-05": { rm: 0.04,  ut: 0.03 } },
  "FG-TDI-DHJ": { "2026-04": { rm: -0.01, ut: 0.01 },  "2026-05": { rm: 0.06,  ut: 0.04 } },
};

function buildConsumption() {
  const rows = [];
  Object.entries(varianceByPeriod).forEach(([product, periods]) => {
    const ce = costEstimates[product];
    Object.entries(periods).forEach(([period, v]) => {
      const stdRM = ce.components.RawMaterial;
      const stdUT = ce.components.Utilities;
      rows.push({
        Product: product,
        Period: period,
        StandardRawMaterialPerUnit: stdRM,
        ActualRawMaterialPerUnit: Math.round(stdRM * (1 + v.rm)),
        StandardUtilitiesPerUnit: stdUT,
        ActualUtilitiesPerUnit: Math.round(stdUT * (1 + v.ut)),
        Currency: ce.currency,
      });
    });
  });
  return rows;
}

module.exports = buildConsumption();
