from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator

SCENARIOS = [
    ScenarioSpec(id="normal", label="Normal Operation"),
    ScenarioSpec(id="bearing_fault", label="Bearing Fault"),
    ScenarioSpec(id="rotor_imbalance", label="Rotor Imbalance"),
    ScenarioSpec(id="cavitation", label="Cavitation (Pump only)"),
]

def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))

def lag(prev: float, target: float, alpha: float) -> float:
    return prev + alpha * (target - prev)

def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)

class RotaryEquipmentGenerator(DomainGenerator):
    domain_id = "rotary_equipment"
    display_name = "Rotary Equipment"
    description = "Vibration, temperature, and performance data for industrial rotary machinery."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="rotary_equipment.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=60, min=1, max=1440, step=1),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=10, min=1, max=1000, step=1),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="equipment_type", label="Type", type="select", default="motor", options=["motor", "pump", "turbine", "compressor"]),
                ParameterSpec(name="nominal_rpm", label="Nominal RPM", type="number", default=2950, min=500, max=15000, step=50),
                ParameterSpec(name="nominal_load_pct", label="Nominal Load", type="number", unit="%", default=80, min=0, max=120, step=1),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.5, min=0, max=1, step=0.1),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=40, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        p = request.parameters
        duration_minutes = float(p.get("duration_minutes", 60))
        sample_rate_hz = float(p.get("sample_rate_hz", 10))
        seed = int(p.get("seed", 42))
        eq_type = str(p.get("equipment_type", "motor"))
        nom_rpm = float(p.get("nominal_rpm", 2950))
        nom_load = float(p.get("nominal_load_pct", 80)) / 100.0
        severity = float(p.get("fault_severity", 0.5))
        event_start_pct = float(p.get("event_start_pct", 40)) / 100.0
        start_time = parse_time(p.get("start_time"))

        rng = random.Random(seed)
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        dt = 1.0 / sample_rate_hz
        event_start = duration_minutes * 60 * event_start_pct

        rpm = nom_rpm
        vib_x = 1.2
        vib_y = 1.5
        vib_z = 0.8
        temp_bearing_de = 45.0
        temp_bearing_nde = 42.0
        temp_winding = 65.0
        power_draw = 100.0 * nom_load
        
        rows = []
        for i in range(total_samples):
            elapsed = i * dt
            ts = start_time + timedelta(seconds=elapsed)
            event = elapsed >= event_start
            state = "NORMAL"

            target_rpm = nom_rpm + 5 * math.sin(elapsed / 2.0)
            target_vib_x = 1.2 + 0.1 * math.sin(elapsed * nom_rpm/60.0 * 2 * math.pi)
            target_vib_y = 1.5 + 0.15 * math.cos(elapsed * nom_rpm/60.0 * 2 * math.pi)
            target_vib_z = 0.8
            target_b_de = 45.0 + 5 * nom_load
            target_b_nde = 42.0 + 4 * nom_load

            cavitation_noise = 0
            if event:
                if request.scenario == "bearing_fault":
                    state = "BEARING_FAULT"
                    target_vib_x += severity * 8.0 * math.sin(elapsed * (nom_rpm/60.0) * 0.4 * 2 * math.pi)
                    target_vib_y += severity * 6.0
                    target_b_de += severity * 30.0
                elif request.scenario == "rotor_imbalance":
                    state = "IMBALANCE"
                    target_vib_x += severity * 12.0 * math.sin(elapsed * (nom_rpm/60.0) * 2 * math.pi)
                    target_vib_y += severity * 12.0 * math.cos(elapsed * (nom_rpm/60.0) * 2 * math.pi)
                    target_b_de += severity * 10.0
                elif request.scenario == "cavitation" and eq_type == "pump":
                    state = "CAVITATION"
                    cavitation_noise = severity * 15.0 * rng.random()
                    target_vib_z += cavitation_noise
                    power_draw = lag(power_draw, 100.0 * nom_load * (1 - severity * 0.2), 0.1)

            rpm = lag(rpm, target_rpm, 0.2)
            vib_x = lag(vib_x, target_vib_x, 0.8)
            vib_y = lag(vib_y, target_vib_y, 0.8)
            vib_z = lag(vib_z, target_vib_z, 0.5)
            temp_bearing_de = lag(temp_bearing_de, target_b_de, 0.01 * dt)
            temp_bearing_nde = lag(temp_bearing_nde, target_b_nde, 0.01 * dt)
            
            rows.append({
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "scenario": request.scenario,
                "operating_state": state,
                "equipment_type": eq_type,
                "rpm": round(rpm + rng.gauss(0, 0.5), 1),
                "vibration_x_mms": round(abs(vib_x) + rng.gauss(0, 0.1), 3),
                "vibration_y_mms": round(abs(vib_y) + rng.gauss(0, 0.1), 3),
                "vibration_z_mms": round(abs(vib_z) + rng.gauss(0, 0.05), 3),
                "bearing_de_temp_c": round(temp_bearing_de + rng.gauss(0, 0.2), 2),
                "bearing_nde_temp_c": round(temp_bearing_nde + rng.gauss(0, 0.2), 2),
                "stator_winding_temp_c": round(temp_winding + rng.gauss(0, 0.2), 2),
                "power_kw": round(power_draw + rng.gauss(0, 1.0), 2),
                "fault_active": 1 if state != "NORMAL" else 0
            })
        return rows
