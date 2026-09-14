from __future__ import annotations

from ..models import SignalDefinition, SimulationFrame, TargetBinding, TargetRuntimeStatus


class HttpTarget:
    """Per-simulation view on the shared Industrial FastAPI host."""

    def __init__(self, binding: TargetBinding):
        self.target_id = binding.target_id
        self.binding = binding
        self._state = "created"
        self._endpoint: str | None = None
        self.last_frame: SimulationFrame | None = None

    async def start(self, simulation_id: str, simulation_name: str, schema: list[SignalDefinition]) -> None:
        if self.binding.hosting_mode != "shared":
            raise ValueError("HTTP target currently supports shared hosting only.")
        self._endpoint = f"/api/v2/simulations/{simulation_id}/targets/{self.target_id}"
        self._state = "running"

    async def publish(self, frame: SimulationFrame) -> None:
        self.last_frame = frame

    async def stop(self) -> None:
        self._state = "stopped"

    def status(self) -> TargetRuntimeStatus:
        return TargetRuntimeStatus(
            target_id=self.target_id,
            kind="http",
            state=self._state,  # type: ignore[arg-type]
            endpoint=self._endpoint,
            details={"last_sequence": self.last_frame.sequence if self.last_frame else None},
        )
