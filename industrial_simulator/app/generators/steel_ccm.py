from __future__ import annotations
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator

SCENARIOS = [
    ScenarioSpec(id="normal", label="Normal Casting"),
    ScenarioSpec(id="breakout", label="Breakout"),
    ScenarioSpec(id="clogged_nozzle", label="Clogged Nozzle"),
    ScenarioSpec(id="mold_level_fluctuation", label="Mold Level Fluctuation"),
]

def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))

def lag(prev: float, target: float, alpha: float) -> float:
    return prev + alpha * (target - prev)

def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)

class CcmGenerator(DomainGenerator):
    domain_id = "steel_ccm"
    display_name = "Steel: Continuous Casting Machine"
    description = "Simulation of a Continuous Casting Machine (CCM)."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="ccm_casting.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=60, min=10, max=300, step=1),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=5, min=0.1, max=50, step=0.1),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="casting_speed_mpm", label="Casting Speed", type="number", unit="m/min", default=1.2, min=0.5, max=5.0, step=0.1),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.5, min=0, max=1, step=0.1),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=50, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        p = request.parameters
        duration_minutes = float(p.get("duration_minutes", 60))
        sample_rate_hz = float(p.get("sample_rate_hz", 5))
        seed = int(p.get("seed", 42))
        nom_speed = float(p.get("casting_speed_mpm", 1.2))
        severity = float(p.get("fault_severity", 0.5))
        event_start_pct = float(p.get("event_start_pct", 50)) / 100.0
        start_time = parse_time(p.get("start_time"))

        rng = random.Random(seed)
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        dt = 1.0 / sample_rate_hz
        event_start = duration_minutes * 60 * event_start_pct

        mold_level = 80.0 # %
        tundish_weight = 25.0 # t
        casting_speed = nom_speed
        primary_cooling = 1200.0 # L/min
        secondary_cooling = 800.0 # L/min
        strand_surface_temp = 950.0 # C
        
        rows = []
        for i in range(total_samples):
            elapsed = i * dt
            ts = start_time + timedelta(seconds=elapsed)
            event = elapsed >= event_start
            state = "CASTING"

            target_level = 80.0
            target_speed = nom_speed
            target_primary = 1200.0
            target_secondary = 800.0 * (casting_speed / max(0.1, nom_speed))

            breakout = clog = level_alarm = 0

            if event:
                if request.scenario == "breakout":
                    state = "BREAKOUT"
                    breakout = 1
                    target_level = 0.0 # Drains instantly
                    target_speed = 0.0
                    target_primary = 0.0
                elif request.scenario == "clogged_nozzle":
                    state = "CLOGGED"
                    clog = 1
                    target_level -= severity * 30.0
                elif request.scenario == "mold_level_fluctuation":
                    state = "FLUCTUATION"
                    level_alarm = 1
                    target_level += severity * 20.0 * math.sin(elapsed * 2)

            tundish_weight -= (0.01 * casting_speed * dt)
            if tundish_weight < 5.0:
                tundish_weight = 25.0 # Refill mock

            mold_level = lag(mold_level, target_level, (0.5 if breakout else 0.1) * dt)
            casting_speed = lag(casting_speed, target_speed, 0.2 * dt)
            primary_cooling = lag(primary_cooling, target_primary, 0.1 * dt)
            secondary_cooling = lag(secondary_cooling, target_secondary, 0.1 * dt)
            
            strand_surface_temp = 950.0 - 50.0 * (secondary_cooling / 800.0) + 100.0 * (casting_speed / nom_speed)

            rows.append({
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "scenario": request.scenario,
                "operating_state": state,
                "mold_level_pct": round(mold_level + rng.gauss(0, 1.0), 2),
                "tundish_weight_t": round(tundish_weight, 2),
                "casting_speed_mpm": round(casting_speed + rng.gauss(0, 0.01), 3),
                "primary_cooling_lmin": round(primary_cooling + rng.gauss(0, 10.0), 1),
                "secondary_cooling_lmin": round(secondary_cooling + rng.gauss(0, 5.0), 1),
                "strand_surface_temp_c": round(strand_surface_temp + rng.gauss(0, 5.0), 1),
                "breakout_alarm": breakout,
                "clogged_nozzle_alarm": clog,
                "level_fluctuation_alarm": level_alarm
            })
        return rows
