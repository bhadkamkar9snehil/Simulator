from __future__ import annotations
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator

SCENARIOS = [
    ScenarioSpec(id="normal", label="Normal Operation"),
    ScenarioSpec(id="pushing_delay", label="Pushing Delay"),
    ScenarioSpec(id="under_heating", label="Under-heating"),
]

def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))

def lag(prev: float, target: float, alpha: float) -> float:
    return prev + alpha * (target - prev)

def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)

class CokeOvenGenerator(DomainGenerator):
    domain_id = "steel_coke_oven"
    display_name = "Steel: Coke Oven Plant"
    description = "Simulation of Coke Oven Battery heating and pushing."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="coke_oven.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=1440, min=60, max=10000, step=60),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=0.01666, min=0.001, max=1, step=0.001), # 1 per min
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="coking_time_hrs", label="Coking Time", type="number", unit="hrs", default=18.0, min=12, max=30, step=0.5),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.4, min=0, max=1, step=0.05),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=30, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        p = request.parameters
        duration_minutes = float(p.get("duration_minutes", 1440))
        sample_rate_hz = float(p.get("sample_rate_hz", 0.01666))
        seed = int(p.get("seed", 42))
        coking_time = float(p.get("coking_time_hrs", 18.0))
        severity = float(p.get("fault_severity", 0.4))
        event_start_pct = float(p.get("event_start_pct", 30)) / 100.0
        start_time = parse_time(p.get("start_time"))

        rng = random.Random(seed)
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        dt = 1.0 / sample_rate_hz
        event_start = duration_minutes * 60 * event_start_pct

        flue_temp = 1250.0 # C
        oven_temp = 1050.0 # C
        gas_yield = 300.0 # Nm3/t
        pushing_force = 120.0 # amps
        coal_moisture = 8.0 # %
        
        rows = []
        for i in range(total_samples):
            elapsed = i * dt
            ts = start_time + timedelta(seconds=elapsed)
            event = elapsed >= event_start
            state = "NORMAL"

            target_flue = 1250.0
            target_oven = 1050.0
            target_pushing = 120.0

            delay = under_heat = 0

            if event:
                if request.scenario == "pushing_delay":
                    state = "PUSHING_DELAY"
                    delay = 1
                    target_oven -= severity * 50.0
                elif request.scenario == "under_heating":
                    state = "UNDER_HEATING"
                    under_heat = 1
                    target_flue -= severity * 150.0
                    target_oven -= severity * 100.0
                    target_pushing += severity * 80.0

            flue_temp = lag(flue_temp, target_flue, 0.005 * dt)
            oven_temp = lag(oven_temp, target_oven, 0.002 * dt)
            pushing_force = lag(pushing_force, target_pushing, 0.05 * dt)

            rows.append({
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "scenario": request.scenario,
                "operating_state": state,
                "flue_temperature_c": round(flue_temp + rng.gauss(0, 2.0), 1),
                "oven_temperature_c": round(oven_temp + rng.gauss(0, 3.0), 1),
                "coke_oven_gas_yield_nm3t": round(gas_yield + rng.gauss(0, 5.0), 1),
                "pushing_machine_current_a": round(pushing_force + rng.gauss(0, 5.0), 1),
                "coal_moisture_pct": round(coal_moisture + rng.gauss(0, 0.2), 2),
                "pushing_delay_alarm": delay,
                "under_heating_alarm": under_heat
            })
        return rows
