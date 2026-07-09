from __future__ import annotations

from typing import Any

from app.source_simulators.base import SourceSimulator, apply_simple_query


PRODUCTION_ORDER_ROWS: list[dict[str, Any]] = []

_PRODUCTION_ORDER_SOURCE = [
    ("FG-AMM-FO", "1001-BHR", 45000, [("2026-04", 44000, 42350, 120), ("2026-05", 45000, 43980, 95)]),
    ("FG-AMM-NG", "1001-BHR", 40000, [("2026-04", 39000, 40100, 60), ("2026-05", 40000, 39250, 80)]),
    ("FG-UREA", "1001-BHR", 60000, [("2026-04", 58000, 55600, 210), ("2026-05", 60000, 59100, 150)]),
    ("FG-WNA", "1001-BHR", 20000, [("2026-04", 19500, 19800, 40), ("2026-05", 20000, 18650, 55)]),
    ("FG-CNA", "1001-BHR", 15000, [("2026-04", 14500, 14100, 30), ("2026-05", 15000, 14900, 25)]),
    ("FG-ANP", "1001-BHR", 18000, [("2026-04", 17500, 16200, 70), ("2026-05", 18000, 17750, 45)]),
    ("FG-AA", "1001-BHR", 12000, [("2026-04", 11500, 11900, 20), ("2026-05", 12000, 11100, 35)]),
    ("FG-EA", "1001-BHR", 8000, [("2026-04", 7800, 7450, 25), ("2026-05", 8000, 7920, 18)]),
    ("FG-FA", "1001-BHR", 6000, [("2026-04", 5800, 5650, 15), ("2026-05", 6000, 5980, 10)]),
    ("FG-MEOH", "1001-BHR", 25000, [("2026-04", 24000, 22800, 90), ("2026-05", 25000, 24650, 60)]),
    ("FG-TDI-BHR", "1001-BHR", 5000, [("2026-04", 4800, 4300, 40), ("2026-05", 5000, 4850, 22)]),
    ("FG-ANI", "1001-BHR", 9000, [("2026-04", 8700, 8550, 18), ("2026-05", 9000, 8100, 33)]),
    ("FG-TDI-DHJ", "2001-DHJ", 6000, [("2026-04", 5700, 5900, 15), ("2026-05", 6000, 5250, 48)]),
]

for product, plant, capacity, orders in _PRODUCTION_ORDER_SOURCE:
    for period, planned, actual, scrap in orders:
        PRODUCTION_ORDER_ROWS.append(
            {
                "OrderID": f"PO-{product}-{period}",
                "Product": product,
                "Plant": plant,
                "Period": period,
                "UnitOfMeasure": "TO",
                "MonthlyRatedCapacity": capacity,
                "PlannedOrderQuantity": planned,
                "ConfirmedYieldQuantity": actual,
                "ScrapQuantity": scrap,
                "OrderStatus": "TECO",
            }
        )

_STANDARD_COST = {
    "FG-AMM-FO": (18500, 4200),
    "FG-AMM-NG": (16200, 3600),
    "FG-UREA": (14500, 2900),
    "FG-WNA": (6800, 1900),
    "FG-CNA": (7600, 2200),
    "FG-ANP": (12800, 2500),
    "FG-AA": (38500, 6400),
    "FG-EA": (43500, 7100),
    "FG-FA": (31500, 5200),
    "FG-MEOH": (21400, 4800),
    "FG-TDI-BHR": (104000, 16200),
    "FG-ANI": (72500, 11900),
    "FG-TDI-DHJ": (101500, 15800),
}

_VARIANCE_BY_PERIOD = {
    "FG-AMM-FO": {"2026-04": (0.04, 0.06), "2026-05": (0.01, 0.02)},
    "FG-AMM-NG": {"2026-04": (-0.02, -0.01), "2026-05": (0.03, 0.04)},
    "FG-UREA": {"2026-04": (0.06, 0.08), "2026-05": (0.01, 0.01)},
    "FG-WNA": {"2026-04": (-0.01, 0.02), "2026-05": (0.05, 0.07)},
    "FG-CNA": {"2026-04": (0.02, 0.01), "2026-05": (0.00, 0.01)},
    "FG-ANP": {"2026-04": (0.07, 0.05), "2026-05": (0.01, 0.02)},
    "FG-AA": {"2026-04": (-0.02, -0.03), "2026-05": (0.04, 0.03)},
    "FG-EA": {"2026-04": (0.03, 0.02), "2026-05": (0.00, 0.01)},
    "FG-FA": {"2026-04": (0.01, 0.02), "2026-05": (0.00, 0.00)},
    "FG-MEOH": {"2026-04": (0.05, 0.06), "2026-05": (0.02, 0.02)},
    "FG-TDI-BHR": {"2026-04": (0.08, 0.05), "2026-05": (0.02, 0.03)},
    "FG-ANI": {"2026-04": (0.02, 0.01), "2026-05": (0.04, 0.03)},
    "FG-TDI-DHJ": {"2026-04": (-0.01, 0.01), "2026-05": (0.06, 0.04)},
}


def _build_consumption_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for product, periods in _VARIANCE_BY_PERIOD.items():
        standard_rm, standard_utilities = _STANDARD_COST[product]
        for period, variance in periods.items():
            rm_variance, utilities_variance = variance
            rows.append(
                {
                    "OrderID": f"PO-{product}-{period}",
                    "Product": product,
                    "Period": period,
                    "StandardRawMaterialPerUnit": standard_rm,
                    "ActualRawMaterialPerUnit": round(standard_rm * (1 + rm_variance)),
                    "StandardUtilitiesPerUnit": standard_utilities,
                    "ActualUtilitiesPerUnit": round(standard_utilities * (1 + utilities_variance)),
                    "Currency": "INR",
                }
            )
    return rows


CONFIRMED_YIELD_ROWS = _build_consumption_rows()


def _build_variance_rows() -> list[dict[str, Any]]:
    consumption_by_key = {(row["Product"], row["Period"]): row for row in CONFIRMED_YIELD_ROWS}
    rows: list[dict[str, Any]] = []
    for order in PRODUCTION_ORDER_ROWS:
        consumption = consumption_by_key.get((order["Product"], order["Period"]))
        rm_variance = None
        utilities_variance = None
        total_efficiency = None
        if consumption:
            rm_variance = consumption["StandardRawMaterialPerUnit"] - consumption["ActualRawMaterialPerUnit"]
            utilities_variance = consumption["StandardUtilitiesPerUnit"] - consumption["ActualUtilitiesPerUnit"]
            total_efficiency = rm_variance + utilities_variance
        planned = order["PlannedOrderQuantity"]
        actual = order["ConfirmedYieldQuantity"]
        rows.append(
            {
                "OrderID": order["OrderID"],
                "Product": order["Product"],
                "Plant": order["Plant"],
                "Period": order["Period"],
                "PlannedOrderQuantity": planned,
                "ConfirmedYieldQuantity": actual,
                "ScrapQuantity": order["ScrapQuantity"],
                "VolumeVarianceQty": actual - planned,
                "VolumeVariancePct": round(((actual - planned) / planned) * 100, 2),
                "MonthlyRatedCapacity": order["MonthlyRatedCapacity"],
                "CapacityUtilizationPct": round((actual / order["MonthlyRatedCapacity"]) * 100, 2),
                "RawMaterialEfficiencyVariancePerUnit": rm_variance,
                "UtilitiesEfficiencyVariancePerUnit": utilities_variance,
                "TotalEfficiencyVariancePerUnit": total_efficiency,
                "TotalEfficiencyVarianceValue": round(total_efficiency * actual) if total_efficiency is not None else None,
                "Currency": consumption["Currency"] if consumption else None,
            }
        )
    return rows


VARIANCE_ROWS = _build_variance_rows()


ENTITY_ROWS = {
    "A_ProductionOrder": PRODUCTION_ORDER_ROWS,
    "A_ProdOrderConfirmedYield": CONFIRMED_YIELD_ROWS,
    "A_ProductionVariance": VARIANCE_ROWS,
}

ODATA_ENTITY_PATHS = {
    "/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV/A_ProductionOrder": "A_ProductionOrder",
    "/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV/A_ProdOrderConfirmedYield": "A_ProdOrderConfirmedYield",
    "/sap/opu/odata/sap/ZGNFC_PROD_VARIANCE_SRV/A_ProductionVariance": "A_ProductionVariance",
}


class SapPpSourceSimulator(SourceSimulator):
    connector_id = "sap_pp"
    display_name = "SAP PP OData Simulator"
    description = "S/4HANA-style production order, confirmation, and variance data for PP integration tests."

    def spec(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "display_name": self.display_name,
            "description": self.description,
            "shape": "http_odata_v2",
            "query_options": ["$filter", "$top", "$skip", "simulate_error", "simulate_latency"],
            "entities": self.entities(),
        }

    def entities(self) -> list[dict[str, Any]]:
        return [
            {
                "entity": "A_ProductionOrder",
                "path": "/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV/A_ProductionOrder",
                "row_count": len(PRODUCTION_ORDER_ROWS),
                "description": "Planned and confirmed production order quantities.",
            },
            {
                "entity": "A_ProdOrderConfirmedYield",
                "path": "/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV/A_ProdOrderConfirmedYield",
                "row_count": len(CONFIRMED_YIELD_ROWS),
                "description": "Order confirmation consumption values used for efficiency variance.",
            },
            {
                "entity": "A_ProductionVariance",
                "path": "/sap/opu/odata/sap/ZGNFC_PROD_VARIANCE_SRV/A_ProductionVariance",
                "row_count": len(VARIANCE_ROWS),
                "description": "Derived production volume, capacity, and consumption variance.",
            },
        ]

    def query(
        self,
        entity: str,
        filter_text: str = "",
        top: int | None = None,
        skip: int = 0,
        watermark: str | None = None,
    ) -> list[dict[str, Any]]:
        if entity not in ENTITY_ROWS:
            raise KeyError(f"Unknown SAP PP entity: {entity}")
        if watermark:
            raise ValueError("SAP PP OData simulator does not support watermark polling; use $filter/$top/$skip.")
        return apply_simple_query(ENTITY_ROWS[entity], filter_text=filter_text, top=top, skip=skip)
