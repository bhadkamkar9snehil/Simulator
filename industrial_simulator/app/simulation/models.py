from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import DataType


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class SignalValue(BaseModel):
    value: Any = None
    data_type: DataType = "String"
    quality: str = "GOOD"
    unit: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalDefinition(BaseModel):
    name: str
    node_id: str
    data_type: DataType = "String"
    initial_value: Any = None
    unit: str | None = None
    writable: bool = False


class SignalMapping(BaseModel):
    source: str
    target: str | None = None
    node_id: str | None = None
    enabled: bool = True
    data_type: DataType | None = None
    unit: str | None = None
    quality: str | None = None
    scale: float = 1.0
    offset: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source")
    @classmethod
    def source_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Signal mapping source is required.")
        return value

    @field_validator("target", "node_id")
    @classmethod
    def empty_optional_text_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class SimulationFrame(BaseModel):
    simulation_id: str
    sequence: int = Field(default=0, ge=0)
    timestamp: str = Field(default_factory=utc_now_iso)
    source_timestamp: str | None = None
    values: dict[str, SignalValue] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class SourceBinding(BaseModel):
    kind: str
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Source kind is required.")
        return normalized


class TargetBinding(BaseModel):
    target_id: str = Field(default_factory=lambda: _new_id("target"), pattern=r"^[A-Za-z0-9_.-]+$")
    kind: str
    hosting_mode: Literal["shared", "dedicated"] = "shared"
    enabled: bool = True
    failure_policy: Literal["continue", "retry", "stop_simulation"] = "continue"
    queue_size: int = Field(default=256, ge=1, le=100_000)
    overflow_policy: Literal["block", "drop_oldest", "drop_newest"] = "drop_oldest"
    retry_seconds: float = Field(default=1.0, ge=0.05, le=300.0)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Target kind is required.")
        return normalized


class ClockSpec(BaseModel):
    mode: Literal["fixed_rate", "source_timestamp"] = "fixed_rate"
    frequency_hz: float = Field(default=1.0, gt=0)
    speed: float = Field(default=1.0, gt=0)
    max_delay_seconds: float = Field(default=60.0, gt=0)


class SimulationDefinition(BaseModel):
    simulation_id: str = Field(default_factory=lambda: _new_id("sim"), pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = "Simulation"
    source: SourceBinding
    mappings: list[SignalMapping] = Field(default_factory=list)
    drop_unmapped_signals: bool = False
    clock: ClockSpec = Field(default_factory=ClockSpec)
    loop_mode: Literal["once", "loop_forever", "hold_last", "ping_pong"] = "loop_forever"
    targets: list[TargetBinding] = Field(default_factory=list)
    world_id: str | None = None
    autostart: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_targets_and_mappings(self) -> "SimulationDefinition":
        enabled = [target for target in self.targets if target.enabled]
        if not enabled:
            raise ValueError("At least one enabled target is required.")
        target_ids = [target.target_id for target in self.targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("Target ids must be unique within a simulation.")
        mapped_targets = [mapping.target or mapping.source for mapping in self.mappings if mapping.enabled]
        if len(mapped_targets) != len(set(mapped_targets)):
            raise ValueError("Enabled signal mappings must produce unique target names.")
        return self


class TargetRuntimeStatus(BaseModel):
    target_id: str
    kind: str
    state: Literal["created", "starting", "running", "error", "stopped"] = "created"
    endpoint: str | None = None
    queue_depth: int = 0
    dropped_frames: int = 0
    published_frames: int = 0
    retry_count: int = 0
    last_success_at: str | None = None
    last_latency_ms: float | None = None
    last_error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SimulationStatus(BaseModel):
    simulation_id: str
    name: str
    state: Literal["created", "starting", "running", "paused", "stopped", "completed", "degraded", "error"]
    world_id: str | None = None
    emitted_count: int = 0
    source_position: int = 0
    source_count: int | None = None
    started_at: str | None = None
    updated_at: str | None = None
    last_error: str | None = None
    targets: list[TargetRuntimeStatus] = Field(default_factory=list)


class WorldDefinition(BaseModel):
    world_id: str = Field(default_factory=lambda: _new_id("world"), pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = "World"
    simulation_ids: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("simulation_ids")
    @classmethod
    def unique_members(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("World simulation_ids must be unique.")
        return values


class RuntimeSnapshot(BaseModel):
    simulations: list[SimulationStatus] = Field(default_factory=list)
    worlds: list[WorldDefinition] = Field(default_factory=list)
    persistence_error: str | None = None
