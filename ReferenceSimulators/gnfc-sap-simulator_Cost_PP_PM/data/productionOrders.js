// Mock Production Order data (mirrors SAP PP API_PRODUCTION_ORDER_2_SRV / A_ProductionOrder)
// Two monthly orders per product (Apr & May 2026) to allow trend + variance testing.
// MonthlyRatedCapacity is carried on the order for straightforward capacity-utilization calc.

const productionOrders = [
  // Product, Plant, MonthlyRatedCapacity, [ {Period, Planned, Actual, Scrap} ]
  { Product: "FG-AMM-FO",  Plant: "1001-BHR", MonthlyRatedCapacity: 45000, orders: [
      { Period: "2026-04", Planned: 44000, Actual: 42350, Scrap: 120 },
      { Period: "2026-05", Planned: 45000, Actual: 43980, Scrap: 95 } ] },
  { Product: "FG-AMM-NG",  Plant: "1001-BHR", MonthlyRatedCapacity: 40000, orders: [
      { Period: "2026-04", Planned: 39000, Actual: 40100, Scrap: 60 },
      { Period: "2026-05", Planned: 40000, Actual: 39250, Scrap: 80 } ] },
  { Product: "FG-UREA",    Plant: "1001-BHR", MonthlyRatedCapacity: 60000, orders: [
      { Period: "2026-04", Planned: 58000, Actual: 55600, Scrap: 210 },
      { Period: "2026-05", Planned: 60000, Actual: 59100, Scrap: 150 } ] },
  { Product: "FG-WNA",     Plant: "1001-BHR", MonthlyRatedCapacity: 20000, orders: [
      { Period: "2026-04", Planned: 19500, Actual: 19800, Scrap: 40 },
      { Period: "2026-05", Planned: 20000, Actual: 18650, Scrap: 55 } ] },
  { Product: "FG-CNA",     Plant: "1001-BHR", MonthlyRatedCapacity: 15000, orders: [
      { Period: "2026-04", Planned: 14500, Actual: 14100, Scrap: 30 },
      { Period: "2026-05", Planned: 15000, Actual: 14900, Scrap: 25 } ] },
  { Product: "FG-ANP",     Plant: "1001-BHR", MonthlyRatedCapacity: 18000, orders: [
      { Period: "2026-04", Planned: 17500, Actual: 16200, Scrap: 70 },
      { Period: "2026-05", Planned: 18000, Actual: 17750, Scrap: 45 } ] },
  { Product: "FG-AA",      Plant: "1001-BHR", MonthlyRatedCapacity: 12000, orders: [
      { Period: "2026-04", Planned: 11500, Actual: 11900, Scrap: 20 },
      { Period: "2026-05", Planned: 12000, Actual: 11100, Scrap: 35 } ] },
  { Product: "FG-EA",      Plant: "1001-BHR", MonthlyRatedCapacity: 8000,  orders: [
      { Period: "2026-04", Planned: 7800,  Actual: 7450,  Scrap: 25 },
      { Period: "2026-05", Planned: 8000,  Actual: 7920,  Scrap: 18 } ] },
  { Product: "FG-FA",      Plant: "1001-BHR", MonthlyRatedCapacity: 6000,  orders: [
      { Period: "2026-04", Planned: 5800,  Actual: 5650,  Scrap: 15 },
      { Period: "2026-05", Planned: 6000,  Actual: 5980,  Scrap: 10 } ] },
  { Product: "FG-MEOH",    Plant: "1001-BHR", MonthlyRatedCapacity: 25000, orders: [
      { Period: "2026-04", Planned: 24000, Actual: 22800, Scrap: 90 },
      { Period: "2026-05", Planned: 25000, Actual: 24650, Scrap: 60 } ] },
  { Product: "FG-TDI-BHR", Plant: "1001-BHR", MonthlyRatedCapacity: 5000,  orders: [
      { Period: "2026-04", Planned: 4800,  Actual: 4300,  Scrap: 40 },
      { Period: "2026-05", Planned: 5000,  Actual: 4850,  Scrap: 22 } ] },
  { Product: "FG-ANI",     Plant: "1001-BHR", MonthlyRatedCapacity: 9000,  orders: [
      { Period: "2026-04", Planned: 8700,  Actual: 8550,  Scrap: 18 },
      { Period: "2026-05", Planned: 9000,  Actual: 8100,  Scrap: 33 } ] },
  { Product: "FG-TDI-DHJ", Plant: "2001-DHJ", MonthlyRatedCapacity: 6000,  orders: [
      { Period: "2026-04", Planned: 5700,  Actual: 5900,  Scrap: 15 },
      { Period: "2026-05", Planned: 6000,  Actual: 5250,  Scrap: 48 } ] },
];

module.exports = productionOrders;
