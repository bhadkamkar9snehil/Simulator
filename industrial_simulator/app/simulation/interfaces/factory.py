from __future__ import annotations

from ..contracts import SimulationTarget
from ..models import TargetBinding
from ..odata import ODataTarget
from .http import HttpTarget
from .memory import MemoryTarget
from .mqtt import MqttTarget
from .opcua import InterfaceHostManager, OpcUaTarget
from .sql_server import SqlServerTarget


def create_target(binding: TargetBinding, hosts: InterfaceHostManager) -> SimulationTarget:
    kind = binding.kind
    if kind == "opcua":
        return OpcUaTarget(binding, hosts)
    if kind == "mqtt":
        return MqttTarget(binding)
    if kind in {"sql", "sql_server", "mssql"}:
        return SqlServerTarget(binding)
    if kind in {"odata", "sap_odata"}:
        return ODataTarget(binding)
    if kind in {"http", "http_stream"}:
        return HttpTarget(binding)
    if kind in {"memory", "internal"}:
        return MemoryTarget(binding)
    raise ValueError(f"Unsupported simulation target kind: {kind}")
