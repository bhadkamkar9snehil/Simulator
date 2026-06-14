from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator

SCENARIOS = [
    ScenarioSpec(id="normal", label="Normal Operation"),
    ScenarioSpec(id="small_leak", label="Small Leak"),
    ScenarioSpec(id="large_leak", label="Large Leak"),
    ScenarioSpec(id="pump_trip", label="Pump Trip"),
    ScenarioSpec(id="valve_closure", label="Valve Closure"),
    ScenarioSpec(id="sensor_drift", label="Sensor Drift"),
]
PRODUCTS = ["crude", "diesel", "petrol", "atf"]


def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


def lag(prev: float, target: float, alpha: float) -> float:
    return prev + alpha * (target - prev)


def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


class PetroleumPipelineGenerator(DomainGenerator):
    domain_id = "petroleum_pipeline"
    display_name = "Petroleum Pipeline"
    description = "Synthetic SCADA-like data for crude and petroleum product pipeline operations."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="petroleum_pipeline.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=120, min=1, max=1440, step=1),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=1, min=0.1, max=100, step=0.1),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="start_time", label="Start Time", type="datetime", default="2026-01-01T00:00:00Z", required=False),
                ParameterSpec(name="product", label="Product", type="select", default="crude", options=PRODUCTS),
                ParameterSpec(name="line_length_km", label="Line Length", type="number", unit="km", default=937, min=1, max=2500, step=1),
                ParameterSpec(name="nominal_flow_m3h", label="Nominal Flow", type="number", unit="m3/h", default=1200, min=10, max=6000, step=10),
                ParameterSpec(name="nominal_discharge_pressure_bar", label="Nominal Discharge Pressure", type="number", unit="bar", default=68, min=5, max=150, step=0.5),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.025, min=0, max=1, step=0.005),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=45, min=0, max=100, step=1),
                ParameterSpec(name="event_end_pct", label="Event End", type="number", unit="%", default=75, min=0, max=100, step=1),
                ParameterSpec(name="alarm_delay_seconds", label="Alarm Delay", type="number", unit="s", default=90, min=0, max=3600, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        p = request.parameters
        duration_minutes = float(p.get("duration_minutes", 120))
        sample_rate_hz = float(p.get("sample_rate_hz", 1))
        seed = int(p.get("seed", 42))
        product = str(p.get("product", "crude"))
        line_length_km = float(p.get("line_length_km", 937))
        nominal_flow = float(p.get("nominal_flow_m3h", 1200))
        nominal_pressure = float(p.get("nominal_discharge_pressure_bar", 68))
        fault_severity = float(p.get("fault_severity", 0.025))
        event_start_pct = float(p.get("event_start_pct", 45)) / 100.0
        event_end_pct = float(p.get("event_end_pct", 75)) / 100.0
        alarm_delay_s = float(p.get("alarm_delay_seconds", 90))
        start_time = parse_time(p.get("start_time"))
        if product not in PRODUCTS:
            raise ValueError("Unsupported product.")
        if request.scenario not in {s.id for s in SCENARIOS}:
            raise ValueError("Unsupported scenario.")

        profiles = {
            "crude": {"density": 860.0, "viscosity": 12.0, "temperature": 34.0},
            "diesel": {"density": 830.0, "viscosity": 3.5, "temperature": 31.0},
            "petrol": {"density": 745.0, "viscosity": 0.7, "temperature": 29.0},
            "atf": {"density": 800.0, "viscosity": 1.5, "temperature": 28.0},
        }
        prof = profiles[product]
        rng = random.Random(seed)
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        total_seconds = duration_minutes * 60
        dt = 1.0 / sample_rate_hz
        event_start = total_seconds * event_start_pct
        event_end = total_seconds * event_end_pct
        if event_end < event_start:
            event_start, event_end = event_end, event_start

        temp = prof["temperature"]
        viscosity = prof["viscosity"]
        density = prof["density"]
        flow = nominal_flow
        flow_mid = nominal_flow
        flow_out = nominal_flow
        pump_speed = 1480.0
        valve_main = 100.0
        valve_delivery = 92.0
        a_suction = 7.5
        a_discharge = nominal_pressure
        b_suction = nominal_pressure * 0.72
        b_discharge = nominal_pressure * 0.70
        c_receipt = nominal_pressure * 0.46
        drift = 0.0
        rows: list[dict[str, Any]] = []

        for i in range(total_samples):
            elapsed = i * dt
            ts = start_time + timedelta(seconds=elapsed)
            event = event_start <= elapsed <= event_end
            state = "NORMAL"
            leak_active = pump_trip_active = valve_closure_active = sensor_fault_active = 0
            wave = math.sin(2 * math.pi * elapsed / max(total_seconds, 1))
            ripple = math.sin(2 * math.pi * elapsed / 300.0)

            temp = lag(temp, prof["temperature"] + 1.5 * wave, 0.005)
            viscosity = max(0.2, prof["viscosity"] * math.exp(-0.025 * (temp - prof["temperature"])))
            pump_target = 1480 + 8 * ripple
            pump_status = 1
            if request.scenario == "pump_trip" and event:
                state = "PUMP_TRIP"; pump_trip_active = 1; pump_status = 0; pump_target = 0
            pump_speed = lag(pump_speed, pump_target, 0.08)

            valve_target = 100.0
            if request.scenario == "valve_closure" and event:
                state = "VALVE_CLOSURE"; valve_closure_active = 1; valve_target = 42.0
            valve_main = lag(valve_main, valve_target, 0.04)

            speed_factor = pump_speed / 1480.0
            valve_factor = clamp(valve_main / 100, 0.1, 1.0)
            viscosity_factor = clamp(prof["viscosity"] / viscosity, 0.6, 1.3)
            target_flow = nominal_flow * speed_factor * (0.35 + 0.65 * valve_factor) * viscosity_factor

            leak_fraction = 0.0
            if request.scenario == "small_leak" and event:
                state = "SMALL_LEAK"; leak_active = 1; leak_fraction = max(0.005, fault_severity)
            if request.scenario == "large_leak" and event:
                state = "LARGE_LEAK"; leak_active = 1; leak_fraction = max(0.05, fault_severity * 3.0)
            if request.scenario == "sensor_drift" and event:
                state = "SENSOR_DRIFT"; sensor_fault_active = 1; drift += 0.0025
            elif request.scenario != "sensor_drift":
                drift = 0.0

            flow = lag(flow, target_flow, 0.08)
            flow_mid = lag(flow_mid, flow * (1 - leak_fraction * 0.45), 0.05)
            flow_out = lag(flow_out, flow * (1 - leak_fraction), 0.04)
            hydraulic_load = (flow / max(nominal_flow, 1)) ** 2
            base_drop = clamp(0.000018 * line_length_km * hydraulic_load * (viscosity / prof["viscosity"]) * nominal_pressure, 5.0, nominal_pressure * 0.75)
            valve_backpressure = (1 - valve_factor) * 18.0
            a_suction_t = 7.5 + 0.4 * ripple
            a_discharge_t = nominal_pressure * speed_factor + valve_backpressure - 0.12 * (viscosity - prof["viscosity"])
            if pump_trip_active: a_discharge_t = 9.0
            b_suction_t = a_discharge_t - base_drop * 0.45
            b_discharge_t = b_suction_t - 1.5
            c_receipt_t = a_discharge_t - base_drop
            if leak_active:
                b_suction_t -= nominal_pressure * leak_fraction * 1.5
                c_receipt_t -= nominal_pressure * leak_fraction * 2.8
            if valve_closure_active:
                a_discharge_t += 5
                c_receipt_t -= 8
            a_suction = lag(a_suction, a_suction_t, 0.08)
            a_discharge = lag(a_discharge, a_discharge_t, 0.07)
            b_suction = lag(b_suction, b_suction_t, 0.045)
            b_discharge = lag(b_discharge, b_discharge_t, 0.045)
            c_receipt = lag(c_receipt, c_receipt_t, 0.035)
            pump_power = (150 + 0.00038 * flow * a_discharge * (viscosity / prof["viscosity"])) * clamp(speed_factor, 0, 1.2)
            if valve_closure_active: pump_power *= 1.08
            leak_alarm = 1 if leak_active and elapsed >= event_start + alarm_delay_s else 0

            rows.append({
                "timestamp": ts.isoformat().replace("+00:00", "Z"), "scenario": request.scenario, "operating_state": state, "product": product,
                "station_a_suction_pressure_bar": round(a_suction + rng.gauss(0, 0.04), 3),
                "station_a_discharge_pressure_bar": round(a_discharge + rng.gauss(0, 0.08), 3),
                "station_b_suction_pressure_bar": round(b_suction + drift + rng.gauss(0, 0.07), 3),
                "station_b_discharge_pressure_bar": round(b_discharge + rng.gauss(0, 0.07), 3),
                "station_c_receipt_pressure_bar": round(c_receipt + rng.gauss(0, 0.06), 3),
                "flow_in_m3h": round(flow + rng.gauss(0, 1.8), 3), "flow_mid_m3h": round(flow_mid + rng.gauss(0, 1.8), 3), "flow_out_m3h": round(flow_out + rng.gauss(0, 1.8), 3),
                "pump_1_speed_rpm": round(pump_speed + rng.gauss(0, 1.2), 2), "pump_1_power_kw": round(pump_power + rng.gauss(0, 3), 2), "pump_1_status": pump_status,
                "pump_2_speed_rpm": 0.0, "pump_2_power_kw": 0.0, "pump_2_status": 0,
                "mainline_valve_position_pct": round(valve_main + rng.gauss(0, 0.15), 2), "delivery_valve_position_pct": round(valve_delivery + rng.gauss(0, 0.1), 2),
                "product_temperature_c": round(temp + rng.gauss(0, 0.03), 3), "product_density_kgm3": round(density + rng.gauss(0, 0.2), 3), "product_viscosity_cp": round(viscosity + rng.gauss(0, 0.03), 4),
                "pressure_drop_ab_bar": round(a_discharge - b_suction, 3), "pressure_drop_bc_bar": round(b_discharge - c_receipt, 3), "flow_imbalance_m3h": round(flow - flow_out, 3),
                "leak_active": leak_active, "leak_alarm": leak_alarm, "pump_trip_active": pump_trip_active, "valve_closure_active": valve_closure_active, "sensor_fault_active": sensor_fault_active,
            })
        return rows
