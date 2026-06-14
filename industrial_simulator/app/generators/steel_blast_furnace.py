from __future__ import annotations
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator

SCENARIOS = [
    ScenarioSpec(id="normal", label="Normal Operation"),
    ScenarioSpec(id="hanging", label="Hanging and Slipping"),
    ScenarioSpec(id="chilled_hearth", label="Chilled Hearth"),
    ScenarioSpec(id="tuyere_failure", label="Tuyere Failure"),
]

def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))

def lag(prev: float, target: float, alpha: float) -> float:
    return prev + alpha * (target - prev)

def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)

class BlastFurnaceGenerator(DomainGenerator):
    domain_id = "steel_blast_furnace"
    display_name = "Steel: Blast Furnace"
    description = "Process simulation of a Blast Furnace ironmaking operation."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="blast_furnace.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=300, min=10, max=2880, step=10),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=0.1, min=0.01, max=1, step=0.01),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="capacity_tpd", label="Capacity TPD", type="number", default=5000, min=1000, max=12000, step=100),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.3, min=0, max=1, step=0.05),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=30, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        p = request.parameters
        duration_minutes = float(p.get("duration_minutes", 300))
        sample_rate_hz = float(p.get("sample_rate_hz", 0.1))
        seed = int(p.get("seed", 42))
        capacity = float(p.get("capacity_tpd", 5000))
        severity = float(p.get("fault_severity", 0.3))
        event_start_pct = float(p.get("event_start_pct", 30)) / 100.0
        start_time = parse_time(p.get("start_time"))

        rng = random.Random(seed)
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        dt = 1.0 / sample_rate_hz
        event_start = duration_minutes * 60 * event_start_pct

        top_press = 2.0 # bar
        top_temp = 150.0 # C
        blast_press = 4.0 # bar
        blast_temp = 1150.0 # C
        blast_vol = capacity * 1.5 # Nm3/min approx
        coke_rate = 350.0 # kg/thm
        pci_rate = 150.0 # kg/thm
        hm_temp = 1500.0 # C
        
        rows = []
        for i in range(total_samples):
            elapsed = i * dt
            ts = start_time + timedelta(seconds=elapsed)
            event = elapsed >= event_start
            state = "NORMAL"

            target_top_press = 2.0
            target_top_temp = 150.0 + 10 * math.sin(elapsed / 1800)
            target_blast_press = 4.0
            target_hm_temp = 1500.0

            hanging = chilled = tuyere = 0

            if event:
                if request.scenario == "hanging":
                    state = "HANGING"
                    hanging = 1
                    target_blast_press += severity * 1.0
                    target_top_press -= severity * 0.5
                    target_top_temp += severity * 50.0
                elif request.scenario == "chilled_hearth":
                    state = "CHILLED_HEARTH"
                    chilled = 1
                    target_hm_temp -= severity * 100.0
                elif request.scenario == "tuyere_failure":
                    state = "TUYERE_FAILURE"
                    tuyere = 1
                    blast_vol = lag(blast_vol, capacity * 1.5 * (1 - severity * 0.2), 0.05 * dt)
                    target_blast_press -= severity * 0.5
            
            if hanging and rng.random() < 0.05:
                # Slipping event
                target_top_press += 0.5
                target_top_temp -= 20.0

            top_press = lag(top_press, target_top_press, 0.05 * dt)
            top_temp = lag(top_temp, target_top_temp, 0.02 * dt)
            blast_press = lag(blast_press, target_blast_press, 0.05 * dt)
            blast_temp = lag(blast_temp, 1150.0, 0.05 * dt)
            hm_temp = lag(hm_temp, target_hm_temp, 0.005 * dt)

            rows.append({
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "scenario": request.scenario,
                "operating_state": state,
                "top_pressure_bar": round(top_press + rng.gauss(0, 0.02), 3),
                "top_temperature_c": round(top_temp + rng.gauss(0, 2.0), 1),
                "blast_pressure_bar": round(blast_press + rng.gauss(0, 0.05), 3),
                "blast_temperature_c": round(blast_temp + rng.gauss(0, 1.0), 1),
                "blast_volume_nm3min": round(blast_vol + rng.gauss(0, 50.0), 0),
                "coke_rate_kgthm": round(coke_rate + rng.gauss(0, 2.0), 1),
                "pci_rate_kgthm": round(pci_rate + rng.gauss(0, 1.0), 1),
                "hot_metal_temp_c": round(hm_temp + rng.gauss(0, 3.0), 1),
                "hanging_alarm": hanging,
                "chilled_hearth_alarm": chilled,
                "tuyere_failure_alarm": tuyere
            })
        return rows
