from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator

SCENARIOS = [
    ScenarioSpec(id="base_load", label="Base Load"),
    ScenarioSpec(id="load_following", label="Load Following"),
    ScenarioSpec(id="tube_leak", label="Boiler Tube Leak"),
    ScenarioSpec(id="condenser_fouling", label="Condenser Fouling"),
]

def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))

def lag(prev: float, target: float, alpha: float) -> float:
    return prev + alpha * (target - prev)

def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)

class PowerPlantGenerator(DomainGenerator):
    domain_id = "power_plant"
    display_name = "Power Plant"
    description = "Rankine cycle simulation representing a boiler, turbine, and condenser."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="power_plant.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=120, min=1, max=1440, step=1),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=1, min=0.1, max=10, step=0.1),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="capacity_mw", label="Capacity MW", type="number", default=500, min=50, max=1000, step=50),
                ParameterSpec(name="fuel_type", label="Fuel Type", type="select", default="coal", options=["coal", "gas", "biomass"]),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.2, min=0, max=1, step=0.05),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=30, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        p = request.parameters
        duration_minutes = float(p.get("duration_minutes", 120))
        sample_rate_hz = float(p.get("sample_rate_hz", 1))
        seed = int(p.get("seed", 42))
        capacity = float(p.get("capacity_mw", 500))
        fuel_type = str(p.get("fuel_type", "coal"))
        severity = float(p.get("fault_severity", 0.2))
        event_start_pct = float(p.get("event_start_pct", 30)) / 100.0
        start_time = parse_time(p.get("start_time"))

        rng = random.Random(seed)
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        dt = 1.0 / sample_rate_hz
        event_start = duration_minutes * 60 * event_start_pct

        mw_out = capacity * 0.95
        steam_flow = capacity * 3.2
        steam_press = 160.0
        steam_temp = 540.0
        fw_flow = steam_flow
        drum_level = 0.0
        cond_vacuum = -0.09
        fuel_flow = capacity * (0.35 if fuel_type == "coal" else 0.2)
        
        rows = []
        for i in range(total_samples):
            elapsed = i * dt
            ts = start_time + timedelta(seconds=elapsed)
            event = elapsed >= event_start
            state = "NORMAL"

            target_mw = capacity * 0.95
            if request.scenario == "load_following":
                target_mw = capacity * (0.7 + 0.25 * math.sin(elapsed / 1800.0))

            target_steam_press = 160.0
            target_vacuum = -0.09
            leak = fouling = 0

            if event:
                if request.scenario == "tube_leak":
                    state = "TUBE_LEAK"
                    leak = 1
                    target_steam_press -= severity * 40.0
                    fw_flow = lag(fw_flow, steam_flow * (1 + severity * 0.5), 0.05 * dt)
                    drum_level = lag(drum_level, -severity * 200, 0.02 * dt)
                elif request.scenario == "condenser_fouling":
                    state = "FOULING"
                    fouling = 1
                    target_vacuum += severity * 0.06

            mw_out = lag(mw_out, target_mw - (severity*capacity*0.1 if leak else 0) - (severity*capacity*0.05 if fouling else 0), 0.05 * dt)
            steam_flow = lag(steam_flow, mw_out * 3.2, 0.05 * dt)
            steam_press = lag(steam_press, target_steam_press, 0.02 * dt)
            cond_vacuum = lag(cond_vacuum, target_vacuum, 0.01 * dt)
            fuel_flow = lag(fuel_flow, mw_out * (0.35 if fuel_type == "coal" else 0.2) * (1.1 if leak else 1.0) * (1.05 if fouling else 1.0), 0.03 * dt)
            
            if not leak:
                fw_flow = lag(fw_flow, steam_flow, 0.1 * dt)
                drum_level = lag(drum_level, 0.0 + 5*math.sin(elapsed/60), 0.05 * dt)

            rows.append({
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "scenario": request.scenario,
                "operating_state": state,
                "active_power_mw": round(mw_out + rng.gauss(0, capacity*0.005), 2),
                "main_steam_flow_th": round(steam_flow + rng.gauss(0, 2.0), 1),
                "main_steam_pressure_bar": round(steam_press + rng.gauss(0, 0.5), 2),
                "main_steam_temp_c": round(steam_temp + rng.gauss(0, 1.0), 1),
                "feedwater_flow_th": round(fw_flow + rng.gauss(0, 3.0), 1),
                "drum_level_mm": round(drum_level + rng.gauss(0, 5.0), 1),
                "condenser_vacuum_bar": round(cond_vacuum + rng.gauss(0, 0.001), 4),
                "fuel_flow_th": round(fuel_flow + rng.gauss(0, 1.0), 2),
                "boiler_tube_leak_alarm": leak,
                "condenser_fouling_alarm": fouling
            })
        return rows
