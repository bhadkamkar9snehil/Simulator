"""Compatibility exports for unified simulation interfaces.

New interface implementations live under ``app.simulation.interfaces``. Keep
this module as a thin import surface while existing callers migrate; it must
not accumulate protocol logic again.
"""

from .interfaces import (
    HttpTarget,
    InterfaceHostManager,
    MemoryTarget,
    MqttTarget,
    OpcUaTarget,
    SqlServerTarget,
    create_target,
)
from .odata import ODataTarget

__all__ = [
    "HttpTarget",
    "InterfaceHostManager",
    "MemoryTarget",
    "MqttTarget",
    "ODataTarget",
    "OpcUaTarget",
    "SqlServerTarget",
    "create_target",
]
