from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models import GenerateRequest, GeneratorSpec, ParameterSpec, ScenarioSpec
from .base import DomainGenerator, historian_datetime_text


SCENARIOS = [
    ScenarioSpec(id="normal", label="Normal Operation"),
    ScenarioSpec(id="pressure_drop", label="Polymer / Quench Pressure Drop"),
    ScenarioSpec(id="drive_trip", label="Drive Trip"),
    ScenarioSpec(id="filter_fouling", label="Pre-filter Fouling"),
    ScenarioSpec(id="vacuum_loss", label="Polycondensation Vacuum Loss"),
]

PRODUCT_GRADES = ["POY", "PSF", "Hi-IV"]


@dataclass(frozen=True)
class ProductProfile:
    target_iv: float
    throughput_factor: float
    poy_speed_factor: float
    draw_speed_factor: float
    draw_ratio_target: float
    denier_target: float
    denier_low: float
    denier_high: float
    quench_factor: float
    finish_oil_factor: float
    bale_weight_factor: float
    moisture_factor: float


@dataclass(frozen=True)
class TagDef:
    column: str
    area: str
    isa: str
    description: str
    nominal: float
    low: float
    high: float
    unit: str
    noise: float


PRODUCT_PROFILES = {
    "POY": ProductProfile(
        target_iv=0.72,
        throughput_factor=1.0,
        poy_speed_factor=1.0,
        draw_speed_factor=0.92,
        draw_ratio_target=3.0,
        denier_target=120.0,
        denier_low=95.0,
        denier_high=150.0,
        quench_factor=1.0,
        finish_oil_factor=1.0,
        bale_weight_factor=1.0,
        moisture_factor=1.0,
    ),
    "PSF": ProductProfile(
        target_iv=0.68,
        throughput_factor=1.08,
        poy_speed_factor=0.78,
        draw_speed_factor=1.05,
        draw_ratio_target=3.25,
        denier_target=145.0,
        denier_low=135.0,
        denier_high=220.0,
        quench_factor=1.08,
        finish_oil_factor=1.18,
        bale_weight_factor=1.03,
        moisture_factor=1.18,
    ),
    "Hi-IV": ProductProfile(
        target_iv=0.82,
        throughput_factor=0.86,
        poy_speed_factor=0.9,
        draw_speed_factor=0.96,
        draw_ratio_target=2.88,
        denier_target=132.0,
        denier_low=105.0,
        denier_high=165.0,
        quench_factor=0.95,
        finish_oil_factor=0.92,
        bale_weight_factor=0.98,
        moisture_factor=0.8,
    ),
}


TAGS = [
    TagDef("poly_lic_101_pta_silo_level_pct", "POLY", "LIC-101", "PTA silo level", 50.0, 20.0, 90.0, "%", 0.12),
    TagDef("poly_fic_102_pta_feed_rate_kgh", "POLY", "FIC-102", "PTA feed rate", 1850.0, 1500.0, 2200.0, "kg/h", 3.5),
    TagDef("poly_aic_103_n2_o2_ppm", "POLY", "AIC-103", "Conveying nitrogen oxygen", 35.0, 0.0, 80.0, "ppm", 0.8),
    TagDef("poly_tic_111_meg_storage_temp_c", "POLY", "TIC-111", "MEG storage temperature", 32.0, 25.0, 45.0, "C", 0.05),
    TagDef("poly_lic_112_meg_tank_level_pct", "POLY", "LIC-112", "MEG tank level", 62.0, 25.0, 90.0, "%", 0.12),
    TagDef("poly_ric_120_pta_meg_ratio", "POLY", "RIC-120", "PTA to MEG molar ratio", 1.34, 1.2, 1.5, "ratio", 0.002),
    TagDef("poly_tic_120_slurry_temp_c", "POLY", "TIC-120", "Slurry mixing temperature", 78.0, 68.0, 88.0, "C", 0.06),
    TagDef("poly_sic_120_agitator_speed_rpm", "POLY", "SIC-120", "Slurry agitator speed", 68.0, 45.0, 85.0, "rpm", 0.25),
    TagDef("poly_pic_121_slurry_pump_discharge_bar", "POLY", "PIC-121", "Slurry pump discharge pressure", 6.2, 4.8, 7.6, "bar", 0.015),
    TagDef("poly_fic_121_slurry_flow_kgh", "POLY", "FIC-121", "Slurry transfer flow", 2450.0, 2100.0, 2800.0, "kg/h", 5.0),
    TagDef("poly_tic_201_es1_temp_c", "POLY", "TIC-201", "First esterification temperature", 260.0, 250.0, 270.0, "C", 0.08),
    TagDef("poly_pic_202_es1_pressure_bar", "POLY", "PIC-202", "First esterification pressure", 1.2, 1.0, 1.4, "bar", 0.004),
    TagDef("poly_lic_203_es1_chamber_level_pct", "POLY", "LIC-203", "First esterification chamber level", 58.0, 40.0, 75.0, "%", 0.12),
    TagDef("poly_tic_211_es_column_top_temp_c", "POLY", "TIC-211", "Esterification column top temperature", 104.0, 96.0, 112.0, "C", 0.05),
    TagDef("poly_pdt_212_es_column_dp_mbar", "POLY", "PDT-212", "Esterification column differential pressure", 42.0, 20.0, 75.0, "mbar", 0.25),
    TagDef("poly_tic_221_es2_temp_c", "POLY", "TIC-221", "Second esterification temperature", 265.0, 255.0, 275.0, "C", 0.08),
    TagDef("poly_aic_222_es_percent_pct", "POLY", "AIC-222", "Esterification completion", 96.0, 93.0, 99.0, "%", 0.03),
    TagDef("poly_fic_231_oligomer_flow_kgh", "POLY", "FIC-231", "Oligomer flow", 2320.0, 2000.0, 2650.0, "kg/h", 4.5),
    TagDef("poly_pdt_232_pre_pc_filter_dp_bar", "POLY", "PDT-232", "Pre-PC filter differential pressure", 1.8, 0.5, 4.2, "bar", 0.01),
    TagDef("poly_tic_310_pc1_melt_temp_c", "POLY", "TIC-310", "First PC melt temperature", 276.0, 270.0, 282.0, "C", 0.06),
    TagDef("poly_pic_311_pc1_vacuum_mbar", "POLY", "PIC-311", "First PC vacuum", 42.0, 18.0, 65.0, "mbar", 0.2),
    TagDef("poly_aic_312_pc1_torque_pct", "POLY", "AIC-312", "First PC agitator torque", 44.0, 30.0, 70.0, "%", 0.08),
    TagDef("poly_tic_320_pc2_melt_temp_c", "POLY", "TIC-320", "Second PC melt temperature", 282.0, 274.0, 288.0, "C", 0.06),
    TagDef("poly_pic_321_pc2_vacuum_mbar", "POLY", "PIC-321", "Second PC vacuum", 14.0, 6.0, 28.0, "mbar", 0.08),
    TagDef("poly_tic_330_finisher_temp_c", "POLY", "TIC-330", "Finisher melt temperature", 286.0, 278.0, 292.0, "C", 0.06),
    TagDef("poly_pic_331_finisher_vacuum_mbar", "POLY", "PIC-331", "Finisher vacuum", 4.5, 1.5, 9.0, "mbar", 0.03),
    TagDef("poly_aic_332_final_iv_dl_g", "POLY", "AIC-332", "Final intrinsic viscosity", 0.72, 0.635, 0.87, "dL/g", 0.0008),
    TagDef("poly_pdt_341_pre_cutter_filter_dp_bar", "POLY", "PDT-341", "Pre-cutter filter differential pressure", 2.0, 0.6, 4.5, "bar", 0.01),
    TagDef("poly_wic_351_chip_moisture_ppm", "POLY", "WIC-351", "Chip moisture", 34.0, 10.0, 80.0, "ppm", 0.8),
    TagDef("poy_tic_301_ext_z1_temp_c", "POY", "TIC-301", "Extruder zone 1 temperature", 280.0, 270.0, 290.0, "C", 0.08),
    TagDef("poy_tic_302_ext_z2_temp_c", "POY", "TIC-302", "Extruder zone 2 temperature", 285.0, 275.0, 295.0, "C", 0.08),
    TagDef("poy_tic_303_ext_z3_temp_c", "POY", "TIC-303", "Extruder zone 3 temperature", 290.0, 280.0, 300.0, "C", 0.08),
    TagDef("poy_tic_304_ext_z4_temp_c", "POY", "TIC-304", "Extruder zone 4 temperature", 292.0, 282.0, 302.0, "C", 0.08),
    TagDef("poy_tic_305_ext_z5_temp_c", "POY", "TIC-305", "Extruder zone 5 temperature", 295.0, 285.0, 305.0, "C", 0.08),
    TagDef("poy_tic_306_ext_z6_temp_c", "POY", "TIC-306", "Extruder zone 6 temperature", 295.0, 285.0, 305.0, "C", 0.08),
    TagDef("poy_pic_307_melt_pressure_bar", "POY", "PIC-307", "Extruder melt pressure", 150.0, 130.0, 170.0, "bar", 0.18),
    TagDef("poy_sic_308_extruder_speed_rpm", "POY", "SIC-308", "Extruder speed", 85.0, 70.0, 100.0, "rpm", 0.12),
    TagDef("poy_iic_309_extruder_amp_a", "POY", "IIC-309", "Extruder current", 140.0, 100.0, 180.0, "A", 0.35),
    TagDef("poy_pt_310_main_header_pressure_bar", "POY", "PT-310", "Main polymer header pressure", 145.0, 125.0, 165.0, "bar", 0.18),
    TagDef("poy_tt_311_main_header_temp_c", "POY", "TT-311", "Main polymer header temperature", 294.0, 285.0, 305.0, "C", 0.06),
    TagDef("poy_pdt_312_filter_a_dp_bar", "POY", "PDT-312", "Spin-pack filter A differential pressure", 45.0, 20.0, 80.0, "bar", 0.12),
    TagDef("poy_tic_314_beam_a_temp_c", "POY", "TIC-314", "Beam A temperature", 292.0, 285.0, 298.0, "C", 0.05),
    TagDef("poy_pi_315_pack_a_pressure_bar", "POY", "PI-315", "Pack A pressure", 180.0, 150.0, 210.0, "bar", 0.22),
    TagDef("poy_sic_316_pump_a_speed_rpm", "POY", "SIC-316", "Metering pump A speed", 30.0, 25.0, 35.0, "rpm", 0.04),
    TagDef("poy_fi_317_poly_flow_a_kgh", "POY", "FI-317", "Polymer flow A", 150.0, 120.0, 180.0, "kg/h", 0.22),
    TagDef("poy_tic_318_beam_b_temp_c", "POY", "TIC-318", "Beam B temperature", 292.0, 285.0, 298.0, "C", 0.05),
    TagDef("poy_pi_319_pack_b_pressure_bar", "POY", "PI-319", "Pack B pressure", 182.0, 150.0, 210.0, "bar", 0.22),
    TagDef("poy_sic_320_pump_b_speed_rpm", "POY", "SIC-320", "Metering pump B speed", 30.0, 25.0, 35.0, "rpm", 0.04),
    TagDef("poy_fic_324_quench_a_flow_m3h", "POY", "FIC-324", "Quench A airflow", 55.0, 45.0, 65.0, "m3/h", 0.12),
    TagDef("poy_tic_325_quench_a_temp_c", "POY", "TIC-325", "Quench A temperature", 22.0, 18.0, 26.0, "C", 0.03),
    TagDef("poy_pic_326_quench_a_pressure_mbar", "POY", "PIC-326", "Quench A pressure", 15.0, 10.0, 20.0, "mbar", 0.04),
    TagDef("poy_fic_327_quench_b_flow_m3h", "POY", "FIC-327", "Quench B airflow", 54.0, 45.0, 65.0, "m3/h", 0.12),
    TagDef("poy_fic_330_finish_flow_a_lh", "POY", "FIC-330", "Finish oil flow A", 2.5, 1.5, 3.5, "L/h", 0.01),
    TagDef("poy_sic_332_godet_1a_speed_mpm", "POY", "SIC-332", "Godet 1A speed", 3200.0, 3000.0, 3400.0, "m/min", 2.0),
    TagDef("poy_sic_333_godet_2a_speed_mpm", "POY", "SIC-333", "Godet 2A speed", 3220.0, 3000.0, 3420.0, "m/min", 2.0),
    TagDef("poy_sic_334_winder_a_speed_mpm", "POY", "SIC-334", "Winder A speed", 3250.0, 3000.0, 3500.0, "m/min", 2.0),
    TagDef("poy_wic_335_winder_a_tension_cn", "POY", "WIC-335", "Winder A tension", 12.0, 8.0, 16.0, "cN", 0.04),
    TagDef("poy_sic_337_godet_1b_speed_mpm", "POY", "SIC-337", "Godet 1B speed", 3200.0, 3000.0, 3400.0, "m/min", 2.0),
    TagDef("poy_sic_339_winder_b_speed_mpm", "POY", "SIC-339", "Winder B speed", 3250.0, 3000.0, 3500.0, "m/min", 2.0),
    TagDef("draw_wic_401_creel_tension_cn", "DRAW", "WIC-401", "Creel tension", 25.0, 15.0, 35.0, "cN", 0.06),
    TagDef("draw_tic_402_bath_temp_c", "DRAW", "TIC-402", "Draw bath temperature", 45.0, 35.0, 55.0, "C", 0.04),
    TagDef("draw_lic_403_bath_level_pct", "DRAW", "LIC-403", "Draw bath level", 60.0, 40.0, 80.0, "%", 0.1),
    TagDef("draw_sic_404_roll_1_speed_mpm", "DRAW", "SIC-404", "Roll 1 speed", 100.0, 90.0, 110.0, "m/min", 0.12),
    TagDef("draw_tic_405_roll_1_temp_c", "DRAW", "TIC-405", "Roll 1 temperature", 80.0, 70.0, 90.0, "C", 0.05),
    TagDef("draw_iic_406_roll_1_amp_a", "DRAW", "IIC-406", "Roll 1 current", 45.0, 20.0, 70.0, "A", 0.18),
    TagDef("draw_vic_407_roll_1_vibration_mms", "DRAW", "VIC-407", "Roll 1 vibration", 1.2, 0.5, 2.5, "mm/s", 0.015),
    TagDef("draw_sic_408_roll_2_speed_mpm", "DRAW", "SIC-408", "Roll 2 speed", 300.0, 270.0, 330.0, "m/min", 0.25),
    TagDef("draw_tic_409_roll_2_temp_c", "DRAW", "TIC-409", "Roll 2 temperature", 140.0, 130.0, 150.0, "C", 0.05),
    TagDef("draw_iic_410_roll_2_amp_a", "DRAW", "IIC-410", "Roll 2 current", 85.0, 50.0, 120.0, "A", 0.22),
    TagDef("draw_sic_412_crimper_speed_mpm", "DRAW", "SIC-412", "Crimper speed", 305.0, 275.0, 335.0, "m/min", 0.22),
    TagDef("draw_pic_413_box_pressure_bar", "DRAW", "PIC-413", "Crimper box pressure", 2.5, 1.8, 3.2, "bar", 0.006),
    TagDef("draw_pic_414_steam_pressure_bar", "DRAW", "PIC-414", "Crimper steam pressure", 1.5, 1.0, 2.0, "bar", 0.004),
    TagDef("draw_qic_416_crimp_frequency_cpi", "DRAW", "QIC-416", "Crimp frequency", 12.0, 9.0, 15.0, "cpi", 0.03),
    TagDef("draw_sic_417_belt_speed_mpm", "DRAW", "SIC-417", "Oven belt speed", 15.0, 10.0, 20.0, "m/min", 0.03),
    TagDef("draw_tic_418_oven_z1_temp_c", "DRAW", "TIC-418", "Oven zone 1 temperature", 130.0, 120.0, 140.0, "C", 0.05),
    TagDef("draw_fic_419_oven_z1_flow_pct", "DRAW", "FIC-419", "Oven zone 1 air flow", 80.0, 60.0, 100.0, "%", 0.15),
    TagDef("draw_tic_420_oven_z3_temp_c", "DRAW", "TIC-420", "Oven zone 3 temperature", 132.0, 120.0, 140.0, "C", 0.05),
    TagDef("draw_sic_422_exhaust_fan_rpm", "DRAW", "SIC-422", "Oven exhaust fan", 1450.0, 1200.0, 1600.0, "rpm", 1.2),
    TagDef("draw_sic_423_cutter_speed_rpm", "DRAW", "SIC-423", "Cutter speed", 600.0, 500.0, 700.0, "rpm", 0.8),
    TagDef("draw_pic_425_hydraulic_pressure_bar", "DRAW", "PIC-425", "Baler hydraulic pressure", 150.0, 100.0, 180.0, "bar", 0.2),
    TagDef("draw_wic_426_bale_weight_kg", "DRAW", "WIC-426", "Bale weight", 400.0, 380.0, 420.0, "kg", 0.2),
]

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lag(previous: float, target: float, alpha: float) -> float:
    alpha = clamp(alpha, 0.0, 1.0)
    return previous + alpha * (target - previous)


def parse_time(value: Any) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


class PolyesterFiberGenerator(DomainGenerator):
    domain_id = "polyester_fiber"
    display_name = "Polyester Fiber Plant"
    description = "SCADA-style PET polymerization, POY spinning, drawline, cutter, and baler process data."

    def get_spec(self) -> GeneratorSpec:
        return GeneratorSpec(
            domain_id=self.domain_id,
            display_name=self.display_name,
            description=self.description,
            scenarios=SCENARIOS,
            default_output_filename="polyester_fiber.csv",
            parameters=[
                ParameterSpec(name="duration_minutes", label="Duration", type="number", unit="min", default=120, min=1, max=1440, step=1),
                ParameterSpec(name="sample_rate_hz", label="Sample Rate", type="number", unit="Hz", default=1, min=0.1, max=10, step=0.1),
                ParameterSpec(name="seed", label="Random Seed", type="number", default=42, min=0, max=999999, step=1),
                ParameterSpec(name="start_time", label="Start Time", type="datetime", default="2026-01-01T00:00:00Z", required=False),
                ParameterSpec(name="product_grade", label="Product Grade", type="select", default="POY", options=PRODUCT_GRADES),
                ParameterSpec(name="line_speed_pct", label="Line Speed", type="number", unit="%", default=100, min=40, max=115, step=1),
                ParameterSpec(name="throughput_kgh", label="Polymer Throughput", type="number", unit="kg/h", default=2400, min=500, max=6000, step=50),
                ParameterSpec(name="target_iv", label="Target IV", type="number", unit="dL/g", default=0.72, min=0.635, max=0.87, step=0.005),
                ParameterSpec(name="fault_severity", label="Fault Severity", type="number", default=0.35, min=0, max=1, step=0.05),
                ParameterSpec(name="event_start_pct", label="Event Start", type="number", unit="%", default=35, min=0, max=100, step=1),
                ParameterSpec(name="event_end_pct", label="Event End", type="number", unit="%", default=80, min=0, max=100, step=1),
            ],
        )

    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        return list(self.iter_rows(request))

    def iter_rows(self, request: GenerateRequest):
        if request.scenario not in {scenario.id for scenario in SCENARIOS}:
            raise ValueError("Unsupported scenario.")

        p = request.parameters
        duration_minutes = float(p.get("duration_minutes", 120))
        sample_rate_hz = float(p.get("sample_rate_hz", 1))
        seed = int(p.get("seed", 42))
        product_grade = str(p.get("product_grade", "POY"))
        line_speed_pct = float(p.get("line_speed_pct", 100))
        throughput_kgh = float(p.get("throughput_kgh", 2400))
        requested_target_iv = float(p.get("target_iv", 0.72))
        severity = float(p.get("fault_severity", 0.35))
        event_start_pct = float(p.get("event_start_pct", 35)) / 100.0
        event_end_pct = float(p.get("event_end_pct", 80)) / 100.0
        start_time = parse_time(p.get("start_time"))

        if product_grade not in PRODUCT_GRADES:
            raise ValueError("Unsupported product grade.")
        if duration_minutes <= 0 or sample_rate_hz <= 0:
            raise ValueError("Duration and sample rate must be positive.")

        profile = PRODUCT_PROFILES[product_grade]
        target_iv = profile.target_iv if requested_target_iv == 0.72 and product_grade != "POY" else requested_target_iv
        total_samples = max(1, int(duration_minutes * 60 * sample_rate_hz))
        total_seconds = duration_minutes * 60
        dt = 1.0 / sample_rate_hz
        event_start = total_seconds * event_start_pct
        event_end = total_seconds * event_end_pct
        if event_end < event_start:
            event_start, event_end = event_end, event_start

        rng = random.Random(seed)
        values = {tag.column: self._scaled_nominal(tag, line_speed_pct, throughput_kgh, target_iv, product_grade) for tag in TAGS}
        previous_pre_filter_dp = values["poly_pdt_232_pre_pc_filter_dp_bar"]

        for i in range(total_samples):
            elapsed = i * dt
            ts = start_time + timedelta(seconds=elapsed)
            in_event = event_start <= elapsed <= event_end
            progress = self._event_progress(elapsed, event_start, event_end)
            wave = math.sin(2 * math.pi * elapsed / max(total_seconds, 1))
            ripple = math.sin(2 * math.pi * elapsed / 180.0)
            state = "NORMAL"
            pressure_drop_active = 0
            drive_trip_active = 0
            filter_fouling_active = 0
            vacuum_loss_active = 0

            targets = {
                tag.column: self._scaled_nominal(tag, line_speed_pct, throughput_kgh, target_iv, product_grade) + self._cyclic_offset(tag, wave, ripple)
                for tag in TAGS
            }

            if in_event and request.scenario == "pressure_drop":
                state = "PRESSURE_DROP"
                pressure_drop_active = 1
                self._apply_pressure_drop(targets, severity, progress)
            elif in_event and request.scenario == "drive_trip":
                state = "DRIVE_TRIP"
                drive_trip_active = 1
                self._apply_drive_trip(targets, severity, progress)
            elif in_event and request.scenario == "filter_fouling":
                state = "FILTER_FOULING"
                filter_fouling_active = 1
                self._apply_filter_fouling(targets, severity, progress)
            elif in_event and request.scenario == "vacuum_loss":
                state = "VACUUM_LOSS"
                vacuum_loss_active = 1
                self._apply_vacuum_loss(targets, severity, progress)

            row: dict[str, Any] = {
                "timestamp": historian_datetime_text(ts),
                "scenario": request.scenario,
                "operating_state": state,
                "product_grade": product_grade,
                "batch_id": f"PF-{start_time:%Y%m%d}-{seed % 10000:04d}",
            }

            for tag in TAGS:
                values[tag.column] = lag(values[tag.column], targets[tag.column], 0.08 * dt)
                noisy_value = values[tag.column] + rng.gauss(0, tag.noise)
                row[tag.column] = round(self._bounded(tag, noisy_value), self._decimals(tag.unit))

            draw_ratio = row["draw_sic_408_roll_2_speed_mpm"] / max(float(row["draw_sic_404_roll_1_speed_mpm"]), 1.0)
            quench_balance = float(row["poy_fic_324_quench_a_flow_m3h"]) - float(row["poy_fic_327_quench_b_flow_m3h"])
            quench_total = max(float(row["poy_fic_324_quench_a_flow_m3h"]) + float(row["poy_fic_327_quench_b_flow_m3h"]), 1.0)
            estimated_denier = round(
                profile.denier_target
                * (float(row["poy_fi_317_poly_flow_a_kgh"]) / 150.0)
                / max(float(row["poy_sic_334_winder_a_speed_mpm"]) / 3250.0, 0.1),
                3,
            )
            filter_dp = float(row["poly_pdt_232_pre_pc_filter_dp_bar"])
            filter_dp_rate = (filter_dp - previous_pre_filter_dp) / max(dt / 60.0, 0.001)
            previous_pre_filter_dp = filter_dp
            melt_pressure_drop_pct = 100.0 * (
                float(row["poy_pic_307_melt_pressure_bar"]) - float(row["poy_pt_310_main_header_pressure_bar"])
            ) / max(float(row["poy_pic_307_melt_pressure_bar"]), 1.0)
            winder_slip_pct = 100.0 * (
                float(row["poy_sic_334_winder_a_speed_mpm"]) - float(row["poy_sic_332_godet_1a_speed_mpm"])
            ) / max(float(row["poy_sic_334_winder_a_speed_mpm"]), 1.0)
            row.update({
                "draw_ratio": round(draw_ratio, 4),
                "quench_flow_balance_m3h": round(quench_balance, 3),
                "quench_asymmetry_pct": round(100.0 * quench_balance / quench_total, 3),
                "iv_deviation_dl_g": round(float(row["poly_aic_332_final_iv_dl_g"]) - target_iv, 4),
                "filter_dp_rate_bar_per_min": round(filter_dp_rate, 4),
                "melt_pressure_drop_pct": round(melt_pressure_drop_pct, 3),
                "winder_slip_pct": round(winder_slip_pct, 3),
                "estimated_denier": estimated_denier,
                "estimated_tenacity_gpd": round(4.2 + (draw_ratio - profile.draw_ratio_target) * 0.45 - abs(float(row["draw_tic_402_bath_temp_c"]) - 45.0) * 0.015, 3),
                "pressure_drop_active": pressure_drop_active,
                "drive_trip_active": drive_trip_active,
                "filter_fouling_active": filter_fouling_active,
                "vacuum_loss_active": vacuum_loss_active,
                "line_trip_alarm": 1 if drive_trip_active and progress > 0.2 else 0,
            })
            row["polymer_quality_alarm"] = self._quality_alarm(row, profile)
            yield row

    def _scaled_nominal(self, tag: TagDef, line_speed_pct: float, throughput_kgh: float, target_iv: float, product_grade: str) -> float:
        profile = PRODUCT_PROFILES[product_grade]
        speed_factor = line_speed_pct / 100.0
        throughput_factor = (throughput_kgh / 2400.0) * profile.throughput_factor
        value = tag.nominal
        if "_flow_" in tag.column or tag.column.endswith("_flow_kgh") or tag.column.endswith("_flow_a_kgh"):
            value *= throughput_factor
        if "_speed_" in tag.column or tag.column.endswith("_rpm") or tag.column.endswith("_mpm"):
            value *= speed_factor
        if tag.area == "POY" and ("_speed_" in tag.column or tag.column.endswith("_mpm") or tag.column.endswith("_rpm")):
            value *= profile.poy_speed_factor
        if tag.area == "DRAW" and ("_speed_" in tag.column or tag.column.endswith("_mpm") or tag.column.endswith("_rpm")):
            value *= profile.draw_speed_factor
        if "_amp_" in tag.column or "_torque_" in tag.column:
            value *= 0.55 + 0.45 * throughput_factor
        if "quench" in tag.column and "_flow_" in tag.column:
            value *= profile.quench_factor
        if "finish_flow" in tag.column:
            value *= profile.finish_oil_factor
        if "bale_weight" in tag.column:
            value *= profile.bale_weight_factor
        if "chip_moisture" in tag.column:
            value *= profile.moisture_factor
        if "final_iv" in tag.column:
            value = target_iv
        return value

    def _cyclic_offset(self, tag: TagDef, wave: float, ripple: float) -> float:
        if "_temp_" in tag.column:
            return wave * 0.7
        if "_pressure_" in tag.column or "_press" in tag.column or "_vacuum" in tag.column:
            return ripple * max(tag.nominal * 0.01, 0.03)
        if "_flow_" in tag.column:
            return wave * max(tag.nominal * 0.01, 0.03)
        if "_speed_" in tag.column:
            return ripple * max(tag.nominal * 0.002, 0.05)
        return wave * max(tag.nominal * 0.001, 0.01)

    def _event_progress(self, elapsed: float, start: float, end: float) -> float:
        if end <= start:
            return 1.0 if elapsed >= start else 0.0
        return clamp((elapsed - start) / (end - start), 0.0, 1.0)

    def _apply_pressure_drop(self, targets: dict[str, float], severity: float, progress: float) -> None:
        hydraulic_lag = clamp((progress - 0.08) / 0.92, 0.0, 1.0)
        quality_lag = clamp((progress - 0.35) / 0.65, 0.0, 1.0)
        drop = severity * (0.35 + 0.45 * hydraulic_lag)
        for col in [
            "poy_pic_307_melt_pressure_bar",
            "poy_pt_310_main_header_pressure_bar",
            "poy_pi_315_pack_a_pressure_bar",
            "poy_pi_319_pack_b_pressure_bar",
            "poy_pic_326_quench_a_pressure_mbar",
        ]:
            targets[col] *= 1.0 - drop
        targets["poy_fic_324_quench_a_flow_m3h"] *= 1.0 - severity * 0.25 * hydraulic_lag
        targets["poy_fic_327_quench_b_flow_m3h"] *= 1.0 - severity * 0.18 * hydraulic_lag
        targets["poy_tic_325_quench_a_temp_c"] += severity * 7.0 * quality_lag
        targets["poly_aic_332_final_iv_dl_g"] -= severity * 0.015 * quality_lag

    def _apply_drive_trip(self, targets: dict[str, float], severity: float, progress: float) -> None:
        trip_curve = clamp(progress * 2.5, 0.0, 1.0)
        remaining = max(0.0, 1.0 - severity * (1.1 + trip_curve))
        for col in [
            "poy_sic_334_winder_a_speed_mpm",
            "poy_sic_332_godet_1a_speed_mpm",
            "poy_sic_333_godet_2a_speed_mpm",
            "draw_sic_423_cutter_speed_rpm",
        ]:
            targets[col] *= remaining
        targets["poy_wic_335_winder_a_tension_cn"] *= 1.0 + severity * 1.4 * trip_curve
        targets["poy_iic_309_extruder_amp_a"] *= 1.0 - severity * 0.35 * trip_curve
        targets["poy_fi_317_poly_flow_a_kgh"] *= max(0.2, 1.0 - severity * 0.65 * trip_curve)
        targets["draw_vic_407_roll_1_vibration_mms"] *= 1.0 + severity * 1.2 * trip_curve

    def _apply_filter_fouling(self, targets: dict[str, float], severity: float, progress: float) -> None:
        dp_progress = clamp(progress * 1.35, 0.0, 1.0)
        flow_progress = clamp((progress - 0.28) / 0.72, 0.0, 1.0)
        rise = 1.0 + severity * (1.2 + dp_progress)
        targets["poly_pdt_232_pre_pc_filter_dp_bar"] *= rise
        targets["poly_pdt_341_pre_cutter_filter_dp_bar"] *= rise
        targets["poy_pdt_312_filter_a_dp_bar"] *= rise
        targets["poly_fic_231_oligomer_flow_kgh"] *= 1.0 - severity * 0.18 * flow_progress
        targets["poy_fi_317_poly_flow_a_kgh"] *= 1.0 - severity * 0.15 * flow_progress
        targets["poly_aic_332_final_iv_dl_g"] -= severity * 0.012 * flow_progress

    def _apply_vacuum_loss(self, targets: dict[str, float], severity: float, progress: float) -> None:
        vacuum_progress = clamp(progress * 1.8, 0.0, 1.0)
        quality_progress = clamp((progress - 0.22) / 0.78, 0.0, 1.0)
        leak = 1.0 + severity * (1.4 + vacuum_progress)
        targets["poly_pic_311_pc1_vacuum_mbar"] *= leak
        targets["poly_pic_321_pc2_vacuum_mbar"] *= leak
        targets["poly_pic_331_finisher_vacuum_mbar"] *= leak
        targets["poly_aic_332_final_iv_dl_g"] -= severity * 0.06 * quality_progress
        targets["poly_aic_312_pc1_torque_pct"] *= 1.0 - severity * 0.18 * quality_progress

    def _quality_alarm(self, row: dict[str, Any], profile: ProductProfile) -> int:
        iv = float(row["poly_aic_332_final_iv_dl_g"])
        moisture = float(row["poly_wic_351_chip_moisture_ppm"])
        denier = float(row["estimated_denier"])
        return int(iv <= 0.635 or iv >= 0.87 or moisture > 80.0 or denier < profile.denier_low or denier > profile.denier_high)

    def _bounded(self, tag: TagDef, value: float) -> float:
        span = max(tag.high - tag.low, 0.001)
        low = 0.0 if "_speed_" in tag.column or tag.column.endswith("_rpm") or tag.column.endswith("_mpm") else tag.low - 0.25 * span
        return clamp(value, low, tag.high + 0.25 * span)

    def _decimals(self, unit: str) -> int:
        if unit in {"dL/g", "ratio"}:
            return 4
        if unit in {"bar", "mbar", "mm/s", "cpi"}:
            return 3
        if unit in {"C", "%", "A", "kg/h", "m3/h", "L/h", "m/min", "rpm", "cN", "kg", "ppm"}:
            return 2
        return 3

