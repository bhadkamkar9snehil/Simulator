from __future__ import annotations
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator

SCENARIOS = [
    ScenarioSpec(id="normal", label="Normal Rolling"),
    ScenarioSpec(id="cobble", label="Cobble in Mill"),
    ScenarioSpec(id="roll_wear", label="Roll Wear"),
    ScenarioSpec(id="tension_loss", label="Inter-stand Tension Loss"),
]

def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))

def lag(prev: float, target: float, alpha: float) -> float:
    return prev + alpha * (target - prev)

def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)

class RollingMillGenerator(DomainGenerator):
    domain_id = "steel_rolling_mill"
    display_name = "Steel: Rolling Mill"
    description = "Simulation of a Long Products Rolling Mill."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="rolling_mill.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=60, min=10, max=600, step=10),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=10, min=1, max=100, step=1),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="billet_size_mm", label="Billet Size", type="number", unit="mm", default=150, min=100, max=200, step=10),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.5, min=0, max=1, step=0.1),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=50, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        p = request.parameters
        duration_minutes = float(p.get("duration_minutes", 60))
        sample_rate_hz = float(p.get("sample_rate_hz", 10))
        seed = int(p.get("seed", 42))
        billet = float(p.get("billet_size_mm", 150))
        severity = float(p.get("fault_severity", 0.5))
        event_start_pct = float(p.get("event_start_pct", 50)) / 100.0
        start_time = parse_time(p.get("start_time"))

        rng = random.Random(seed)
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        dt = 1.0 / sample_rate_hz
        event_start = duration_minutes * 60 * event_start_pct

        furnace_temp = 1150.0
        s1_speed = 0.5
        s2_speed = 0.8
        s3_speed = 1.2
        tension_12 = 50.0
        tension_23 = 45.0
        prod_dim = 12.0
        
        rows = []
        for i in range(total_samples):
            elapsed = i * dt
            ts = start_time + timedelta(seconds=elapsed)
            event = elapsed >= event_start
            state = "ROLLING"

            t_s1 = 0.5
            t_s2 = 0.8
            t_s3 = 1.2
            t_ten12 = 50.0
            t_ten23 = 45.0
            t_dim = 12.0

            cobble = wear = ten_loss = 0

            if event:
                if request.scenario == "cobble":
                    state = "COBBLE"
                    cobble = 1
                    t_s1 = t_s2 = t_s3 = 0.0
                    t_ten12 = t_ten23 = 0.0
                elif request.scenario == "roll_wear":
                    state = "WEAR"
                    wear = 1
                    t_dim += severity * 0.5 # Product gets thicker as rolls wear
                elif request.scenario == "tension_loss":
                    state = "TENSION_LOSS"
                    ten_loss = 1
                    t_ten12 -= severity * 40.0

            s1_speed = lag(s1_speed, t_s1, 0.5 * dt)
            s2_speed = lag(s2_speed, t_s2, 0.5 * dt)
            s3_speed = lag(s3_speed, t_s3, 0.5 * dt)
            tension_12 = lag(tension_12, t_ten12, 0.2 * dt)
            tension_23 = lag(tension_23, t_ten23, 0.2 * dt)
            prod_dim = lag(prod_dim, t_dim, 0.05 * dt)
            
            s1_current = s1_speed * 1200
            s2_current = s2_speed * 1000
            s3_current = s3_speed * 800

            if cobble:
                s2_current = s3_current = 0

            rows.append({
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "scenario": request.scenario,
                "operating_state": state,
                "reheat_furnace_temp_c": round(furnace_temp + rng.gauss(0, 1.0), 1),
                "stand1_speed_mps": round(s1_speed + rng.gauss(0, 0.005), 3),
                "stand2_speed_mps": round(s2_speed + rng.gauss(0, 0.005), 3),
                "stand3_speed_mps": round(s3_speed + rng.gauss(0, 0.005), 3),
                "stand1_current_a": round(s1_current + rng.gauss(0, 10.0) if s1_current>0 else 0, 1),
                "stand2_current_a": round(s2_current + rng.gauss(0, 8.0) if s2_current>0 else 0, 1),
                "stand3_current_a": round(s3_current + rng.gauss(0, 5.0) if s3_current>0 else 0, 1),
                "tension_1_2_kn": round(tension_12 + rng.gauss(0, 1.0), 1),
                "tension_2_3_kn": round(tension_23 + rng.gauss(0, 1.0), 1),
                "product_dimension_mm": round(prod_dim + rng.gauss(0, 0.05), 2),
                "cobble_alarm": cobble,
                "roll_wear_alarm": wear,
                "tension_loss_alarm": ten_loss
            })
        return rows
