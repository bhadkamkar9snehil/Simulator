from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from app import csv_manager
from app.models import DatasetManifest, DatasetSchemaField, RegisterDatasetRequest, utc_now_iso

DATASET_DIR = csv_manager.GENERATED_DIR / "datasets"
LAKEHOUSE_DIR = csv_manager.ROOT / "lakehouse"


def _dataset_path(dataset_id: str) -> Path:
    return DATASET_DIR / dataset_id


def _manifest_path(dataset_id: str) -> Path:
    return _dataset_path(dataset_id) / "dataset_manifest.json"


def _new_dataset_id(name: str) -> str:
    stem = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_") or "dataset"
    return f"ds_{stem}_{uuid.uuid4().hex[:8]}"


def _size_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def _storage_format(path: Path) -> str:
    if path.is_dir():
        if list(path.glob("*.parquet")) or list(path.rglob("*.parquet")):
            return "parquet_folder"
        raise ValueError("Only Parquet folders can be registered as folders.")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".xlsx":
        return "xlsx"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".ndjson":
        return "ndjson"
    if suffix == ".parquet":
        return "parquet"
    raise ValueError("Supported dataset formats are CSV, XLSX, JSONL, NDJSON, and Parquet.")


def _allowed_roots() -> list[Path]:
    return [csv_manager.UPLOAD_DIR, csv_manager.GENERATED_DIR, csv_manager.SAMPLE_DIR, LAKEHOUSE_DIR]


def validate_registered_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Dataset path not found: {path}")
    allowed = [root.resolve() for root in _allowed_roots()]
    if not any(path == root or root in path.parents for root in allowed):
        roots = ", ".join(str(root) for root in allowed)
        raise ValueError(f"Registered paths must be under one of: {roots}")
    return path


def write_manifest(manifest: DatasetManifest) -> DatasetManifest:
    now = utc_now_iso()
    if manifest.created_at is None:
        manifest.created_at = now
    manifest.modified_at = now
    target_dir = _dataset_path(manifest.dataset_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    _manifest_path(manifest.dataset_id).write_text(json.dumps(manifest.model_dump(), indent=2), encoding="utf-8")
    return manifest


def read_manifest(dataset_id: str) -> DatasetManifest:
    path = _manifest_path(dataset_id)
    if not path.exists():
        raise KeyError(f"Dataset not found: {dataset_id}")
    return DatasetManifest(**json.loads(path.read_text(encoding="utf-8")))


def find_manifest(dataset_id: str) -> DatasetManifest | None:
    try:
        return read_manifest(dataset_id)
    except KeyError:
        return None


def list_managed_datasets() -> list[DatasetManifest]:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    manifests: list[DatasetManifest] = []
    for path in DATASET_DIR.glob("*/dataset_manifest.json"):
        try:
            manifests.append(DatasetManifest(**json.loads(path.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return sorted(manifests, key=lambda item: item.modified_at or "", reverse=True)


def csv_file_datasets() -> list[DatasetManifest]:
    items: list[DatasetManifest] = []
    for record in csv_manager.list_files():
        dataset_id = f"csv_{record.source}_{record.filename}".replace(" ", "_").replace(".", "_")
        items.append(
            DatasetManifest(
                dataset_id=dataset_id,
                name=record.filename,
                source=record.source if record.source != "sample" else "sample",
                storage_format="xlsx" if record.filename.lower().endswith(".xlsx") else "csv",
                state="ready",
                row_count=record.row_count,
                column_count=record.column_count,
                physical_size_bytes=(csv_manager.resolve_csv_path(record.filename, record.source).stat().st_size),
                ready_for_replay=True,
                path=record.path,
                modified_at=record.modified_at,
            )
        )
    return items


def find_csv_file_dataset(dataset_id: str) -> DatasetManifest | None:
    for item in csv_file_datasets():
        if item.dataset_id == dataset_id:
            return item
    return None


def list_datasets(include_csv: bool = True) -> list[DatasetManifest]:
    items = list_managed_datasets()
    seen = {item.dataset_id for item in items}
    if include_csv:
        for item in csv_file_datasets():
            if item.dataset_id in seen:
                continue
            items.append(item)
            seen.add(item.dataset_id)
    return items


def get_dataset(dataset_id: str) -> DatasetManifest:
    manifest = find_manifest(dataset_id)
    if manifest is not None:
        return manifest
    csv_item = find_csv_file_dataset(dataset_id)
    if csv_item is not None:
        return csv_item
    raise KeyError(f"Dataset not found: {dataset_id}")


def dataset_path(manifest: DatasetManifest) -> Path:
    if not manifest.path:
        raise ValueError("Dataset has no path.")
    path = Path(manifest.path)
    if path.is_absolute():
        return path
    rooted = (csv_manager.ROOT / path).resolve()
    if rooted.exists():
        return rooted
    if manifest.source in {"uploaded", "generated", "sample"}:
        return csv_manager.resolve_csv_path(manifest.name, manifest.source)
    return rooted


def register_local(request: RegisterDatasetRequest) -> DatasetManifest:
    path = validate_registered_path(request.path)
    fmt = _storage_format(path)
    name = request.name or path.name
    dataset_id = _new_dataset_id(name)
    manifest = DatasetManifest(
        dataset_id=dataset_id,
        name=name,
        description=request.description,
        source=request.source,
        storage_format=fmt,  # type: ignore[arg-type]
        state="registered",
        physical_size_bytes=_size_bytes(path),
        ready_for_replay=fmt in {"csv", "parquet", "parquet_folder"},
        path=str(path),
    )
    return write_manifest(manifest)


def preview(dataset_id: str, limit: int = 10) -> dict[str, Any]:
    manifest = get_dataset(dataset_id)
    if manifest.storage_format == "csv" and manifest.path:
        path = dataset_path(manifest)
        source_columns, rows = csv_manager.read_rows(path, max_rows=limit)
        return {"filename": path.name, "source": manifest.source, "columns": source_columns, "rows": rows}
    if manifest.storage_format in {"parquet", "parquet_folder"}:
        try:
            import pyarrow.parquet as pq  # type: ignore
        except Exception as exc:
            raise ValueError("Parquet preview requires pyarrow in the bundled runtime.") from exc
        path = Path(manifest.path or "")
        if path.is_dir():
            parts = sorted(path.rglob("*.parquet"))
            if not parts:
                raise ValueError("Parquet dataset has no part files.")
            path = parts[0]
        table = pq.read_table(path, columns=None)
        rows = table.slice(0, limit).to_pylist()
        return {"filename": manifest.name, "source": manifest.source, "columns": table.column_names, "rows": rows}
    raise ValueError(f"Preview is not supported for {manifest.storage_format}.")


def scan_dataset(dataset_id: str, job_id: str | None = None) -> DatasetManifest:
    manifest = read_manifest(dataset_id)
    if not manifest.path:
        raise ValueError("Dataset has no registered path to scan.")
    path = dataset_path(manifest)
    if manifest.storage_format == "csv":
        columns, preview_rows, type_sample, row_count = csv_manager.scan_rows(path, preview_rows=10)
        inferred = csv_manager.infer_types(type_sample, columns) if hasattr(csv_manager, "infer_types") else {}
        manifest.schema = [DatasetSchemaField(name=col, data_type=str(inferred.get(col, "String"))) for col in columns]
        manifest.column_count = len(columns)
        manifest.row_count = row_count
        manifest.ready_for_replay = True
    elif manifest.storage_format in {"parquet", "parquet_folder"}:
        try:
            import pyarrow.parquet as pq  # type: ignore
        except Exception as exc:
            raise ValueError("Parquet scan requires pyarrow in the bundled runtime.") from exc
        parts = [path] if path.is_file() else sorted(path.rglob("*.parquet"))
        if not parts:
            raise ValueError("Parquet dataset has no part files.")
        schema = pq.read_schema(parts[0])
        manifest.schema = [DatasetSchemaField(name=field.name, data_type=str(field.type)) for field in schema]
        manifest.column_count = len(manifest.schema)
        manifest.row_count = sum(pq.ParquetFile(part).metadata.num_rows for part in parts)
        manifest.part_count = len(parts)
        manifest.ready_for_replay = True
    else:
        manifest.ready_for_replay = False
    manifest.scan_job_id = job_id or manifest.scan_job_id
    manifest.physical_size_bytes = _size_bytes(path)
    manifest.state = "ready"
    manifest.error = None
    return write_manifest(manifest)


def delete_dataset(dataset_id: str, delete_files: bool = False) -> dict[str, bool]:
    manifest = read_manifest(dataset_id)
    if delete_files and manifest.path:
        path = Path(manifest.path)
        if path.exists() and _dataset_path(dataset_id).resolve() in path.resolve().parents:
            shutil.rmtree(path if path.is_dir() else path.parent, ignore_errors=True)
    dataset_dir = _dataset_path(dataset_id)
    if dataset_dir.exists():
        shutil.rmtree(dataset_dir)
    return {"deleted": True}
