from __future__ import annotations

from typing import Any, Protocol

from .models import SignalDefinition, SimulationFrame, TargetBinding, TargetRuntimeStatus


class SimulationSource(Protocol):
    @property
    def position(self) -> int: ...

    @property
    def count(self) -> int | None: ...

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def next_frame(self) -> SimulationFrame | None: ...

    async def seek(self, position: int) -> None: ...

    def schema(self) -> list[SignalDefinition]: ...


class SimulationTarget(Protocol):
    target_id: str
    binding: TargetBinding

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None: ...

    async def publish(self, frame: SimulationFrame) -> None: ...

    async def stop(self) -> None: ...

    def status(self) -> TargetRuntimeStatus: ...


class TargetFactory(Protocol):
    def __call__(self, binding: TargetBinding) -> SimulationTarget: ...


def require_config(config: dict[str, Any], key: str) -> Any:
    value = config.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"Missing required config value: {key}")
    return value
