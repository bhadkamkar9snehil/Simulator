from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

DataType = str
OPCUA_DATA_TYPES = {
    "Boolean", "SByte", "Byte", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64",
    "Float", "Double", "String", "DateTime", "Guid", "ByteString", "XmlElement", "NodeId",
    "QualifiedName", "LocalizedText", "StatusCode",
}
LoopMode = Literal["loop_forever", "once", "hold_last", "ping_pong"]
TimestampMode = Literal["wall_clock", "csv_timestamp_ignore_rate", "relative_from_csv"]
SimulatorState = Literal["idle", "configured", "running", "stopped", "completed", "error"]
CsvSource = Literal["uploaded", "generated", "sample"]
ProtocolMode = Literal["opcua", "mqtt", "both"]
TagProtocol = Literal["opcua", "mqtt"]
DatasetState = Literal["registered", "scanning", "ready", "generating", "converting", "partial", "failed", "cancelled", "deleted"]
DatasetSource = Literal["generated", "uploaded", "registered", "lakehouse", "converted", "sample"]
StorageFormat = Literal["csv", "xlsx", "jsonl", "ndjson", "parquet", "parquet_folder"]
JobState = Literal["queued", "running", "paused", "completed", "failed", "cancelled", "partial", "cleanup_required"]
JobType = Literal["generate_dataset", "scan_dataset", "convert_dataset", "replay_dataset", "lakehouse_write", "sql_projection", "video_generation", "stream_ingest", "source_simulation"]
TargetBasis = Literal["physical_bytes", "logical_bytes", "stream_bytes", "rows", "duration"]
OutputFormat = Literal["csv", "parquet", "lakehouse"]
SpeedMode = Literal["max_throughput", "realistic_rate"]
SchemaPolicy = Literal["fail", "quarantine"]


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


class GenerateJobRequest(BaseModel):
    scenario: str
    name: str = "Generated dataset"
    output_format: OutputFormat = "parquet"
    parameters: dict[str, Any] = Field(default_factory=dict)
    target_basis: TargetBasis = "physical_bytes"
    target_value: int | float | None = None
    speed_mode: SpeedMode = "max_throughput"
    rows_per_batch: int = Field(default=10000, ge=1)
    rows_per_part: int = Field(default=1_000_000, ge=1)
    compression: str = "zstd"
    partition_columns: list[str] = Field(default_factory=list)
    output_sinks: list[str] = Field(default_factory=lambda: ["dataset"])
    schema_policy: SchemaPolicy = "fail"
    checkpoint_interval_parts: int = Field(default=1, ge=1)
    lakehouse_root: str | None = None
    sql_projection: dict[str, Any] | None = None
    video: dict[str, Any] | None = None


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
    quality: str | int = "Good"
    quality_column: str | None = None
    source_timestamp: Any = None
    source_timestamp_column: str | None = None

    @field_validator("data_type")
    @classmethod
    def valid_opcua_data_type(cls, value: str) -> str:
        text = str(value or "String").strip()
        base = text[:-2] if text.endswith("[]") else (text[6:-1].strip() if text.startswith("Array[") and text.endswith("]") else text)
        if base not in OPCUA_DATA_TYPES:
            raise ValueError(f"Unsupported OPC UA datatype: {value}")
        return text


class ReplayConfig(BaseModel):
    protocol: ProtocolMode = "opcua"
    csv_file: str = ""
    csv_source: CsvSource = "generated"
    dataset_id: str | None = None
    frequency_hz: float = Field(default=1.0, gt=0)
    loop_mode: LoopMode = "loop_forever"
    timestamp_mode: TimestampMode = "wall_clock"
    start_row: int = Field(default=0, ge=0)
    namespace_uri: str = "http://local/industrial-tag-simulator"
    root_folder: str = "TagSimulator"
    node_id_prefix: str = "TagSimulator"
    max_rows: int | None = None
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


class WorkloadReplayOptions(BaseModel):
    enabled: bool = True
    dataset_id: str | None = None
    csv_file: str = "sample_pipeline_normal.csv"
    csv_source: CsvSource = "sample"
    protocol: ProtocolMode = "both"
    frequency_hz: float = Field(default=5.0, gt=0)
    loop_mode: LoopMode = "loop_forever"
    timestamp_mode: TimestampMode = "wall_clock"
    max_rows: int | None = Field(default=100, ge=1)


class WorkloadSourceJobOptions(BaseModel):
    enabled: bool = True
    entity: str
    mode: Literal["query", "cycle"] = "query"
    filter_text: str = ""
    top: int | None = Field(default=10, ge=1)
    watermark: str | None = None
    interval_seconds: float = Field(default=10.0, gt=0)
    max_cycles: int | None = Field(default=None, ge=1)
    cycle_parameters: dict[str, Any] = Field(default_factory=dict)


class WorkloadRunRequest(BaseModel):
    name: str = "Concurrent simulator run"
    run_id: str | None = None
    replays: list[WorkloadReplayOptions] = Field(default_factory=list)
    sap_pp_jobs: list[WorkloadSourceJobOptions] = Field(default_factory=list)
    lims_odbc_jobs: list[WorkloadSourceJobOptions] = Field(default_factory=list)
    video_jobs: list["VideoJobRequest"] = Field(default_factory=list)
    replay: WorkloadReplayOptions | None = None
    sap_pp: WorkloadSourceJobOptions | None = None
    lims_odbc: WorkloadSourceJobOptions | None = None

    @model_validator(mode="after")
    def _fold_legacy_singular_fields(self) -> "WorkloadRunRequest":
        if self.replay is not None and self.replay.enabled:
            self.replays.insert(0, self.replay)
        if self.sap_pp is not None and self.sap_pp.enabled:
            self.sap_pp_jobs.insert(0, self.sap_pp)
        if self.lims_odbc is not None and self.lims_odbc.enabled:
            self.lims_odbc_jobs.insert(0, self.lims_odbc)
        return self


class ReplayFileSelection(BaseModel):
    filename: str
    source: CsvSource = "uploaded"
    dataset_id: str | None = None
    frequency_hz: float | None = Field(default=None, gt=0)
    loop_mode: LoopMode | None = None
    timestamp_mode: TimestampMode | None = None
    start_row: int | None = Field(default=None, ge=0)
    max_rows: int | None = None


class ProtocolTagSelection(BaseModel):
    protocol: TagProtocol
    filename: str
    source: CsvSource = "uploaded"
    csv_column: str
    enabled: bool = True


class ReplayFilesConfig(BaseModel):
    protocol: ProtocolMode = "opcua"
    files: list[ReplayFileSelection] = Field(default_factory=list)
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
    emitted_count: int = 0
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


class DatasetSchemaField(BaseModel):
    name: str
    data_type: str = "String"


class DatasetManifest(BaseModel):
    dataset_id: str
    name: str
    description: str = ""
    source: DatasetSource = "generated"
    storage_format: StorageFormat = "csv"
    state: DatasetState = "registered"
    schema: list[DatasetSchemaField] = Field(default_factory=list)
    column_count: int = 0
    row_count: int | None = None
    logical_size_bytes: int | None = None
    physical_size_bytes: int = 0
    part_count: int = 0
    partition_columns: list[str] = Field(default_factory=list)
    created_at: str | None = None
    modified_at: str | None = None
    ready_for_replay: bool = False
    producer_job_id: str | None = None
    scan_job_id: str | None = None
    scan_status: dict[str, Any] = Field(default_factory=dict)
    path: str | None = None
    error: str | None = None


class RegisterDatasetRequest(BaseModel):
    path: str
    name: str | None = None
    description: str = ""
    source: DatasetSource = "registered"


class ConvertDatasetRequest(BaseModel):
    output_format: OutputFormat = "parquet"
    rows_per_part: int = Field(default=1_000_000, ge=1)
    compression: str = "zstd"
    schema_policy: SchemaPolicy = "fail"


class JobRecord(BaseModel):
    job_id: str
    name: str
    type: JobType
    state: JobState = "queued"
    progress_percent: float = 0.0
    current_step: str = ""
    message: str = ""
    rows_done: int = 0
    bytes_done: int = 0
    logical_bytes_done: int = 0
    physical_bytes_done: int = 0
    parts_done: int = 0
    commits_done: int = 0
    rows_per_sec: float = 0.0
    mb_per_sec: float = 0.0
    queue_depth: int = 0
    active_bottleneck: str = ""
    started_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    output_paths: list[str] = Field(default_factory=list)
    dataset_id: str | None = None
    error: str | None = None


class VideoJobRequest(BaseModel):
    name: str = "Synthetic video"
    run_id: str | None = None
    camera_count: int = Field(default=1, ge=1, le=32)
    camera_id_prefix: str = "CAM"
    fps: int = Field(default=5, ge=1, le=60)
    width: int = Field(default=640, ge=64, le=3840)
    height: int = Field(default=360, ge=64, le=2160)
    duration_seconds: int = Field(default=10, ge=1)
    segment_seconds: int = Field(default=5, ge=1)
    visual_mode: str = "moving_gradient"
    overlay_timestamp: bool = True
    overlay_run_id: bool = True
    linked_dataset_id: str | None = None


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


WorkloadRunRequest.model_rebuild()
