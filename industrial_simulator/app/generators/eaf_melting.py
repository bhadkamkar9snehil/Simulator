from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator

SCENARIOS = [
    ScenarioSpec(id="normal_heat", label="Normal Heat"),
    ScenarioSpec(id="unstable_arc", label="Unstable Arc"),
    ScenarioSpec(id="oxygen_lance_fault", label="Oxygen Lance Fault"),
    ScenarioSpec(id="cooling_water_issue", label="Cooling Water Issue"),
    ScenarioSpec(id="delayed_melting", label="Delayed Melting"),
]


def lag(prev: float, target: float, alpha: float) -> float:
    return prev + alpha * (target - prev)


def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


class EafMeltingGenerator(DomainGenerator):
    domain_id = "eaf_melting"
    display_name = "Electric Arc Furnace"
    description = "Synthetic batch data for EAF melting phases and faults."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="eaf_melting.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=90, min=10, max=240, step=1),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=1, min=0.1, max=20, step=0.1),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="start_time", label="Start Time", type="datetime", default="2026-01-01T00:00:00Z", required=False),
                ParameterSpec(name="heat_size_tonnes", label="Heat Size", type="number", unit="t", default=100, min=10, max=300, step=1),
                ParameterSpec(name="tap_temperature_c", label="Tap Temperature", type="number", unit="C", default=1650, min=1500, max=1750, step=1),
                ParameterSpec(name="nominal_power_mw", label="Nominal Power", type="number", unit="MW", default=85, min=5, max=160, step=1),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.25, min=0, max=1, step=0.01),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=35, min=0, max=100, step=1),
                ParameterSpec(name="event_end_pct", label="Event End", type="number", unit="%", default=70, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        p = request.parameters
        duration = float(p.get("duration_minutes", 90))
        rate = float(p.get("sample_rate_hz", 1))
        seed = int(p.get("seed", 42))
        heat_size = float(p.get("heat_size_tonnes", 100))
        tap_temp = float(p.get("tap_temperature_c", 1650))
        nominal_power = float(p.get("nominal_power_mw", 85))
        severity = float(p.get("fault_severity", 0.25))
        start_pct = float(p.get("event_start_pct", 35)) / 100
        end_pct = float(p.get("event_end_pct", 70)) / 100
        start_time = parse_time(p.get("start_time"))
        if request.scenario not in {s.id for s in SCENARIOS}:
            raise ValueError("Unsupported scenario.")
        rng = random.Random(seed)
        samples = max(1, int(duration * 60 * rate))
        total_s = duration * 60
        dt = 1 / rate
        ev_start, ev_end = total_s * start_pct, total_s * end_pct
        if ev_end < ev_start: ev_start, ev_end = ev_end, ev_start
        bath = 25.0
        offgas = 30.0
        water_out = 28.0
        energy = 0.0
        rows: list[dict[str, Any]] = []
        heat_id = f"HEAT-{seed:06d}"
        for i in range(samples):
            t = i * dt
            x = t / max(total_s, 1)
            event = ev_start <= t <= ev_end
            if x < 0.06: phase = "idle"
            elif x < 0.22: phase = "bore_down"
            elif x < 0.70: phase = "melting"
            elif x < 0.92: phase = "refining"
            else: phase = "tapping"
            unstable = oxygen_fault = cooling_fault = delayed = 0
            power_factor = {"idle": 0.05, "bore_down": 0.75, "melting": 1.0, "refining": 0.65, "tapping": 0.08}[phase]
            arc_stability = {"idle": 1.0, "bore_down": 0.65, "melting": 0.82, "refining": 0.90, "tapping": 1.0}[phase]
            if request.scenario == "unstable_arc" and event:
                unstable = 1; arc_stability -= 0.35 * severity; power_factor *= 1 + rng.gauss(0, 0.18 * severity)
            oxygen_flow = 0.0 if phase in {"idle", "tapping"} else (2800 if phase == "melting" else 5200)
            if request.scenario == "oxygen_lance_fault" and event:
                oxygen_fault = 1; oxygen_flow *= max(0.1, 1 - severity)
            carbon = 0.0 if phase in {"idle", "tapping"} else (55 if phase == "melting" else 35)
            gas = 0.0 if phase in {"idle", "tapping"} else 800
            power = nominal_power * power_factor * (1 + rng.gauss(0, 0.02))
            if request.scenario == "delayed_melting" and event and phase == "melting":
                delayed = 1; power *= 0.88; heat_gain_factor = 0.65
            else:
                heat_gain_factor = 1.0
            current = power * 1.55 + rng.gauss(0, 1.5)
            voltage = 620 + (power_factor * 80) + rng.gauss(0, 8)
            target_bath = 25 + tap_temp * min(1, max(0, (x - 0.05) / 0.84))
            heat_rate = 0.0035 * power_factor * heat_gain_factor
            bath = lag(bath, target_bath, heat_rate)
            offgas_target = 120 + power * 8 + oxygen_flow * 0.035 + carbon * 3
            offgas = lag(offgas, offgas_target, 0.04)
            water_in = 26 + math.sin(t / 600) * 0.5
            water_delta = 4 + power * 0.11
            if request.scenario == "cooling_water_issue" and event:
                cooling_fault = 1; water_delta *= 1 + severity
            water_out = lag(water_out, water_in + water_delta, 0.03)
            energy += power * dt / 3600.0
            tilt = 0 if phase != "tapping" else min(18, (x - 0.92) / 0.08 * 18)
            alarm = 0
            if unstable: alarm = 101
            if oxygen_fault: alarm = 203
            if cooling_fault: alarm = 305
            if delayed: alarm = 407
            rows.append({
                "timestamp": (start_time + timedelta(seconds=t)).isoformat().replace("+00:00", "Z"),
                "scenario": request.scenario, "phase": phase, "heat_id": heat_id,
                "transformer_power_mw": round(max(0, power), 3),
                "electrode_current_ka": round(max(0, current), 3),
                "electrode_voltage_v": round(max(0, voltage), 3),
                "arc_stability_index": round(clamp(arc_stability + rng.gauss(0, 0.03), 0, 1), 4),
                "bath_temperature_c": round(bath + rng.gauss(0, 2.5), 3),
                "offgas_temperature_c": round(offgas + rng.gauss(0, 8), 3),
                "oxygen_flow_nm3h": round(oxygen_flow + rng.gauss(0, 30), 3),
                "carbon_injection_kgmin": round(carbon + rng.gauss(0, 1.2), 3),
                "natural_gas_flow_nm3h": round(gas + rng.gauss(0, 12), 3),
                "cooling_water_inlet_c": round(water_in, 3),
                "cooling_water_outlet_c": round(water_out + rng.gauss(0, 0.08), 3),
                "cooling_water_delta_t_c": round(water_out - water_in, 3),
                "furnace_tilt_deg": round(tilt, 3),
                "energy_consumed_mwh": round(energy, 5),
                "energy_per_tonne_kwh_t": round(energy * 1000 / heat_size, 4),
                "unstable_arc_active": unstable,
                "oxygen_lance_fault_active": oxygen_fault,
                "cooling_water_fault_active": cooling_fault,
                "delayed_melting_active": delayed,
                "alarm_code": alarm,
            })
        return rows
