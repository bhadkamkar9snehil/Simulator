from __future__ import annotations
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator

SCENARIOS = [
    ScenarioSpec(id="normal", label="Normal Heat"),
    ScenarioSpec(id="argon_plug_failure", label="Argon Plug Failure"),
    ScenarioSpec(id="electrode_breakage", label="Electrode Breakage"),
]

def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))

def lag(prev: float, target: float, alpha: float) -> float:
    return prev + alpha * (target - prev)

def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)

class LrfGenerator(DomainGenerator):
    domain_id = "steel_lrf"
    display_name = "Steel: Ladle Refining Furnace"
    description = "Simulation of a Ladle Refining Furnace (LRF)."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="lrf_heat.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=45, min=20, max=120, step=1),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=1, min=0.1, max=10, step=0.1),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="heat_size_t", label="Heat Size", type="number", unit="t", default=150, min=50, max=300, step=5),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.6, min=0, max=1, step=0.1),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=50, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        p = request.parameters
        duration_minutes = float(p.get("duration_minutes", 45))
        sample_rate_hz = float(p.get("sample_rate_hz", 1))
        seed = int(p.get("seed", 42))
        heat_size = float(p.get("heat_size_t", 150))
        severity = float(p.get("fault_severity", 0.6))
        event_start_pct = float(p.get("event_start_pct", 50)) / 100.0
        start_time = parse_time(p.get("start_time"))

        rng = random.Random(seed)
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        dt = 1.0 / sample_rate_hz
        event_start = duration_minutes * 60 * event_start_pct

        bath_temp = 1550.0 # C
        argon_flow = 200.0 # Nl/min
        electrode_current = 0.0 # kA
        arc_voltage = 0.0 # V
        arc_power = 0.0 # MW
        
        rows = []
        for i in range(total_samples):
            elapsed = i * dt
            ts = start_time + timedelta(seconds=elapsed)
            event = elapsed >= event_start
            state = "HEATING" if elapsed < duration_minutes*60*0.8 else "STIRRING"

            target_argon = 200.0 if state == "HEATING" else 400.0
            target_current = 40.0 if state == "HEATING" else 0.0
            target_voltage = 250.0 if state == "HEATING" else 0.0

            plug_fail = electrode_fail = 0

            if event:
                if request.scenario == "argon_plug_failure":
                    state = "PLUG_FAILURE"
                    plug_fail = 1
                    target_argon *= (1 - severity)
                elif request.scenario == "electrode_breakage" and target_current > 0:
                    state = "ELECTRODE_BREAK"
                    electrode_fail = 1
                    target_current = 0.0
                    target_voltage = 0.0

            argon_flow = lag(argon_flow, target_argon, 0.1 * dt)
            electrode_current = lag(electrode_current, target_current, 0.5 * dt)
            arc_voltage = lag(arc_voltage, target_voltage, 0.5 * dt)
            
            # Rough power calculation
            arc_power = math.sqrt(3) * electrode_current * arc_voltage / 1000.0
            
            # Temp increase during heating
            if arc_power > 1.0:
                bath_temp += (arc_power * 0.02 * dt)
            else:
                bath_temp -= (0.01 * dt) # natural cooling

            rows.append({
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "scenario": request.scenario,
                "operating_state": state,
                "bath_temperature_c": round(bath_temp + rng.gauss(0, 0.5), 1),
                "argon_flow_nlmin": round(argon_flow + rng.gauss(0, 5.0), 1),
                "electrode_current_ka": round(electrode_current + rng.gauss(0, 1.0) if electrode_current>0 else 0, 2),
                "arc_voltage_v": round(arc_voltage + rng.gauss(0, 5.0) if arc_voltage>0 else 0, 1),
                "arc_power_mw": round(arc_power + rng.gauss(0, 0.5) if arc_power>0 else 0, 2),
                "plug_failure_alarm": plug_fail,
                "electrode_breakage_alarm": electrode_fail
            })
        return rows
