from __future__ import annotations

from app.source_simulators.base import SourceSimulator
from app.source_simulators.lims_odbc import LimsOdbcSourceSimulator
from app.source_simulators.sap_pp import SapPpSourceSimulator

_SOURCES: dict[str, SourceSimulator] = {
    "sap_pp": SapPpSourceSimulator(),
    "lims_odbc": LimsOdbcSourceSimulator(),
}


def list_source_simulators() -> list[SourceSimulator]:
    return list(_SOURCES.values())


def get_source_simulator(connector_id: str) -> SourceSimulator:
    if connector_id not in _SOURCES:
        raise KeyError(f"Unknown source simulator: {connector_id}")
    return _SOURCES[connector_id]
