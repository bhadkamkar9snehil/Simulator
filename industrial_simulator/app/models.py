from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

DataType = Literal["Double", "Int64", "Boolean", "String"]
LoopMode = Literal["loop_forever", "once", "hold_last", "ping_pong"]
TimestampMode = Literal["wall_clock", "csv_timestamp_ignore_rate", "relative_from_csv"]
SimulatorState = Literal["idle", "configured", "running", "stopped", "completed", "error"]
CsvSource = Literal["uploaded", "generated", "sample"]
ProtocolMode = Literal["opcua", "mqtt", "both"]
TagProtocol = Literal["opcua", "mqtt"]


class ScenarioSpec(BaseModel):
    id: str
    label: str
    description: str | None = None


class ParameterSpec(BaseModel):
    name: str
    label: str
    type: Literal["number", "select", "text", "datetime"] = "text"
    unit: str | None = None
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    required: bool = True
    options: list[Any] | None = None
    description: str | None = None


class GeneratorSpec(BaseModel):
    domain_id: str
    display_name: str
    description: str
    scenarios: list[ScenarioSpec]
    parameters: list[ParameterSpec]
    default_output_filename: str


class GeneratorSummary(BaseModel):
    domain_id: str
    display_name: str
    description: str


class GenerateRequest(BaseModel):
    scenario: str
    output_filename: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    load_into_replay: bool = False


class GenerateResponse(BaseModel):
    status: str
    filename: str
    source: CsvSource = "generated"
    row_count: int
    column_count: int
    columns: list[str]
    preview: list[dict[str, Any]] = Field(default_factory=list)
    loaded_into_replay: bool = False
    default_tag_mappings: list["TagMapping"] = Field(default_factory=list)


class CsvFileRecord(BaseModel):
    filename: str
    source: CsvSource
    path: str
    row_count: int
    column_count: int
    modified_at: str


class CsvMetadata(BaseModel):
    filename: str
    source: CsvSource
    row_count: int
    column_count: int
    columns: list[str]
    preview: list[dict[str, Any]] = Field(default_factory=list)
    inferred_types: dict[str, DataType] = Field(default_factory=dict)
    modified_at: str | None = None
    default_tag_mappings: list["TagMapping"] = Field(default_factory=list)


class CsvPreviewResponse(BaseModel):
    filename: str
    source: CsvSource
    columns: list[str]
    rows: list[dict[str, Any]]


class TagMapping(BaseModel):
    enabled: bool = True
    csv_column: str
    tag_name: str
    node_id: str
    data_type: DataType = "String"
    initial_value: Any = None
    writable: bool = False


class ReplayConfig(BaseModel):
    protocol: ProtocolMode = "opcua"
    csv_file: str
    csv_source: CsvSource = "generated"
    frequency_hz: float = Field(default=1.0, gt=0)
    loop_mode: LoopMode = "loop_forever"
    timestamp_mode: TimestampMode = "wall_clock"
    start_row: int = Field(default=0, ge=0)
    # Legacy naming fields are kept for config compatibility and default mapping display.
    namespace_uri: str = "http://local/industrial-tag-simulator"
    root_folder: str = "TagSimulator"
    node_id_prefix: str = "TagSimulator"
    max_rows: int | None = None

    # MQTT connection and publish settings.
    mqtt_host: str = "localhost"
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_topic_prefix: str = "industrial-tag-simulator"
    mqtt_device_id: str = "FlowMeter01"
    mqtt_client_id: str = "industrial-tag-simulator"
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_qos: int = Field(default=0, ge=0, le=2)
    mqtt_retain: bool = False
    publish_individual_tags: bool = True
    publish_aggregate: bool = True

    tags: list[TagMapping]

    @field_validator("tags")
    @classmethod
    def must_have_enabled_tags(cls, tags: list[TagMapping]) -> list[TagMapping]:
        if not any(t.enabled for t in tags):
            raise ValueError("At least one tag must be enabled.")
        return tags


class ReplayFileSelection(BaseModel):
    filename: str
    source: CsvSource = "uploaded"


class ProtocolTagSelection(BaseModel):
    protocol: TagProtocol
    filename: str
    source: CsvSource = "uploaded"
    csv_column: str
    enabled: bool = True


class ReplayFilesConfig(BaseModel):
    protocol: ProtocolMode = "opcua"
    # Backward-compatible shared selection. For OPC UA-only and MQTT-only this is
    # the active file list. For BOTH mode it is used when protocol-specific lists
    # are not provided.
    files: list[ReplayFileSelection] = Field(default_factory=list)
    # Optional protocol-specific selections. These enable OPC UA to replay one
    # group of Excel/CSV files while MQTT replays a different group at the same
    # time.
    opcua_files: list[ReplayFileSelection] = Field(default_factory=list)
    mqtt_files: list[ReplayFileSelection] = Field(default_factory=list)
    frequency_hz: float = Field(default=1.0, gt=0)
    loop_mode: LoopMode = "loop_forever"
    timestamp_mode: TimestampMode = "wall_clock"
    start_row: int = Field(default=0, ge=0)
    max_rows: int | None = None
    namespace_uri: str = "http://local/industrial-tag-simulator"
    root_folder: str = "TagSimulator"
    node_id_prefix: str = "TagSimulator"
    mqtt_host: str = "localhost"
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_topic_prefix: str = "industrial-tag-simulator"
    mqtt_device_id: str = "FlowMeter01"
    mqtt_client_id: str = "industrial-tag-simulator"
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_qos: int = Field(default=0, ge=0, le=2)
    mqtt_retain: bool = False
    publish_individual_tags: bool = True
    publish_aggregate: bool = True
    # Optional per-protocol tag enable/disable list generated by the UI tag-plan preview.
    # Missing selections default to enabled so older configs still run exactly as before.
    tag_selections: list[ProtocolTagSelection] = Field(default_factory=list)



class ReplayStatus(BaseModel):
    state: SimulatorState = "idle"
    protocol: ProtocolMode | None = None
    configured: bool = False
    csv_file: str | None = None
    csv_source: CsvSource | None = None
    frequency_hz: float | None = None
    cursor: int = 0
    row_count: int = 0
    tag_count: int = 0
    loop_mode: LoopMode | None = None
    timestamp_mode: TimestampMode | None = None
    last_error: str | None = None


class CurrentValue(BaseModel):
    tag_name: str
    node_id: str
    value: Any
    data_type: DataType
    last_updated: str


class CurrentValuesResponse(BaseModel):
    updated_at: str | None = None
    values: list[CurrentValue] = Field(default_factory=list)


class SavedConfig(BaseModel):
    name: str
    description: str = ""
    created_at: str | None = None
    modified_at: str | None = None
    generator: dict[str, Any] | None = None
    csv: dict[str, Any] | None = None
    replay: dict[str, Any] | None = None


class ConfigSummary(BaseModel):
    name: str
    description: str = ""
    created_at: str | None = None
    modified_at: str | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
