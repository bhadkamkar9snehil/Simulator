from __future__ import annotations

from ..models import SignalDefinition, SimulationFrame, TargetBinding, TargetRuntimeStatus


class MemoryTarget:
    """In-process target used for diagnostics, tests, and API-only simulations."""

    def __init__(self, binding: TargetBinding):
        self.target_id = binding.target_id
        self.binding = binding
        self.last_frame: SimulationFrame | None = None
        self._state = "created"

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None:
        self._state = "running"

    async def publish(self, frame: SimulationFrame) -> None:
        self.last_frame = frame

    async def stop(self) -> None:
        self._state = "stopped"

    def status(self) -> TargetRuntimeStatus:
        return TargetRuntimeStatus(
            target_id=self.target_id,
            kind="memory",
            state=self._state,  # type: ignore[arg-type]
            endpoint=f"memory://{self.target_id}",
        )
