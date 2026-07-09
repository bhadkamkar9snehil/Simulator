from app.generator_registry import get_generator, list_generators
from app.generators.gnfc_chemical_process import GnfcChemicalProcessGenerator
from app.models import GenerateRequest


def request(scenario: str, **params):
    payload = {
        "duration_minutes": 5,
        "sample_rate_hz": 1,
        "seed": 11,
        "product": "FG-UREA",
        "period": "2026-04",
        "fault_severity": 0.5,
        "event_start_pct": 20,
        "event_end_pct": 80,
    }
    payload.update(params)
    return GenerateRequest(scenario=scenario, output_filename="gnfc.csv", parameters=payload)


def test_registry_contains_gnfc_chemical_process() -> None:
    ids = {item.domain_id for item in list_generators()}

    assert "gnfc_chemical_process" in ids
    assert get_generator("gnfc_chemical_process").domain_id == "gnfc_chemical_process"


def test_gnfc_generator_exposes_sap_join_keys_and_process_columns() -> None:
    rows = GnfcChemicalProcessGenerator().generate(request("normal"))

    assert rows
    assert {
        "Plant",
        "Product",
        "OrderID",
        "BatchID",
        "production_rate_tph",
        "confirmed_yield_t",
        "scrap_t",
        "raw_material_rate_tph",
        "utilities_rate_gjph",
        "capacity_utilization_pct",
        "quality_margin_pct",
        "process_alarm",
    } <= set(rows[0])
    assert rows[0]["Product"] == "FG-UREA"
    assert rows[0]["OrderID"] == "PO-FG-UREA-2026-04"


def test_gnfc_feed_shortage_and_quality_excursion_raise_expected_flags() -> None:
    feed_shortage = GnfcChemicalProcessGenerator().generate(request("feed_shortage"))
    quality = GnfcChemicalProcessGenerator().generate(request("quality_excursion", fault_severity=1.0))

    assert any(row["feed_shortage_active"] == 1 for row in feed_shortage)
    assert any(row["process_alarm"] == 1 for row in feed_shortage)
    assert any(row["quality_excursion_active"] == 1 for row in quality)
    assert min(float(row["quality_margin_pct"]) for row in quality) < 18.0
