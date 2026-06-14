from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator

SCENARIOS = [
    ScenarioSpec(id="normal", label="Normal Operation"),
    ScenarioSpec(id="compressor_trip", label="Compressor Trip"),
    ScenarioSpec(id="leak", label="Pipeline Leak"),
    ScenarioSpec(id="hydrate_formation", label="Hydrate Formation"),
    ScenarioSpec(id="choke", label="Choked Flow"),
]

GAS_TYPES = ["natural_gas", "lpg_vapor", "lng_vapor", "hydrogen_blend"]

def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))

def lag(prev: float, target: float, alpha: float) -> float:
    return prev + alpha * (target - prev)

def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)

class GasPipelineGenerator(DomainGenerator):
    domain_id = "gas_pipeline"
    display_name = "Gas/LPG Pipeline"
    description = "Synthetic SCADA-like data for gas pipeline operations."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="gas_pipeline.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=120, min=1, max=1440, step=1),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=1, min=0.1, max=100, step=0.1),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="gas_type", label="Gas Type", type="select", default="natural_gas", options=GAS_TYPES),
                ParameterSpec(name="line_length_km", label="Line Length", type="number", unit="km", default=500, min=10, max=3000, step=10),
                ParameterSpec(name="nominal_flow_mmscmd", label="Nominal Flow", type="number", unit="MMSCMD", default=15, min=1, max=100, step=1),
                ParameterSpec(name="nominal_pressure_bar", label="Nominal Pressure", type="number", unit="bar", default=90, min=20, max=150, step=1),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.05, min=0, max=1, step=0.01),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=40, min=0, max=100, step=1),
                ParameterSpec(name="event_end_pct", label="Event End", type="number", unit="%", default=80, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        p = request.parameters
        duration_minutes = float(p.get("duration_minutes", 120))
        sample_rate_hz = float(p.get("sample_rate_hz", 1))
        seed = int(p.get("seed", 42))
        gas_type = str(p.get("gas_type", "natural_gas"))
        length_km = float(p.get("line_length_km", 500))
        nom_flow = float(p.get("nominal_flow_mmscmd", 15))
        nom_press = float(p.get("nominal_pressure_bar", 90))
        severity = float(p.get("fault_severity", 0.05))
        event_start_pct = float(p.get("event_start_pct", 40)) / 100.0
        event_end_pct = float(p.get("event_end_pct", 80)) / 100.0
        start_time = parse_time(p.get("start_time"))

        rng = random.Random(seed)
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        total_seconds = duration_minutes * 60
        dt = 1.0 / sample_rate_hz
        event_start = total_seconds * event_start_pct
        event_end = total_seconds * event_end_pct
        if event_end < event_start:
            event_start, event_end = event_end, event_start

        # State vars
        flow_in = nom_flow
        flow_out = nom_flow
        p_suction = 40.0
        p_discharge = nom_press
        p_delivery = nom_press - (length_km * 0.02)
        comp_rpm = 8500.0
        gas_temp = 25.0
        hydrate_risk = 0.0
        wobbe = 50.0 if gas_type == "natural_gas" else 75.0 if gas_type == "lpg_vapor" else 52.0

        rows = []
        for i in range(total_samples):
            elapsed = i * dt
            ts = start_time + timedelta(seconds=elapsed)
            event = event_start <= elapsed <= event_end
            state = "NORMAL"

            comp_trip = leak = hydrate = choke = 0
            
            target_rpm = 8500 + 100 * math.sin(elapsed / 100)
            target_flow = nom_flow
            target_temp = 25.0 + 2 * math.sin(elapsed / 300)

            if request.scenario == "compressor_trip" and event:
                state = "COMP_TRIP"; comp_trip = 1; target_rpm = 0; target_flow *= 0.4
            elif request.scenario == "leak" and event:
                state = "LEAK"; leak = 1; target_flow *= (1 + severity)
            elif request.scenario == "hydrate_formation" and event:
                state = "HYDRATE"; hydrate = 1; target_temp = 5.0; target_flow *= (1 - severity); hydrate_risk = min(100, hydrate_risk + 0.1)
            elif request.scenario == "choke" and event:
                state = "CHOKE"; choke = 1; target_flow *= 0.6
            
            if state != "HYDRATE":
                hydrate_risk = max(0, hydrate_risk - 0.05)

            comp_rpm = lag(comp_rpm, target_rpm, 0.1 * dt)
            flow_in = lag(flow_in, target_flow, 0.05 * dt)
            gas_temp = lag(gas_temp, target_temp, 0.02 * dt)

            if leak:
                flow_out = lag(flow_out, flow_in * (1 - severity), 0.03 * dt)
                p_delivery = lag(p_delivery, nom_press * (1 - severity * 2), 0.02 * dt)
            else:
                flow_out = lag(flow_out, flow_in, 0.03 * dt)
                p_delivery = lag(p_delivery, p_discharge - (length_km * 0.02 * (flow_in / nom_flow)**2), 0.04 * dt)

            if comp_trip:
                p_discharge = lag(p_discharge, p_suction, 0.05 * dt)
            else:
                p_discharge = lag(p_discharge, nom_press * (comp_rpm / 8500.0) - (0 if not choke else 10*severity), 0.1 * dt)

            rows.append({
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "scenario": request.scenario,
                "operating_state": state,
                "compressor_rpm": round(comp_rpm + rng.gauss(0, 10), 1),
                "suction_pressure_bar": round(p_suction + rng.gauss(0, 0.2), 2),
                "discharge_pressure_bar": round(p_discharge + rng.gauss(0, 0.5), 2),
                "delivery_pressure_bar": round(p_delivery + rng.gauss(0, 0.5), 2),
                "flow_in_mmscmd": round(flow_in + rng.gauss(0, 0.1), 2),
                "flow_out_mmscmd": round(flow_out + rng.gauss(0, 0.1), 2),
                "gas_temperature_c": round(gas_temp + rng.gauss(0, 0.1), 2),
                "wobbe_index": round(wobbe + rng.gauss(0, 0.05), 2),
                "hydrate_risk_pct": round(hydrate_risk, 1),
                "compressor_trip_alarm": comp_trip,
                "leak_alarm": leak,
                "hydrate_alarm": 1 if hydrate_risk > 80 else 0,
                "choke_alarm": choke
            })
        return rows
