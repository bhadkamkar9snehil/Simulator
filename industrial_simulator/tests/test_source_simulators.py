import time

from fastapi.testclient import TestClient

from app import job_manager
from app.http_streams import stream_snapshot
from app.models import CurrentValuesResponse
from app.source_simulators.jobs import start_source_job, stop_source_job
from app.source_simulators.lims_odbc import LimsOdbcSourceSimulator
from app.source_simulators.sap_pp import SapPpSourceSimulator
from main import app


class EmptyReplaySimulator:
    def get_current_values(self) -> CurrentValuesResponse:
        return CurrentValuesResponse(updated_at=None, values=[])

    def get_status(self) -> dict:
        return {"state": "idle", "assignment_mode": "test", "file_count": 0}


class EmptyProtocolAdapter:
    def get_status(self) -> dict:
        return {"active_protocol": "none"}


def test_sap_pp_query_filters_and_pages() -> None:
    sim = SapPpSourceSimulator()

    rows = sim.query("A_ProductionOrder", filter_text="Product eq 'FG-UREA'", top=1)

    assert len(rows) == 1
    assert rows[0]["Product"] == "FG-UREA"
    assert rows[0]["OrderID"].startswith("PO-FG-UREA")


def test_sap_pp_variance_calculates_capacity_and_efficiency() -> None:
    sim = SapPpSourceSimulator()

    rows = sim.query("A_ProductionVariance", filter_text="OrderID eq 'PO-FG-UREA-2026-04'")

    assert rows
    row = rows[0]
    assert row["CapacityUtilizationPct"] == 92.67
    assert row["RawMaterialEfficiencyVariancePerUnit"] < 0
    assert row["UtilitiesEfficiencyVariancePerUnit"] < 0


def test_sap_pp_direct_odata_endpoint_and_error_hook() -> None:
    client = TestClient(app)

    response = client.get("/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV/A_ProductionOrder?$top=2")
    error = client.get("/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV/A_ProductionOrder?simulate_error=true")

    assert response.status_code == 200
    payload = response.json()
    assert "d" in payload
    assert len(payload["d"]["results"]) == 2
    assert error.status_code == 503


def test_lims_cycle_latest_excursions_and_watermark() -> None:
    sim = LimsOdbcSourceSimulator()
    before = sim.query("dbo.TestResult")

    cycle = sim.run_cycle(excursion_probability=1.0)
    after = sim.query("dbo.TestResult")
    latest = sim.query("dbo.vw_LatestQualityResults")
    excursions = sim.query("dbo.vw_QualityExcursions")
    newer = sim.query("dbo.TestResult", watermark=max(row["ModifiedUTC"] for row in before))

    assert cycle["samples_created"] == 3
    assert len(after) == len(before) + 12
    assert latest
    assert excursions
    assert newer
    assert all(row["ModifiedUTC"] > max(item["ModifiedUTC"] for item in before) for row in newer)


def test_source_simulation_jobs_run_independently_to_completion() -> None:
    sap_job = start_source_job("sap_pp", "A_ProductionOrder", interval_seconds=0.01, max_cycles=2, top=1)
    lims_job = start_source_job("lims_odbc", "dbo.vw_LatestQualityResults", interval_seconds=0.01, max_cycles=2, mode="cycle", top=2, cycle_parameters={"excursion_probability": 0.1})

    deadline = time.time() + 5
    while time.time() < deadline:
        sap = job_manager.get_job(sap_job.job_id)
        lims = job_manager.get_job(lims_job.job_id)
        if sap.state == "completed" and lims.state == "completed":
            break
        time.sleep(0.05)

    sap = job_manager.get_job(sap_job.job_id)
    lims = job_manager.get_job(lims_job.job_id)
    assert sap.state == "completed"
    assert lims.state == "completed"
    assert sap.rows_done == 2
    assert lims.rows_done >= 4
    assert sap.checkpoint["cycles"] == 2
    assert lims.checkpoint["cycles"] == 2

    stopped_after_complete = stop_source_job(sap_job.job_id)
    assert stopped_after_complete.state == "completed"
    assert stopped_after_complete.current_step == sap.current_step


def test_source_jobs_api_starts_job() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/source-simulators/sap_pp/jobs",
        json={"entity": "A_ProductionOrder", "interval_seconds": 0.01, "max_cycles": 1, "top": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "source_simulation"
    assert payload["name"].startswith("SAP PP OData Simulator")


def test_source_job_outputs_are_visible_in_stream_snapshot() -> None:
    job = start_source_job("sap_pp", "A_ProductionOrder", interval_seconds=0.01, max_cycles=1, top=2)

    deadline = time.time() + 5
    while time.time() < deadline:
        current = job_manager.get_job(job.job_id)
        if current.state == "completed":
            break
        time.sleep(0.05)

    current = job_manager.get_job(job.job_id)
    snapshot = stream_snapshot(EmptyReplaySimulator(), EmptyProtocolAdapter(), value_limit=2)
    source_item = next(item for item in snapshot["source_outputs"]["items"] if item["job_id"] == job.job_id)

    assert current.state == "completed"
    assert current.checkpoint["last_rows"] == 2
    assert len(current.checkpoint["last_rows_sample"]) == 2
    assert current.checkpoint["last_rows_sample"][0]["OrderID"].startswith("PO-")
    assert snapshot["source_outputs"]["total"] >= 1
    assert source_item["connector_id"] == "sap_pp"
    assert source_item["entity"] == "A_ProductionOrder"
    assert len(source_item["sample"]) == 2
