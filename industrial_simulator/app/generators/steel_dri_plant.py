from __future__ import annotations
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator

SCENARIOS = [
    ScenarioSpec(id="normal", label="Normal Operation"),
    ScenarioSpec(id="reformer_trip", label="Reformer Trip"),
    ScenarioSpec(id="clustering", label="Clustering / Sticking"),
]

def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))

def lag(prev: float, target: float, alpha: float) -> float:
    return prev + alpha * (target - prev)

def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)

class DriPlantGenerator(DomainGenerator):
    domain_id = "steel_dri_plant"
    display_name = "Steel: DRI Plant"
    description = "Simulation of a Direct Reduced Iron (DRI) process."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="dri_plant.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=240, min=30, max=1440, step=10),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=0.1, min=0.01, max=1, step=0.01),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="capacity_tph", label="Capacity TPH", type="number", default=200, min=50, max=400, step=10),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.5, min=0, max=1, step=0.1),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=30, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        p = request.parameters
        duration_minutes = float(p.get("duration_minutes", 240))
        sample_rate_hz = float(p.get("sample_rate_hz", 0.1))
        seed = int(p.get("seed", 42))
        capacity = float(p.get("capacity_tph", 200))
        severity = float(p.get("fault_severity", 0.5))
        event_start_pct = float(p.get("event_start_pct", 30)) / 100.0
        start_time = parse_time(p.get("start_time"))

        rng = random.Random(seed)
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        dt = 1.0 / sample_rate_hz
        event_start = duration_minutes * 60 * event_start_pct

        reformer_temp = 1050.0 # C
        bustle_gas_temp = 900.0 # C
        reducing_gas_flow = capacity * 1800.0 # Nm3/h
        metallization = 94.0 # %
        carbon = 2.5 # %
        discharge_temp = 50.0 # C
        
        rows = []
        for i in range(total_samples):
            elapsed = i * dt
            ts = start_time + timedelta(seconds=elapsed)
            event = elapsed >= event_start
            state = "NORMAL"

            target_reformer = 1050.0
            target_bustle = 900.0
            target_flow = capacity * 1800.0
            target_metal = 94.0

            trip = cluster = 0

            if event:
                if request.scenario == "reformer_trip":
                    state = "REFORMER_TRIP"
                    trip = 1
                    target_reformer = 600.0
                    target_bustle = 500.0
                    target_metal -= severity * 10.0
                elif request.scenario == "clustering":
                    state = "CLUSTERING"
                    cluster = 1
                    target_bustle += severity * 50.0
                    target_flow -= severity * capacity * 300.0

            reformer_temp = lag(reformer_temp, target_reformer, 0.02 * dt)
            bustle_gas_temp = lag(bustle_gas_temp, target_bustle, 0.05 * dt)
            reducing_gas_flow = lag(reducing_gas_flow, target_flow, 0.1 * dt)
            metallization = lag(metallization, target_metal, 0.01 * dt)

            rows.append({
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "scenario": request.scenario,
                "operating_state": state,
                "reformer_temperature_c": round(reformer_temp + rng.gauss(0, 1.0), 1),
                "bustle_gas_temperature_c": round(bustle_gas_temp + rng.gauss(0, 1.0), 1),
                "reducing_gas_flow_nm3h": round(reducing_gas_flow + rng.gauss(0, 100.0), 0),
                "metallization_pct": round(metallization + rng.gauss(0, 0.2), 2),
                "carbon_pct": round(carbon + rng.gauss(0, 0.05), 2),
                "product_discharge_temp_c": round(discharge_temp + rng.gauss(0, 2.0), 1),
                "reformer_trip_alarm": trip,
                "clustering_alarm": cluster
            })
        return rows
