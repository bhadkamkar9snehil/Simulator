from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from app import csv_manager, dataset_manager
from app.generator_registry import get_generator
from app.models import GenerateRequest, TagMapping
from app.source_simulators.registry import get_source_simulator
from app.type_inference import convert_value, infer_types

from .contracts import SimulationSource, require_config
from .models import SignalDefinition, SignalValue, SimulationFrame, SourceBinding, utc_now_iso


class IndexedCsvRows:
    """Random-access CSV rows without loading the whole file into memory."""

    def __init__(self, path: Path, max_rows: int | None = None):
        self.path = path
        self.columns: list[str] = []
        self.offsets: list[int] = []
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            header_line = handle.readline()
            if not header_line:
                raise ValueError("File has no header.")
            self.columns = [column.strip() for column in next(csv.reader([header_line]))]
            if not self.columns:
                raise ValueError("File has no header.")
            if len(set(self.columns)) != len(self.columns):
                raise ValueError("File has duplicate columns.")
            while max_rows is None or len(self.offsets) < max_rows:
                offset = handle.tell()
                line = handle.readline()
                if not line:
                    break
                self.offsets.append(offset)

    @property
    def row_count(self) -> int:
        return len(self.offsets)

    def row(self, index: int) -> dict[str, str]:
        if index < 0 or index >= self.row_count:
            raise IndexError("CSV row index out of range.")
        with self.path.open("r", newline="", encoding="utf-8-sig") as handle:
            handle.seek(self.offsets[index])
            line = handle.readline()
        values = next(csv.reader([line]))
        return {column: values[i] if i < len(values) else "" for i, column in enumerate(self.columns)}


class IndexedParquetRows:
    """Random-access Parquet rows with one row-group cache.

    A directory is treated as a multi-file Parquet dataset. This keeps replay
    memory bounded while still supporting seek and ping-pong loop modes.
    """

    def __init__(self, path: Path, max_rows: int | None = None):
        paths = sorted(path.rglob("*.parquet")) if path.is_dir() else [path]
        if not paths:
            raise ValueError(f"No Parquet files found at {path}.")

        self.columns: list[str] = []
        self._segments: list[tuple[pq.ParquetFile, int, int]] = []
        self._cached_key: tuple[int, int] | None = None
        self._cached_rows: list[dict[str, Any]] = []
        total = 0

        for file_path in paths:
            parquet_file = pq.ParquetFile(file_path)
            for column in parquet_file.schema_arrow.names:
                if column not in self.columns:
                    self.columns.append(column)
            available = int(parquet_file.metadata.num_rows)
            if max_rows is not None:
                available = min(available, max(0, int(max_rows) - total))
            if available <= 0:
                break
            self._segments.append((parquet_file, total, available))
            total += available
            if max_rows is not None and total >= int(max_rows):
                break

        self.row_count = total
        if self.row_count <= 0:
            raise ValueError("Parquet source has no data rows.")

    def row(self, index: int) -> dict[str, Any]:
        if index < 0 or index >= self.row_count:
            raise IndexError("Parquet row index out of range.")
        for file_index, (parquet_file, start, available) in enumerate(self._segments):
            if not (start <= index < start + available):
                continue
            local_index = index - start
            row = self._row_from_file(file_index, parquet_file, local_index)
            return {column: row.get(column, "") for column in self.columns}
        raise IndexError("Parquet row index could not be resolved.")

    def _row_from_file(self, file_index: int, parquet_file: pq.ParquetFile, local_index: int) -> dict[str, Any]:
        remaining = local_index
        for row_group in range(parquet_file.metadata.num_row_groups):
            row_count = int(parquet_file.metadata.row_group(row_group).num_rows)
            if remaining < row_count:
                key = (file_index, row_group)
                if self._cached_key != key:
                    self._cached_rows = parquet_file.read_row_group(row_group).to_pylist()
                    self._cached_key = key
                return self._cached_rows[remaining]
            remaining -= row_count
        raise IndexError("Parquet row index exceeds row-group metadata.")


IndexedRows = IndexedCsvRows | IndexedParquetRows


class _RowSource:
    def __init__(self, simulation_id: str, config: dict[str, Any]):
        self.simulation_id = simulation_id
        self.config = config
        self._position = 0
        self._rows: list[dict[str, Any]] = []
        self._indexed: IndexedRows | None = None
        self._columns: list[str] = []
        self._mappings: list[TagMapping] = []
        self._count: int | None = None

    @property
    def position(self) -> int:
        return self._position

    @property
    def count(self) -> int | None:
        return self._count

    async def close(self) -> None:
        return None

    async def seek(self, position: int) -> None:
        count = self._count
        if position < 0 or (count is not None and position > count):
            raise ValueError("Source seek position is outside the available range.")
        self._position = position

    def schema(self) -> list[SignalDefinition]:
        return [
            SignalDefinition(
                name=mapping.csv_column,
                node_id=mapping.node_id,
                data_type=mapping.data_type,
                initial_value=mapping.initial_value,
                writable=mapping.writable,
            )
            for mapping in self._mappings
            if mapping.enabled
        ]

    async def next_frame(self) -> SimulationFrame | None:
        if self._count is None or self._position >= self._count:
            return None
        index = self._position
        row = self._row(index)
        self._position += 1
        return self._frame(row, index)

    def _row(self, index: int) -> dict[str, Any]:
        if self._indexed is not None:
            return self._indexed.row(index)
        return self._rows[index]

    def _configure_rows(
        self,
        columns: list[str],
        rows: list[dict[str, Any]],
        count: int,
        mappings: list[TagMapping] | None = None,
        indexed: IndexedRows | None = None,
    ) -> None:
        if count <= 0:
            raise ValueError("Simulation source has no data rows.")
        self._columns = columns
        self._rows = rows
        self._indexed = indexed
        self._count = count

        if mappings is None:
            sample = rows[:100]
            if indexed is not None:
                sample = [indexed.row(index) for index in range(min(100, count))]
            inferred = infer_types(sample, columns)
            mappings = csv_manager.default_tag_mappings(columns, inferred)

        missing = [mapping.csv_column for mapping in mappings if mapping.enabled and mapping.csv_column not in columns]
        if missing:
            raise ValueError(f"Source columns not found: {', '.join(missing)}")
        self._mappings = mappings

        start_row = int(self.config.get("start_row", 0) or 0)
        if start_row < 0 or start_row >= count:
            raise ValueError("start_row must be within the available source rows.")
        self._position = start_row

    def _configured_mappings(self) -> list[TagMapping] | None:
        raw = self.config.get("tags")
        if not raw:
            return None
        return [TagMapping.model_validate(item) for item in raw]

    def _frame(self, row: dict[str, Any], sequence: int) -> SimulationFrame:
        source_timestamp = _row_value(row, ["timestamp", "Timestamp", "TIMESTAMP"])
        values: dict[str, SignalValue] = {}
        for mapping in self._mappings:
            if not mapping.enabled:
                continue
            raw = row.get(mapping.csv_column)
            try:
                value = convert_value(raw, mapping.data_type)
            except Exception:
                value = None
            metadata = _signal_metadata(row, mapping.csv_column)
            values[mapping.csv_column] = SignalValue(
                value=value,
                data_type=mapping.data_type,
                quality=str(metadata.pop("quality", "GOOD")),
                unit=metadata.pop("unit", None),
                metadata=metadata,
            )

        context_fields = self.config.get("context_fields") or []
        context = {str(key): row.get(str(key)) for key in context_fields if str(key) in row}
        return SimulationFrame(
            simulation_id=self.simulation_id,
            sequence=sequence,
            timestamp=utc_now_iso(),
            source_timestamp=str(source_timestamp) if source_timestamp not in (None, "") else None,
            values=values,
            context=context,
        )


class CsvSimulationSource(_RowSource):
    """CSV/XLSX/dataset source backed by the repository's existing data managers."""

    async def open(self) -> None:
        dataset_id = self.config.get("dataset_id")
        max_rows = self.config.get("max_rows")
        if max_rows is not None:
            max_rows = int(max_rows)

        if dataset_id:
            manifest = dataset_manager.get_dataset(str(dataset_id))
            if manifest.storage_format != "csv":
                raise ValueError("CSV source requires a dataset with storage_format=csv.")
            path = dataset_manager.dataset_path(manifest)
        else:
            filename = str(require_config(self.config, "filename"))
            source = str(self.config.get("csv_source", self.config.get("source", "generated")))
            path = csv_manager.resolve_csv_path(filename, source)

        if path.suffix.lower() == ".csv":
            indexed = IndexedCsvRows(path, max_rows=max_rows)
            self._configure_rows(
                columns=indexed.columns,
                rows=[],
                count=indexed.row_count,
                mappings=self._configured_mappings(),
                indexed=indexed,
            )
            return

        columns, rows = csv_manager.read_rows(path, max_rows=max_rows)
        self._configure_rows(columns, rows, len(rows), mappings=self._configured_mappings())


class ParquetSimulationSource(_RowSource):
    """Parquet file/folder replay with row-group-level memory use."""

    async def open(self) -> None:
        max_rows = self.config.get("max_rows")
        if max_rows is not None:
            max_rows = int(max_rows)

        dataset_id = self.config.get("dataset_id")
        if dataset_id:
            manifest = dataset_manager.get_dataset(str(dataset_id))
            if manifest.storage_format not in {"parquet", "parquet_folder"}:
                raise ValueError("Parquet source requires a parquet or parquet_folder dataset.")
            path = dataset_manager.dataset_path(manifest)
        else:
            path = Path(str(require_config(self.config, "path"))).expanduser().resolve()
            if not path.exists():
                raise FileNotFoundError(f"Parquet source not found: {path}")

        indexed = IndexedParquetRows(path, max_rows=max_rows)
        self._configure_rows(
            columns=indexed.columns,
            rows=[],
            count=indexed.row_count,
            mappings=self._configured_mappings(),
            indexed=indexed,
        )


class InlineSimulationSource(_RowSource):
    """Small in-memory row source for API-driven tests and lightweight simulations."""

    async def open(self) -> None:
        raw_rows = require_config(self.config, "rows")
        if not isinstance(raw_rows, list) or not raw_rows:
            raise ValueError("Inline source config.rows must be a non-empty list.")
        rows = [dict(row) for row in raw_rows]
        columns = list(rows[0].keys())
        for row in rows:
            for column in row:
                if column not in columns:
                    columns.append(column)
        max_rows = self.config.get("max_rows")
        if max_rows is not None:
            rows = rows[: int(max_rows)]
        self._configure_rows(columns, rows, len(rows), mappings=self._configured_mappings())


class SourceSimulatorSimulationSource(_RowSource):
    """Adapter over the existing SAP PP/LIMS source-simulator registry."""

    async def open(self) -> None:
        connector_id = str(self.config.get("connector_id") or self.config.get("source_id") or "").strip()
        if not connector_id:
            raise ValueError("Source simulator requires config.connector_id.")
        entity = str(require_config(self.config, "entity"))
        source = get_source_simulator(connector_id)

        cycles = int(self.config.get("seed_cycles", 0) or 0)
        cycle_parameters = dict(self.config.get("cycle_parameters") or {})
        for _ in range(max(0, cycles)):
            source.run_cycle(**cycle_parameters)

        rows = source.query(
            entity=entity,
            filter_text=str(self.config.get("filter_text", "")),
            top=int(self.config["top"]) if self.config.get("top") is not None else None,
            skip=int(self.config.get("skip", 0) or 0),
            watermark=str(self.config["watermark"]) if self.config.get("watermark") else None,
        )
        if not rows:
            raise ValueError(f"Source simulator {connector_id} entity {entity} returned no rows.")
        columns: list[str] = []
        for row in rows:
            for column in row:
                if column not in columns:
                    columns.append(column)
        self._configure_rows(columns, rows, len(rows), mappings=self._configured_mappings())


class GeneratorSimulationSource(_RowSource):
    """Adapter over the existing domain generator registry."""

    async def open(self) -> None:
        domain_id = str(require_config(self.config, "domain_id"))
        generator = get_generator(domain_id)
        spec = generator.get_spec()
        scenario = self.config.get("scenario")
        if not scenario:
            if not spec.scenarios:
                raise ValueError(f"Generator {domain_id} has no scenarios.")
            scenario = spec.scenarios[0].id
        request = GenerateRequest(
            scenario=str(scenario),
            output_filename="__unified_runtime__.csv",
            parameters=dict(self.config.get("parameters") or {}),
            load_into_replay=False,
        )
        rows = generator.generate(request)
        if not rows:
            raise ValueError(f"Generator {domain_id} produced no rows.")
        columns = list(rows[0].keys())
        max_rows = self.config.get("max_rows")
        if max_rows is not None:
            rows = rows[: int(max_rows)]
        self._configure_rows(columns, rows, len(rows), mappings=self._configured_mappings())


def create_source(binding: SourceBinding, simulation_id: str) -> SimulationSource:
    if binding.kind in {"csv", "dataset", "file"}:
        config = dict(binding.config)
        if binding.kind == "dataset" and "dataset_id" not in config:
            raise ValueError("Dataset source requires config.dataset_id.")
        if binding.kind == "dataset" and config.get("dataset_id"):
            manifest = dataset_manager.get_dataset(str(config["dataset_id"]))
            if manifest.storage_format in {"parquet", "parquet_folder"}:
                return ParquetSimulationSource(simulation_id, config)
        return CsvSimulationSource(simulation_id, config)
    if binding.kind in {"parquet", "parquet_folder"}:
        return ParquetSimulationSource(simulation_id, dict(binding.config))
    if binding.kind == "generator":
        return GeneratorSimulationSource(simulation_id, dict(binding.config))
    if binding.kind in {"source_simulator", "sap_pp", "lims_odbc"}:
        config = dict(binding.config)
        if binding.kind != "source_simulator":
            config.setdefault("connector_id", binding.kind)
        return SourceSimulatorSimulationSource(simulation_id, config)
    if binding.kind in {"inline", "rows"}:
        return InlineSimulationSource(simulation_id, dict(binding.config))
    raise ValueError(f"Unsupported simulation source kind: {binding.kind}")


def _row_value(row: dict[str, Any], names: list[str]) -> Any:
    lower_map = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        value = lower_map.get(str(name).strip().lower())
        if value is not None and str(value).strip() != "":
            return value
    return None


def _signal_metadata(row: dict[str, Any], column: str) -> dict[str, Any]:
    unit = _row_value(
        row,
        [
            f"{column}_unit",
            f"{column} unit",
            f"{column}.unit",
            f"{column}/unit",
            f"unit_{column}",
        ],
    )
    quality = _row_value(
        row,
        [
            f"{column}_quality",
            f"{column} quality",
            f"{column}.quality",
            f"{column}/quality",
            f"quality_{column}",
        ],
    )
    if unit is None:
        unit = _row_value(row, ["unit"])
    if quality is None:
        quality = _row_value(row, ["quality", "status"])
    metadata: dict[str, Any] = {"tag": column}
    if unit is not None:
        metadata["unit"] = unit
    if quality is not None:
        metadata["quality"] = quality
    return metadata
