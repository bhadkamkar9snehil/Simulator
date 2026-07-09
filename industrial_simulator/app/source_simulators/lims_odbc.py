from __future__ import annotations

from datetime import datetime, timedelta
from random import Random
from typing import Any

from app.source_simulators.base import SourceSimulator, apply_simple_query


PLANTS = [
    {"PlantCode": "UREA_AMM", "PlantName": "Urea / Ammonia", "SiteLocation": "Bharuch", "ProductCode": "FG-UREA", "ProductName": "Urea"},
    {"PlantCode": "ACETIC", "PlantName": "Acetic Acid", "SiteLocation": "Bharuch", "ProductCode": "FG-AA", "ProductName": "Acetic Acid"},
    {"PlantCode": "ANMELT", "PlantName": "AN Melt / Nitrophosphate", "SiteLocation": "Bharuch", "ProductCode": "FG-ANP", "ProductName": "AN Melt"},
]

PARAMETERS = [
    {"ParameterCode": "PURITY", "ParameterName": "Purity", "UOM": "%", "LSL": 98.0, "Target": 99.0, "USL": 100.0},
    {"ParameterCode": "MOISTURE", "ParameterName": "Moisture", "UOM": "%", "LSL": 0.0, "Target": 0.18, "USL": 0.40},
    {"ParameterCode": "PH", "ParameterName": "pH", "UOM": "pH", "LSL": 6.8, "Target": 7.2, "USL": 7.8},
    {"ParameterCode": "COLOR", "ParameterName": "Color Index", "UOM": "APHA", "LSL": 0.0, "Target": 12.0, "USL": 25.0},
]


class LimsOdbcSourceSimulator(SourceSimulator):
    connector_id = "lims_odbc"
    display_name = "LIMS ODBC Table Simulator"
    description = "Batch/cycle quality data exposed as SQL table and polling-view shaped rows."

    def __init__(self) -> None:
        self._clock = datetime(2026, 7, 5, 6, 0, 0)
        self._cycle = 0
        self._sample_id = 1000
        self._result_id = 5000
        self._samples: list[dict[str, Any]] = []
        self._results: list[dict[str, Any]] = []
        self._rng = Random(260705)
        for _ in range(2):
            self.run_cycle(excursion_probability=0.08)

    def spec(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "display_name": self.display_name,
            "description": self.description,
            "shape": "odbc_table_polling",
            "watermark_field": "ModifiedUTC",
            "entities": self.entities(),
        }

    def entities(self) -> list[dict[str, Any]]:
        return [
            {"entity": "dbo.SampleRegistration", "row_count": len(self._samples), "description": "Registered lab samples."},
            {"entity": "dbo.TestResult", "row_count": len(self._results), "description": "One approved test result per sample parameter."},
            {"entity": "dbo.vw_LatestQualityResults", "row_count": len(self._latest_quality_rows()), "description": "Latest approved quality result per plant/product/parameter."},
            {"entity": "dbo.vw_QualityExcursions", "row_count": len(self._excursion_rows()), "description": "Fail and marginal approved quality results."},
        ]

    def run_cycle(self, **kwargs: Any) -> dict[str, Any]:
        probability = float(kwargs.get("excursion_probability", 0.05))
        samples_before = len(self._samples)
        results_before = len(self._results)
        self._cycle += 1
        self._clock += timedelta(minutes=15)
        for plant in PLANTS:
            self._add_sample(plant, probability)
        return {
            "status": "completed",
            "cycle": self._cycle,
            "samples_created": len(self._samples) - samples_before,
            "results_created": len(self._results) - results_before,
            "modified_utc": self._clock.isoformat(timespec="milliseconds") + "Z",
        }

    def query(
        self,
        entity: str,
        filter_text: str = "",
        top: int | None = None,
        skip: int = 0,
        watermark: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._entity_rows(entity)
        return apply_simple_query(rows, filter_text=filter_text, top=top, skip=skip, watermark=watermark)

    def _add_sample(self, plant: dict[str, Any], excursion_probability: float) -> None:
        self._sample_id += 1
        now = self._clock
        sample_code = f"{plant['PlantCode']}-{now:%Y%m%d%H%M%S}-{self._cycle:03d}"
        sample = {
            "SampleID": self._sample_id,
            "SampleCode": sample_code,
            "PlantCode": plant["PlantCode"],
            "PlantName": plant["PlantName"],
            "SiteLocation": plant["SiteLocation"],
            "ProductCode": plant["ProductCode"],
            "ProductName": plant["ProductName"],
            "BatchNo": f"B{now:%Y%m%d}-{self._cycle:03d}",
            "SamplePoint": "Product Discharge / Bagging Point",
            "SampleType": "Finished Product",
            "CollectedDateTime": (now - timedelta(minutes=18)).isoformat(timespec="seconds"),
            "ReceivedDateTime": (now - timedelta(minutes=10)).isoformat(timespec="seconds"),
            "Status": "Approved",
            "ModifiedUTC": now.isoformat(timespec="milliseconds") + "Z",
        }
        self._samples.append(sample)
        for parameter in PARAMETERS:
            self._result_id += 1
            value, status = self._quality_value(parameter, excursion_probability)
            self._results.append(
                {
                    "ResultID": self._result_id,
                    "SampleID": self._sample_id,
                    "SampleCode": sample_code,
                    "PlantCode": plant["PlantCode"],
                    "PlantName": plant["PlantName"],
                    "SiteLocation": plant["SiteLocation"],
                    "ProductCode": plant["ProductCode"],
                    "ProductName": plant["ProductName"],
                    "ParameterCode": parameter["ParameterCode"],
                    "ParameterName": parameter["ParameterName"],
                    "UOM": parameter["UOM"],
                    "LSL": parameter["LSL"],
                    "Target": parameter["Target"],
                    "USL": parameter["USL"],
                    "BatchNo": sample["BatchNo"],
                    "SamplePoint": sample["SamplePoint"],
                    "CollectedDateTime": sample["CollectedDateTime"],
                    "ResultValue": value,
                    "ResultStatus": status,
                    "AnalystName": self._rng.choice(["R. Patel", "S. Iyer", "M. Shaikh", "A. Verma"]),
                    "AnalyzedDateTime": now.isoformat(timespec="seconds"),
                    "IsApproved": True,
                    "ModifiedUTC": (now + timedelta(milliseconds=self._result_id % 997)).isoformat(timespec="milliseconds") + "Z",
                }
            )

    def _quality_value(self, parameter: dict[str, Any], excursion_probability: float) -> tuple[float, str]:
        target = float(parameter["Target"])
        low = float(parameter["LSL"])
        high = float(parameter["USL"])
        band = max(high - low, abs(target) * 0.1, 0.1)
        if self._rng.random() < excursion_probability:
            value = low - band * self._rng.uniform(0.02, 0.18) if self._rng.random() < 0.5 else high + band * self._rng.uniform(0.02, 0.18)
        else:
            value = target + self._rng.uniform(-0.18, 0.18) * band
        if value < low or value > high:
            status = "Fail"
        elif value < low + band * 0.10 or value > high - band * 0.10:
            status = "Marginal"
        else:
            status = "Pass"
        return round(value, 4), status

    def _entity_rows(self, entity: str) -> list[dict[str, Any]]:
        if entity == "dbo.SampleRegistration":
            return list(self._samples)
        if entity == "dbo.TestResult":
            return list(self._results)
        if entity == "dbo.vw_LatestQualityResults":
            return self._latest_quality_rows()
        if entity == "dbo.vw_QualityExcursions":
            return self._excursion_rows()
        raise KeyError(f"Unknown LIMS ODBC entity: {entity}")

    def _latest_quality_rows(self) -> list[dict[str, Any]]:
        latest: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in self._results:
            key = (row["PlantCode"], row["ProductCode"], row["ParameterCode"])
            current = latest.get(key)
            if current is None or row["AnalyzedDateTime"] > current["AnalyzedDateTime"]:
                latest[key] = row
        return sorted(latest.values(), key=lambda row: (row["PlantCode"], row["ProductCode"], row["ParameterCode"]))

    def _excursion_rows(self) -> list[dict[str, Any]]:
        return [row for row in self._results if row["ResultStatus"] in {"Fail", "Marginal"} and row["IsApproved"]]
