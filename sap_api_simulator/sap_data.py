from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent / "csv"

MATERIALS = [
    {"Product": "FG-AMM-FO", "ProductDescription": "Ammonia (Fuel Oil Route)", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "FERT"},
    {"Product": "FG-AMM-NG", "ProductDescription": "Ammonia (Natural Gas Route)", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "FERT"},
    {"Product": "FG-UREA", "ProductDescription": "Urea (Prilled)", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "FERT"},
    {"Product": "FG-WNA", "ProductDescription": "Weak Nitric Acid", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "CHEM"},
    {"Product": "FG-CNA", "ProductDescription": "Concentrated Nitric Acid", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "CHEM"},
    {"Product": "FG-ANP", "ProductDescription": "Ammonium Nitrophosphate / AN Melt", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "FERT"},
    {"Product": "FG-AA", "ProductDescription": "Acetic Acid", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "CHEM"},
    {"Product": "FG-EA", "ProductDescription": "Ethyl Acetate", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "CHEM"},
    {"Product": "FG-FA", "ProductDescription": "Formic Acid", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "CHEM"},
    {"Product": "FG-MEOH", "ProductDescription": "Methanol", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "CHEM"},
    {"Product": "FG-TDI-BHR", "ProductDescription": "Toluene Di-Isocyanate (Bharuch)", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "CHEM"},
    {"Product": "FG-ANI", "ProductDescription": "Aniline", "Plant": "1001-BHR", "BaseUnit": "TO", "ProductGroup": "CHEM"},
    {"Product": "FG-TDI-DHJ", "ProductDescription": "Toluene Di-Isocyanate (Dahej)", "Plant": "2001-DHJ", "BaseUnit": "TO", "ProductGroup": "CHEM"},
]

COSTS = {
    "FG-AMM-FO": {"RawMaterial": 18000, "Utilities": 9000, "Labor": 800, "VariableOverhead": 1200, "FixedOverhead": 1500},
    "FG-AMM-NG": {"RawMaterial": 15000, "Utilities": 6000, "Labor": 700, "VariableOverhead": 1000, "FixedOverhead": 1300},
    "FG-UREA": {"RawMaterial": 12000, "Utilities": 4500, "Labor": 600, "VariableOverhead": 900, "FixedOverhead": 1100},
    "FG-WNA": {"RawMaterial": 8000, "Utilities": 3000, "Labor": 400, "VariableOverhead": 600, "FixedOverhead": 700},
    "FG-CNA": {"RawMaterial": 11000, "Utilities": 3800, "Labor": 450, "VariableOverhead": 650, "FixedOverhead": 750},
    "FG-ANP": {"RawMaterial": 13500, "Utilities": 4200, "Labor": 550, "VariableOverhead": 800, "FixedOverhead": 950},
    "FG-AA": {"RawMaterial": 22000, "Utilities": 7500, "Labor": 900, "VariableOverhead": 1300, "FixedOverhead": 1600},
    "FG-EA": {"RawMaterial": 26000, "Utilities": 6800, "Labor": 850, "VariableOverhead": 1250, "FixedOverhead": 1500},
    "FG-FA": {"RawMaterial": 19000, "Utilities": 6200, "Labor": 700, "VariableOverhead": 1000, "FixedOverhead": 1200},
    "FG-MEOH": {"RawMaterial": 14500, "Utilities": 5200, "Labor": 600, "VariableOverhead": 900, "FixedOverhead": 1050},
    "FG-TDI-BHR": {"RawMaterial": 58000, "Utilities": 12000, "Labor": 1500, "VariableOverhead": 2200, "FixedOverhead": 2600},
    "FG-ANI": {"RawMaterial": 34000, "Utilities": 8500, "Labor": 950, "VariableOverhead": 1400, "FixedOverhead": 1650},
    "FG-TDI-DHJ": {"RawMaterial": 57000, "Utilities": 11500, "Labor": 1450, "VariableOverhead": 2100, "FixedOverhead": 2500},
}

PRICE_BY_PRODUCT = {
    "FG-AMM-FO": (34500, 37800, "1000"),
    "FG-AMM-NG": (27500, 29900, "1000"),
    "FG-UREA": (21500, 23200, "1000"),
    "FG-WNA": (15200, 16100, "1000"),
    "FG-CNA": (19800, 20900, "1000"),
    "FG-ANP": (24000, 25600, "1000"),
    "FG-AA": (39500, 42300, "1000"),
    "FG-EA": (43000, 45800, "1000"),
    "FG-FA": (33500, 35700, "1000"),
    "FG-MEOH": (26800, 28500, "1000"),
    "FG-TDI-BHR": (92000, 97500, "1000"),
    "FG-ANI": (55500, 58900, "1000"),
    "FG-TDI-DHJ": (90500, 96200, "2000"),
}

PRODUCTION_PLAN = {
    "FG-AMM-FO": (45000, [( "2026-04", 44000, 42350, 120), ("2026-05", 45000, 43980, 95)]),
    "FG-AMM-NG": (40000, [("2026-04", 39000, 40100, 60), ("2026-05", 40000, 39250, 80)]),
    "FG-UREA": (60000, [("2026-04", 58000, 55600, 210), ("2026-05", 60000, 59100, 150)]),
    "FG-WNA": (20000, [("2026-04", 19500, 19800, 40), ("2026-05", 20000, 18650, 55)]),
    "FG-CNA": (15000, [("2026-04", 14500, 14100, 30), ("2026-05", 15000, 14900, 25)]),
    "FG-ANP": (18000, [("2026-04", 17500, 16200, 70), ("2026-05", 18000, 17750, 45)]),
    "FG-AA": (12000, [("2026-04", 11500, 11900, 20), ("2026-05", 12000, 11100, 35)]),
    "FG-EA": (8000, [("2026-04", 7800, 7450, 25), ("2026-05", 8000, 7920, 18)]),
    "FG-FA": (6000, [("2026-04", 5800, 5650, 15), ("2026-05", 6000, 5980, 10)]),
    "FG-MEOH": (25000, [("2026-04", 24000, 22800, 90), ("2026-05", 25000, 24650, 60)]),
    "FG-TDI-BHR": (5000, [("2026-04", 4800, 4300, 40), ("2026-05", 5000, 4850, 22)]),
    "FG-ANI": (9000, [("2026-04", 8700, 8550, 18), ("2026-05", 9000, 8100, 33)]),
    "FG-TDI-DHJ": (6000, [("2026-04", 5700, 5900, 15), ("2026-05", 6000, 5250, 48)]),
}

EQUIPMENT = [
    {"EquipmentID": "10001001", "Description": "Ammonia Feed Pump", "Plant": "1001-BHR", "Unit": "Ammonia (Natural Gas Route)", "FunctionalLocation": "BHR-AMMNG-PUMP-101", "EquipmentClass": "Pump", "Manufacturer": "KSB", "InstallDate": "2016-03-01"},
    {"EquipmentID": "10001002", "Description": "Ammonia Synthesis Compressor", "Plant": "1001-BHR", "Unit": "Ammonia (Natural Gas Route)", "FunctionalLocation": "BHR-AMMNG-COMP-201", "EquipmentClass": "Compressor", "Manufacturer": "Elliott", "InstallDate": "2016-03-01"},
    {"EquipmentID": "10001003", "Description": "Primary Reformer", "Plant": "1001-BHR", "Unit": "Ammonia (Natural Gas Route)", "FunctionalLocation": "BHR-AMMNG-REF-301", "EquipmentClass": "Reactor", "Manufacturer": "Haldor Topsoe", "InstallDate": "2016-03-01"},
    {"EquipmentID": "10001004", "Description": "Boiler Feed Water Pump", "Plant": "1001-BHR", "Unit": "Urea", "FunctionalLocation": "BHR-UREA-PUMP-102", "EquipmentClass": "Pump", "Manufacturer": "KSB", "InstallDate": "2015-11-15"},
    {"EquipmentID": "10001005", "Description": "Urea Reactor", "Plant": "1001-BHR", "Unit": "Urea", "FunctionalLocation": "BHR-UREA-REACT-401", "EquipmentClass": "Reactor", "Manufacturer": "Stamicarbon", "InstallDate": "2015-11-15"},
    {"EquipmentID": "10001006", "Description": "CO2 Compressor", "Plant": "1001-BHR", "Unit": "Urea", "FunctionalLocation": "BHR-UREA-COMP-202", "EquipmentClass": "Compressor", "Manufacturer": "Elliott", "InstallDate": "2015-11-15"},
    {"EquipmentID": "10001007", "Description": "Nitric Acid Absorption Column", "Plant": "1001-BHR", "Unit": "Concentrated Nitric Acid", "FunctionalLocation": "BHR-CNA-COL-101", "EquipmentClass": "Column", "Manufacturer": "Uhde", "InstallDate": "2010-06-01"},
    {"EquipmentID": "10001008", "Description": "Acetic Acid Distillation Column", "Plant": "1001-BHR", "Unit": "Acetic Acid", "FunctionalLocation": "BHR-AA-COL-102", "EquipmentClass": "Column", "Manufacturer": "Sulzer", "InstallDate": "2012-01-20"},
    {"EquipmentID": "10001009", "Description": "Methanol Reboiler", "Plant": "1001-BHR", "Unit": "Methanol", "FunctionalLocation": "BHR-MEOH-HX-301", "EquipmentClass": "Heat Exchanger", "Manufacturer": "Alfa Laval", "InstallDate": "2013-09-10"},
    {"EquipmentID": "10001010", "Description": "TDI Phosgenation Reactor", "Plant": "1001-BHR", "Unit": "Toluene Di Isocyanate (Bharuch)", "FunctionalLocation": "BHR-TDI-REACT-402", "EquipmentClass": "Reactor", "Manufacturer": "Bayer Technology", "InstallDate": "2018-05-05"},
    {"EquipmentID": "10001011", "Description": "Boiler 1", "Plant": "1001-BHR", "Unit": "Coal/Natural Gas Boilers", "FunctionalLocation": "BHR-BOIL-01", "EquipmentClass": "Boiler", "Manufacturer": "Thermax", "InstallDate": "2009-01-01"},
    {"EquipmentID": "10001012", "Description": "Boiler 2", "Plant": "1001-BHR", "Unit": "Coal/Natural Gas Boilers", "FunctionalLocation": "BHR-BOIL-02", "EquipmentClass": "Boiler", "Manufacturer": "Thermax", "InstallDate": "2009-01-01"},
    {"EquipmentID": "10001013", "Description": "Boiler 4", "Plant": "1001-BHR", "Unit": "Coal/Natural Gas Boilers", "FunctionalLocation": "BHR-BOIL-04", "EquipmentClass": "Boiler", "Manufacturer": "Thermax", "InstallDate": "2019-07-15"},
    {"EquipmentID": "10001014", "Description": "Steam Turbine 1", "Plant": "1001-BHR", "Unit": "Steam Turbines", "FunctionalLocation": "BHR-TURB-01", "EquipmentClass": "Turbine", "Manufacturer": "Siemens", "InstallDate": "2011-04-01"},
    {"EquipmentID": "10001015", "Description": "Gas Turbine", "Plant": "1001-BHR", "Unit": "Gas Turbine", "FunctionalLocation": "BHR-TURB-GT", "EquipmentClass": "Turbine", "Manufacturer": "GE", "InstallDate": "2014-02-01"},
    {"EquipmentID": "20001001", "Description": "TDI Reactor (Dahej)", "Plant": "2001-DHJ", "Unit": "Toluene Di Isocyanate (Dahej)", "FunctionalLocation": "DHJ-TDI-REACT-501", "EquipmentClass": "Reactor", "Manufacturer": "Bayer Technology", "InstallDate": "2020-08-01"},
    {"EquipmentID": "20001002", "Description": "Boiler (Dahej)", "Plant": "2001-DHJ", "Unit": "Boiler (Dahej)", "FunctionalLocation": "DHJ-BOIL-D1", "EquipmentClass": "Boiler", "Manufacturer": "Thermax", "InstallDate": "2020-08-01"},
    {"EquipmentID": "20001003", "Description": "Syn Gas Generator (Dahej)", "Plant": "2001-DHJ", "Unit": "Syn Gas Generator (Dahej)", "FunctionalLocation": "DHJ-SYNGEN-01", "EquipmentClass": "Gasifier", "Manufacturer": "Air Liquide", "InstallDate": "2020-08-01"},
]

ENTITY_FILES = {
    "A_ProductStdCostEstmt": "product_standard_cost.csv",
    "A_CostCompItmCostEstmt": "cost_component_items.csv",
    "A_PricingConditionRecord": "pricing_condition_records.csv",
    "A_ContributionMargin": "contribution_margin.csv",
    "A_ProductionOrder": "production_orders.csv",
    "A_ProdOrderConfirmedYield": "production_order_confirmed_yield.csv",
    "A_ProductionVariance": "production_variance.csv",
    "A_Equipment": "equipment.csv",
    "A_MaintenanceNotification": "maintenance_notifications.csv",
    "A_MaintenanceOrder": "maintenance_orders.csv",
    "A_EquipmentReliability": "equipment_reliability.csv",
}


def _total_cost(product: str) -> int:
    return sum(COSTS[product].values())


def _cost_header_rows() -> list[dict[str, Any]]:
    rows = []
    for material in MATERIALS:
        product = material["Product"]
        rows.append({
            "Product": product,
            "ProductDescription": material["ProductDescription"],
            "Plant": material["Plant"],
            "CostingVariant": "PPC1",
            "CostEstimateDate": "2026-04-01",
            "ValidToDate": "2026-09-30",
            "Currency": "INR",
            "StandardCostPerUnit": _total_cost(product),
            "BaseUnit": material["BaseUnit"],
        })
    return rows


def _cost_component_rows() -> list[dict[str, Any]]:
    rows = []
    plants = {m["Product"]: m["Plant"] for m in MATERIALS}
    for product, components in COSTS.items():
        for component, amount in components.items():
            rows.append({
                "Product": product,
                "Plant": plants[product],
                "CostComponent": component,
                "Amount": amount,
                "Currency": "INR",
            })
    return rows


def _pricing_rows() -> list[dict[str, Any]]:
    rows = []
    for product, (domestic, export, sales_org) in PRICE_BY_PRODUCT.items():
        rows.append(_pricing_row(product, sales_org, "10", "Domestic", domestic))
        rows.append(_pricing_row(product, sales_org, "20", "Export", export))
    return rows


def _pricing_row(product: str, sales_org: str, channel_code: str, channel: str, amount: int) -> dict[str, Any]:
    return {
        "Product": product,
        "SalesOrg": sales_org,
        "DistrChannel": channel_code,
        "Channel": channel,
        "ConditionType": "PR00",
        "Amount": amount,
        "Currency": "INR",
        "ValidFrom": "2026-04-01",
        "ValidTo": "2026-09-30",
    }


def _contribution_margin_rows() -> list[dict[str, Any]]:
    materials = {m["Product"]: m for m in MATERIALS}
    rows = []
    for price in _pricing_rows():
        product = price["Product"]
        components = COSTS[product]
        variable_cost = components["RawMaterial"] + components["Utilities"] + components["VariableOverhead"]
        fixed_cost = components["Labor"] + components["FixedOverhead"]
        selling_price = price["Amount"]
        contribution = selling_price - variable_cost
        rows.append({
            "Product": product,
            "ProductDescription": materials[product]["ProductDescription"],
            "Plant": materials[product]["Plant"],
            "SalesOrg": price["SalesOrg"],
            "Channel": price["Channel"],
            "SellingPricePerUnit": selling_price,
            "VariableCostPerUnit": variable_cost,
            "FixedCostPerUnit": fixed_cost,
            "StandardCostPerUnit": variable_cost + fixed_cost,
            "UnitContributionMargin": contribution,
            "UnitContributionMarginPct": round((contribution / selling_price) * 100, 2),
            "NetUnitMargin": selling_price - variable_cost - fixed_cost,
            "Currency": "INR",
            "ValidFrom": price["ValidFrom"],
            "ValidTo": price["ValidTo"],
        })
    return rows


def _production_order_rows() -> list[dict[str, Any]]:
    materials = {m["Product"]: m for m in MATERIALS}
    rows = []
    for product, (capacity, orders) in PRODUCTION_PLAN.items():
        for period, planned, actual, scrap in orders:
            rows.append({
                "OrderID": f"PO-{product}-{period}",
                "Product": product,
                "Plant": materials[product]["Plant"],
                "Period": period,
                "UnitOfMeasure": "TO",
                "MonthlyRatedCapacity": capacity,
                "PlannedOrderQuantity": planned,
                "ConfirmedYieldQuantity": actual,
                "ScrapQuantity": scrap,
                "OrderStatus": "TECO",
            })
    return rows


def _confirmed_yield_rows() -> list[dict[str, Any]]:
    rows = []
    for index, order in enumerate(_production_order_rows()):
        product = order["Product"]
        components = COSTS[product]
        factor = 1.02 + ((index % 5) * 0.012)
        util_factor = 0.98 + ((index % 4) * 0.015)
        rows.append({
            "OrderID": order["OrderID"],
            "Product": product,
            "Plant": order["Plant"],
            "Period": order["Period"],
            "ConfirmedYieldQuantity": order["ConfirmedYieldQuantity"],
            "StandardRawMaterialPerUnit": components["RawMaterial"],
            "ActualRawMaterialPerUnit": round(components["RawMaterial"] * factor, 2),
            "StandardUtilitiesPerUnit": components["Utilities"],
            "ActualUtilitiesPerUnit": round(components["Utilities"] * util_factor, 2),
            "Currency": "INR",
        })
    return rows


def _production_variance_rows() -> list[dict[str, Any]]:
    consumption = {row["OrderID"]: row for row in _confirmed_yield_rows()}
    rows = []
    for order in _production_order_rows():
        cons = consumption[order["OrderID"]]
        planned = order["PlannedOrderQuantity"]
        actual = order["ConfirmedYieldQuantity"]
        capacity = order["MonthlyRatedCapacity"]
        rm_variance = round(cons["StandardRawMaterialPerUnit"] - cons["ActualRawMaterialPerUnit"], 2)
        util_variance = round(cons["StandardUtilitiesPerUnit"] - cons["ActualUtilitiesPerUnit"], 2)
        efficiency_variance = round(rm_variance + util_variance, 2)
        rows.append({
            "OrderID": order["OrderID"],
            "Product": order["Product"],
            "Plant": order["Plant"],
            "Period": order["Period"],
            "PlannedOrderQuantity": planned,
            "ConfirmedYieldQuantity": actual,
            "ScrapQuantity": order["ScrapQuantity"],
            "VolumeVarianceQty": actual - planned,
            "VolumeVariancePct": round(((actual - planned) / planned) * 100, 2),
            "MonthlyRatedCapacity": capacity,
            "CapacityUtilizationPct": round((actual / capacity) * 100, 2),
            "RawMaterialEfficiencyVariancePerUnit": rm_variance,
            "UtilitiesEfficiencyVariancePerUnit": util_variance,
            "TotalEfficiencyVariancePerUnit": efficiency_variance,
            "TotalEfficiencyVarianceValue": round(efficiency_variance * actual, 2),
            "Currency": "INR",
        })
    return rows


def _maintenance_notification_rows() -> list[dict[str, Any]]:
    rows = []
    for index, eq in enumerate(EQUIPMENT, start=1):
        if index % 3 == 0:
            rows.append({
                "NotificationID": f"MN-BD-{eq['EquipmentID']}",
                "EquipmentID": eq["EquipmentID"],
                "Plant": eq["Plant"],
                "NotificationType": "M1",
                "Priority": "High" if index % 2 else "Medium",
                "Description": f"Breakdown reported for {eq['Description']}",
                "MalfunctionStart": f"2026-04-{(index % 20) + 1:02d}T08:00:00",
                "MalfunctionEnd": f"2026-04-{(index % 20) + 1:02d}T{10 + (index % 7):02d}:30:00",
                "Status": "Completed",
            })
        rows.append({
            "NotificationID": f"MN-PM-{eq['EquipmentID']}",
            "EquipmentID": eq["EquipmentID"],
            "Plant": eq["Plant"],
            "NotificationType": "M2",
            "Priority": "Medium",
            "Description": f"Preventive maintenance due for {eq['Description']}",
            "MalfunctionStart": "",
            "MalfunctionEnd": "",
            "Status": "Released",
        })
    return rows


def _maintenance_order_rows() -> list[dict[str, Any]]:
    rows = []
    for index, eq in enumerate(EQUIPMENT, start=1):
        planned = 25000 + index * 1750
        actual = planned + ((index % 5) - 2) * 2200
        rows.append({
            "MaintenanceOrderID": f"MO-{eq['EquipmentID']}",
            "EquipmentID": eq["EquipmentID"],
            "Plant": eq["Plant"],
            "OrderType": "PM01",
            "Description": f"Maintenance order for {eq['Description']}",
            "PlannedCost": planned,
            "ActualCost": actual,
            "Currency": "INR",
            "BasicStartDate": "2026-04-01",
            "BasicFinishDate": "2026-06-30",
            "SystemStatus": "TECO" if index % 4 else "REL",
        })
    return rows


def _equipment_reliability_rows() -> list[dict[str, Any]]:
    notifications = _maintenance_notification_rows()
    orders = _maintenance_order_rows()
    window_hours = 2184
    rows = []
    for eq in EQUIPMENT:
        breakdowns = [n for n in notifications if n["EquipmentID"] == eq["EquipmentID"] and n["NotificationType"] == "M1"]
        order_rows = [o for o in orders if o["EquipmentID"] == eq["EquipmentID"]]
        downtime = 0.0
        for row in breakdowns:
            if row["MalfunctionStart"] and row["MalfunctionEnd"]:
                start_hour = int(row["MalfunctionStart"][11:13])
                end_hour = int(row["MalfunctionEnd"][11:13])
                downtime += max(end_hour - start_hour, 0) + 0.5
        breakdown_count = len(breakdowns)
        planned = sum(row["PlannedCost"] for row in order_rows)
        actual = sum(row["ActualCost"] for row in order_rows)
        rows.append({
            "EquipmentID": eq["EquipmentID"],
            "Description": eq["Description"],
            "Plant": eq["Plant"],
            "Unit": eq["Unit"],
            "EquipmentClass": eq["EquipmentClass"],
            "WindowHours": window_hours,
            "BreakdownCount": breakdown_count,
            "TotalDowntimeHours": round(downtime, 1),
            "MTBFHours": round((window_hours - downtime) / breakdown_count, 1) if breakdown_count else "",
            "MTTRHours": round(downtime / breakdown_count, 1) if breakdown_count else "",
            "AvailabilityPct": round(((window_hours - downtime) / window_hours) * 100, 2),
            "MaintenancePlannedCost": planned,
            "MaintenanceActualCost": actual,
            "MaintenanceCostVariance": planned - actual,
            "Currency": "INR",
        })
    return rows


def build_datasets() -> dict[str, list[dict[str, Any]]]:
    return {
        "A_ProductStdCostEstmt": _cost_header_rows(),
        "A_CostCompItmCostEstmt": _cost_component_rows(),
        "A_PricingConditionRecord": _pricing_rows(),
        "A_ContributionMargin": _contribution_margin_rows(),
        "A_ProductionOrder": _production_order_rows(),
        "A_ProdOrderConfirmedYield": _confirmed_yield_rows(),
        "A_ProductionVariance": _production_variance_rows(),
        "A_Equipment": EQUIPMENT,
        "A_MaintenanceNotification": _maintenance_notification_rows(),
        "A_MaintenanceOrder": _maintenance_order_rows(),
        "A_EquipmentReliability": _equipment_reliability_rows(),
    }


def write_csv_files(output_dir: Path = DATA_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"datasets": {}}
    for entity_set, rows in build_datasets().items():
        filename = ENTITY_FILES[entity_set]
        path = output_dir / filename
        headers = list(rows[0].keys()) if rows else []
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        manifest["datasets"][entity_set] = {
            "file": filename,
            "rows": len(rows),
            "columns": headers,
        }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def ensure_csv_files(data_dir: Path = DATA_DIR) -> None:
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        write_csv_files(data_dir)


def parse_scalar(value: str) -> Any:
    if value == "":
        return None
    try:
        if "." not in value:
            return int(value)
        return float(value)
    except ValueError:
        return value


def read_entity(entity_set: str, data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    ensure_csv_files(data_dir)
    filename = ENTITY_FILES.get(entity_set)
    if not filename:
        raise KeyError(entity_set)
    path = data_dir / filename
    with path.open(newline="", encoding="utf-8") as handle:
        return [{key: parse_scalar(value) for key, value in row.items()} for row in csv.DictReader(handle)]

