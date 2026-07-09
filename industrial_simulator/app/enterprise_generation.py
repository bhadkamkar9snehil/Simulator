from __future__ import annotations

import itertools
import math
import uuid
from pathlib import Path
from typing import Any

from app import csv_manager, dataset_manager, job_manager
from app.generator_registry import get_generator
from app.lakehouse import write_lakehouse_parts, write_parquet_part
from app.models import DatasetManifest, DatasetSchemaField, GenerateJobRequest, GenerateRequest, utc_now_iso


def _row_limit(request: GenerateJobRequest) -> int:
    if request.target_basis == "rows" and request.target_value:
        return max(1, int(request.target_value))
    duration = float(request.parameters.get("duration_minutes", 1))
    rate = float(request.parameters.get("sample_rate_hz", 1))
    return max(1, int(duration * 60 * rate))


def _rows_for_generator(domain_id: str, request: GenerateJobRequest):
    generator = get_generator(domain_id)
    gen_request = GenerateRequest(scenario=request.scenario, output_filename="enterprise_job.csv", parameters=request.parameters)
    spec = generator.get_spec()
    if request.scenario not in {s.id for s in spec.scenarios}:
        raise ValueError("Invalid scenario for selected generator.")
    iter_rows = getattr(generator, "iter_rows", None)
    rows = iter_rows(gen_request) if callable(iter_rows) else generator.generate(gen_request)
    return itertools.islice(rows, _row_limit(request))


def start_generate_job(domain_id: str, request: GenerateJobRequest) -> str:
    job = job_manager.create_job(request.name, "generate_dataset")
    job_manager.run_background(job.job_id, run_generate_job, domain_id, request)
    return job.job_id


def run_generate_job(job_id: str, domain_id: str, request: GenerateJobRequest) -> None:
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    rows_iter = _rows_for_generator(domain_id, request)
    if request.output_format == "csv":
        filename = f"{run_id}.csv"
        path = csv_manager.write_rows(filename, rows_iter, source="generated")
        meta = csv_manager.metadata(filename, "generated")
        safe_domain = "".join(ch if ch.isalnum() else "_" for ch in domain_id.lower()).strip("_") or "generated"
        dataset = DatasetManifest(
            dataset_id=f"ds_{safe_domain}_{run_id.removeprefix('run_')}",
            name=request.name,
            source="generated",
            storage_format="csv",
            state="ready",
            row_count=meta.row_count,
            column_count=meta.column_count,
            schema=[DatasetSchemaField(name=col, data_type=str(meta.inferred_types.get(col, "String"))) for col in meta.columns],
            physical_size_bytes=path.stat().st_size,
            ready_for_replay=True,
            producer_job_id=job_id,
            path=str(path),
        )
        dataset_manager.write_manifest(dataset)
        job_manager.mark_completed(job_id, "CSV dataset generated.", dataset_id=dataset.dataset_id, output_paths=[str(path)], rows_done=meta.row_count, bytes_done=path.stat().st_size, physical_bytes_done=path.stat().st_size)
        return

    if request.output_format == "lakehouse":
        root = Path(request.lakehouse_root).resolve() if request.lakehouse_root else None
        result = write_lakehouse_parts(rows_iter, domain=domain_id, run_id=run_id, root=root, rows_per_part=request.rows_per_part, compression=request.compression)
        job_manager.mark_completed(job_id, "Lakehouse output generated.", rows_done=int(result["rows"]), parts_done=int(result["parts"]), commits_done=len(result["commits"]), output_paths=result["commits"])
        return

    # Parquet managed dataset.
    try:
        import pyarrow  # noqa: F401
    except Exception as exc:
        raise ValueError("Large Parquet generation requires pyarrow in the bundled runtime. Add compatible pyarrow wheels before running this job.") from exc

    dataset_id = f"ds_{domain_id}_{uuid.uuid4().hex[:8]}"
    dataset_dir = dataset_manager.DATASET_DIR / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    buffer: list[dict[str, Any]] = []
    part_count = 0
    rows_done = 0
    physical_bytes = 0
    schema: list[DatasetSchemaField] = []
    limit = _row_limit(request)
    for row in rows_iter:
        buffer.append(row)
        if len(buffer) >= request.rows_per_part:
            part_count += 1
            path = dataset_dir / f"part-{part_count:06d}.parquet"
            write_parquet_part(buffer, path, compression=request.compression)
            rows_done += len(buffer)
            physical_bytes += path.stat().st_size
            if not schema:
                schema = [DatasetSchemaField(name=key, data_type=type(value).__name__) for key, value in buffer[0].items()]
            percent = min(99.0, (rows_done / max(limit, 1)) * 100)
            rows_per_sec, mb_per_sec = job_manager.Throughput().rates(rows_done, physical_bytes)
            job_manager.update_job(job_id, progress_percent=percent, current_step=f"Committed part {part_count}", rows_done=rows_done, physical_bytes_done=physical_bytes, bytes_done=physical_bytes, parts_done=part_count, commits_done=part_count, rows_per_sec=rows_per_sec, mb_per_sec=mb_per_sec, active_bottleneck="disk_write")
            buffer = []
    if buffer:
        part_count += 1
        path = dataset_dir / f"part-{part_count:06d}.parquet"
        write_parquet_part(buffer, path, compression=request.compression)
        rows_done += len(buffer)
        physical_bytes += path.stat().st_size
        if not schema:
            schema = [DatasetSchemaField(name=key, data_type=type(value).__name__) for key, value in buffer[0].items()]
    manifest = DatasetManifest(
        dataset_id=dataset_id,
        name=request.name,
        source="generated",
        storage_format="parquet_folder",
        state="ready",
        schema=schema,
        column_count=len(schema),
        row_count=rows_done,
        physical_size_bytes=physical_bytes,
        part_count=part_count,
        partition_columns=request.partition_columns,
        ready_for_replay=True,
        producer_job_id=job_id,
        path=str(dataset_dir),
    )
    dataset_manager.write_manifest(manifest)
    job_manager.mark_completed(job_id, "Parquet dataset generated.", dataset_id=dataset_id, rows_done=rows_done, parts_done=part_count, commits_done=part_count, bytes_done=physical_bytes, physical_bytes_done=physical_bytes, output_paths=[str(dataset_dir)])
