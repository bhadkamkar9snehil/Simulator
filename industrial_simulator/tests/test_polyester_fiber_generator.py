from app.generators.polyester_fiber import PolyesterFiberGenerator
from app.models import GenerateRequest
from app.type_inference import infer_types, is_default_disabled_column


def make_request(scenario: str, **params):
    base = {
        "duration_minutes": 5,
        "sample_rate_hz": 1,
        "seed": 7,
        "event_start_pct": 20,
        "event_end_pct": 80,
        "fault_severity": 0.6,
    }
    base.update(params)
    return GenerateRequest(scenario=scenario, output_filename="polyester.csv", parameters=base)


def test_polyester_generator_exposes_core_process_columns() -> None:
    rows = PolyesterFiberGenerator().generate(make_request("normal"))

    assert rows
    assert {
        "poly_tic_201_es1_temp_c",
        "poly_pic_331_finisher_vacuum_mbar",
        "poy_pic_307_melt_pressure_bar",
        "poy_sic_334_winder_a_speed_mpm",
        "draw_sic_408_roll_2_speed_mpm",
        "draw_ratio",
        "iv_deviation_dl_g",
        "filter_dp_rate_bar_per_min",
        "melt_pressure_drop_pct",
        "winder_slip_pct",
        "polymer_quality_alarm",
    } <= set(rows[0])


def test_pressure_drop_lowers_polymer_header_pressure() -> None:
    normal = PolyesterFiberGenerator().generate(make_request("normal"))
    pressure_drop = PolyesterFiberGenerator().generate(make_request("pressure_drop"))

    normal_min = min(float(row["poy_pt_310_main_header_pressure_bar"]) for row in normal)
    event_rows = [row for row in pressure_drop if row["pressure_drop_active"] == 1]
    assert event_rows
    assert min(float(row["poy_pt_310_main_header_pressure_bar"]) for row in event_rows) < normal_min * 0.85


def test_drive_trip_drops_winder_speed_and_raises_alarm() -> None:
    rows = PolyesterFiberGenerator().generate(make_request("drive_trip"))
    event_rows = [row for row in rows if row["drive_trip_active"] == 1]

    assert event_rows
    assert min(float(row["poy_sic_334_winder_a_speed_mpm"]) for row in event_rows) < 1800
    assert any(row["line_trip_alarm"] == 1 for row in rows)


def test_product_grade_changes_process_profile_without_quality_alarm() -> None:
    poy = PolyesterFiberGenerator().generate(make_request("normal", product_grade="POY"))
    psf = PolyesterFiberGenerator().generate(make_request("normal", product_grade="PSF"))
    hi_iv = PolyesterFiberGenerator().generate(make_request("normal", product_grade="Hi-IV"))

    assert float(hi_iv[0]["poly_aic_332_final_iv_dl_g"]) > float(poy[0]["poly_aic_332_final_iv_dl_g"])
    assert float(psf[0]["draw_sic_408_roll_2_speed_mpm"]) > float(poy[0]["draw_sic_408_roll_2_speed_mpm"])
    assert float(psf[0]["estimated_denier"]) > float(poy[0]["estimated_denier"])
    assert not any(row["polymer_quality_alarm"] for row in psf)


def test_filter_fouling_raises_dp_before_flow_loss() -> None:
    rows = PolyesterFiberGenerator().generate(make_request("filter_fouling"))
    event_rows = [row for row in rows if row["filter_fouling_active"] == 1]

    assert event_rows
    assert max(float(row["poly_pdt_232_pre_pc_filter_dp_bar"]) for row in event_rows) > 3.0
    assert max(float(row["filter_dp_rate_bar_per_min"]) for row in event_rows) > 0
    assert min(float(row["poy_fi_317_poly_flow_a_kgh"]) for row in event_rows) < float(rows[0]["poy_fi_317_poly_flow_a_kgh"])


def test_vacuum_loss_degrades_iv_after_vacuum_moves() -> None:
    rows = PolyesterFiberGenerator().generate(make_request("vacuum_loss"))
    event_rows = [row for row in rows if row["vacuum_loss_active"] == 1]

    assert event_rows
    assert max(float(row["poly_pic_331_finisher_vacuum_mbar"]) for row in event_rows) > float(rows[0]["poly_pic_331_finisher_vacuum_mbar"]) * 1.4
    assert min(float(row["iv_deviation_dl_g"]) for row in event_rows) < -0.005


def test_polyester_generator_streams_full_spec_without_domain_cap() -> None:
    request = make_request("normal", duration_minutes=1440, sample_rate_hz=10)

    rows = PolyesterFiberGenerator().iter_rows(request)
    first = next(rows)
    second = next(rows)

    assert first["timestamp"] == "2026-01-01 00:00:00.000"
    assert second["timestamp"] == "2026-01-01 00:00:00.100"
    assert "line_trip_alarm" in first
    assert "polymer_quality_alarm" in first


def test_traceability_and_alarm_columns_are_default_live_tags() -> None:
    rows = PolyesterFiberGenerator().generate(make_request("normal", duration_minutes=1))
    columns = list(rows[0])
    inferred = infer_types(rows, columns)

    assert inferred["product_grade"] == "String"
    assert inferred["batch_id"] == "String"
    assert inferred["line_trip_alarm"] == "Boolean"
    assert inferred["pressure_drop_active"] == "Boolean"
    assert not is_default_disabled_column("product_grade")
    assert not is_default_disabled_column("batch_id")
    assert not is_default_disabled_column("line_trip_alarm")
    assert not is_default_disabled_column("pressure_drop_active")
    assert not is_default_disabled_column("poy_pic_307_melt_pressure_bar")
