from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from app.source_simulators.sap_pp import CONFIRMED_YIELD_ROWS, PRODUCTION_ORDER_ROWS
from .base import DomainGenerator, historian_datetime_text

SCENARIOS = [
    ScenarioSpec(id="normal", label="Normal Operation"),
    ScenarioSpec(id="feed_shortage", label="Feed Shortage"),
    ScenarioSpec(id="utility_efficiency_loss", label="Utility Efficiency Loss"),
    ScenarioSpec(id="capacity_derate", label="Capacity Derate"),
    ScenarioSpec(id="quality_excursion", label="Quality Excursion"),
]

PRODUCTS = sorted({row["Product"] for row in PRODUCTION_ORDER_ROWS})


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lag(previous: float, target: float, alpha: float) -> float:
    return previous + alpha * (target - previous)


def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 4, 1, tzinfo=timezone.utc)


class GnfcChemicalProcessGenerator(DomainGenerator):
    domain_id = "gnfc_chemical_process"
    display_name = "GNFC Chemical Process"
    description = "OT/process CSV stream aligned to GNFC SAP PP Product, Plant, and OrderID keys."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="gnfc_chemical_process.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=120, min=1, max=1440, step=1),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=1, min=0.1, max=10, step=0.1),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="start_time", label="Start Time", type="datetime", default="2026-04-01T00:00:00Z", required=False),
                ParameterSpec(name="product", label="Product", type="select", default="FG-UREA", options=PRODUCTS),
                ParameterSpec(name="period", label="SAP Period", type="select", default="2026-04", options=["2026-04", "2026-05"]),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.35, min=0, max=1, step=0.05),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=35, min=0, max=100, step=1),
                ParameterSpec(name="event_end_pct", label="Event End", type="number", unit="%", default=80, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        if request.scenario not in {scenario.id for scenario in SCENARIOS}:
            raise ValueError("Unsupported scenario.")
        params = request.parameters
        duration_minutes = float(params.get("duration_minutes", 120))
        sample_rate_hz = float(params.get("sample_rate_hz", 1))
        seed = int(params.get("seed", 42))
        product = str(params.get("product", "FG-UREA"))
        period = str(params.get("period", "2026-04"))
        severity = float(params.get("fault_severity", 0.35))
        event_start_pct = float(params.get("event_start_pct", 35)) / 100
        event_end_pct = float(params.get("event_end_pct", 80)) / 100
        start_time = parse_time(params.get("start_time"))

        order = self._order(product, period)
        confirmation = self._confirmation(product, period)
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        total_seconds = duration_minutes * 60
        dt = 1 / sample_rate_hz
        event_start = total_seconds * event_start_pct
        event_end = total_seconds * event_end_pct
        if event_end < event_start:
            event_start, event_end = event_end, event_start

        rng = random.Random(seed)
        planned_rate = float(order["PlannedOrderQuantity"]) / max(duration_minutes / 60, 1)
        capacity_rate = float(order["MonthlyRatedCapacity"]) / 720
        production_rate = planned_rate
        raw_material_rate = production_rate * 1.08
        utilities_rate = production_rate * 0.42
        quality_margin = 18.0
        confirmed_yield = 0.0
        scrap = 0.0
        rows: list[dict[str, Any]] = []

        for index in range(total_samples):
            elapsed = index * dt
            ts = start_time + timedelta(seconds=elapsed)
            event = event_start <= elapsed <= event_end
            wave = math.sin((elapsed / max(total_seconds, 1)) * 2 * math.pi)
            feed_shortage = utility_loss = capacity_derate = quality_excursion = 0
            state = "NORMAL"
            target_rate = planned_rate * (1 + 0.03 * wave)
            raw_factor = float(confirmation["ActualRawMaterialPerUnit"]) / float(confirmation["StandardRawMaterialPerUnit"])
            utility_factor = float(confirmation["ActualUtilitiesPerUnit"]) / float(confirmation["StandardUtilitiesPerUnit"])

            if event and request.scenario == "feed_shortage":
                state = "FEED_SHORTAGE"
                feed_shortage = 1
                target_rate *= 1 - 0.34 * severity
                raw_factor *= 0.88
            elif event and request.scenario == "utility_efficiency_loss":
                state = "UTILITY_EFFICIENCY_LOSS"
                utility_loss = 1
                utility_factor *= 1 + 0.45 * severity
                target_rate *= 1 - 0.10 * severity
            elif event and request.scenario == "capacity_derate":
                state = "CAPACITY_DERATE"
                capacity_derate = 1
                target_rate = min(target_rate, capacity_rate * (0.65 - 0.20 * severity))
            elif event and request.scenario == "quality_excursion":
                state = "QUALITY_EXCURSION"
                quality_excursion = 1
                quality_margin -= 0.018 * severity * dt
                target_rate *= 1 - 0.05 * severity
            else:
                quality_margin = lag(quality_margin, 18.0 + 1.5 * wave, 0.02)

            production_rate = lag(production_rate, target_rate, 0.08)
            raw_material_rate = lag(raw_material_rate, production_rate * 1.08 * raw_factor, 0.05)
            utilities_rate = lag(utilities_rate, production_rate * 0.42 * utility_factor, 0.05)
            incremental_yield = max(production_rate, 0) * dt / 3600
            incremental_scrap = incremental_yield * (0.003 + (0.015 * severity if quality_excursion else 0.0))
            confirmed_yield += incremental_yield - incremental_scrap
            scrap += incremental_scrap
            utilization = (production_rate / max(capacity_rate, 1)) * 100
            process_alarm = 1 if feed_shortage or utility_loss or capacity_derate or quality_margin < 4.0 else 0

            rows.append(
                {
                    "timestamp": historian_datetime_text(ts),
                    "scenario": request.scenario,
                    "operating_state": state,
                    "Plant": order["Plant"],
                    "Product": product,
                    "OrderID": order["OrderID"],
                    "BatchID": f"{product}-{period}-B{1 + index // max(1, int(total_samples / 4)):03d}",
                    "Period": period,
                    "production_rate_tph": round(production_rate + rng.gauss(0, planned_rate * 0.003), 3),
                    "confirmed_yield_t": round(confirmed_yield, 3),
                    "scrap_t": round(scrap, 3),
                    "raw_material_rate_tph": round(raw_material_rate + rng.gauss(0, planned_rate * 0.002), 3),
                    "utilities_rate_gjph": round(utilities_rate + rng.gauss(0, planned_rate * 0.001), 3),
                    "capacity_utilization_pct": round(clamp(utilization + rng.gauss(0, 0.2), 0, 130), 3),
                    "quality_margin_pct": round(quality_margin + rng.gauss(0, 0.08), 3),
                    "feed_shortage_active": feed_shortage,
                    "utility_efficiency_loss_active": utility_loss,
                    "capacity_derate_active": capacity_derate,
                    "quality_excursion_active": quality_excursion,
                    "process_alarm": process_alarm,
                }
            )
        return rows

    def _order(self, product: str, period: str) -> dict[str, Any]:
        for order in PRODUCTION_ORDER_ROWS:
            if order["Product"] == product and order["Period"] == period:
                return order
        raise ValueError(f"No SAP PP order row for Product={product}, Period={period}.")

    def _confirmation(self, product: str, period: str) -> dict[str, Any]:
        for confirmation in CONFIRMED_YIELD_ROWS:
            if confirmation["Product"] == product and confirmation["Period"] == period:
                return confirmation
        raise ValueError(f"No SAP PP confirmation row for Product={product}, Period={period}.")
