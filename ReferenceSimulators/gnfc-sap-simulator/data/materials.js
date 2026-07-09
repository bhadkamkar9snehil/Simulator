// Mock Material Master (mirrors fields returned by SAP API_MATERIAL_STOCK_SRV / MARA-MAKT)
// Scope: GNFC Bharuch & Dahej fertilizer + chemical products (per SoW Annexure-1)

const materials = [
  { Product: "FG-AMM-FO",  ProductDescription: "Ammonia (Fuel Oil Route)",        Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "FERT" },
  { Product: "FG-AMM-NG",  ProductDescription: "Ammonia (Natural Gas Route)",      Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "FERT" },
  { Product: "FG-UREA",    ProductDescription: "Urea (Prilled)",                   Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "FERT" },
  { Product: "FG-WNA",     ProductDescription: "Weak Nitric Acid",                 Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "CHEM" },
  { Product: "FG-CNA",     ProductDescription: "Concentrated Nitric Acid",         Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "CHEM" },
  { Product: "FG-ANP",     ProductDescription: "Ammonium Nitrophosphate / AN Melt",Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "FERT" },
  { Product: "FG-AA",      ProductDescription: "Acetic Acid",                      Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "CHEM" },
  { Product: "FG-EA",      ProductDescription: "Ethyl Acetate",                    Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "CHEM" },
  { Product: "FG-FA",      ProductDescription: "Formic Acid",                     Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "CHEM" },
  { Product: "FG-MEOH",    ProductDescription: "Methanol",                        Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "CHEM" },
  { Product: "FG-TDI-BHR", ProductDescription: "Toluene Di-Isocyanate (Bharuch)",  Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "CHEM" },
  { Product: "FG-ANI",     ProductDescription: "Aniline",                         Plant: "1001-BHR", BaseUnit: "TO", ProductGroup: "CHEM" },
  { Product: "FG-TDI-DHJ", ProductDescription: "Toluene Di-Isocyanate (Dahej)",    Plant: "2001-DHJ", BaseUnit: "TO", ProductGroup: "CHEM" },
];

module.exports = materials;
