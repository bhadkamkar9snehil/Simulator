from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Iterable

from app import csv_manager
from app.models import utc_now_iso


def default_lakehouse_root() -> Path:
    root = csv_manager.ROOT / "lakehouse"
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_part(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value).strip("_")
    return clean or "value"


def write_parquet_part(rows: list[dict[str, Any]], output_path: Path, compression: str = "zstd") -> None:
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore
    except Exception as exc:
        raise ValueError("Parquet output requires pyarrow in the bundled runtime.") from exc
    table = pa.Table.from_pylist(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    pq.write_table(table, tmp, compression=compression)
    tmp.replace(output_path)


def lakehouse_partition_path(root: Path, domain: str, run_id: str, row: dict[str, Any]) -> Path:
    timestamp = str(row.get("timestamp") or utc_now_iso())
    event_date = timestamp[:10] if len(timestamp) >= 10 else utc_now_iso()[:10]
    hour = timestamp[11:13] if len(timestamp) >= 13 else "00"
    return root / safe_part(domain) / safe_part(run_id) / f"event_date={safe_part(event_date)}" / f"hour={safe_part(hour)}"


def commit_manifest(root: Path, run_id: str, commit: dict[str, Any]) -> Path:
    target = root / "_commits" / safe_part(run_id) / f"commit-{commit['part_index']:06d}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(commit, indent=2), encoding="utf-8")
    return target


def write_lakehouse_parts(
    rows_iter: Iterable[dict[str, Any]],
    *,
    domain: str,
    run_id: str,
    root: Path | None = None,
    rows_per_part: int = 1_000_000,
    compression: str = "zstd",
) -> dict[str, Any]:
    lake_root = root or default_lakehouse_root()
    buffer: list[dict[str, Any]] = []
    rows_done = 0
    part_index = 0
    commits: list[str] = []
    for row in rows_iter:
        buffer.append(row)
        if len(buffer) >= rows_per_part:
            part_index += 1
            target_dir = lakehouse_partition_path(lake_root, domain, run_id, buffer[0])
            part_path = target_dir / f"part-{part_index:06d}.parquet"
            write_parquet_part(buffer, part_path, compression=compression)
            rows_done += len(buffer)
            commit = {
                "commit_id": f"commit_{uuid.uuid4().hex[:12]}",
                "run_id": run_id,
                "domain": domain,
                "part_index": part_index,
                "rows": len(buffer),
                "path": str(part_path),
                "size_bytes": part_path.stat().st_size,
                "committed_at": utc_now_iso(),
            }
            commits.append(str(commit_manifest(lake_root, run_id, commit)))
            buffer = []
    if buffer:
        part_index += 1
        target_dir = lakehouse_partition_path(lake_root, domain, run_id, buffer[0])
        part_path = target_dir / f"part-{part_index:06d}.parquet"
        write_parquet_part(buffer, part_path, compression=compression)
        rows_done += len(buffer)
        commit = {
            "commit_id": f"commit_{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "domain": domain,
            "part_index": part_index,
            "rows": len(buffer),
            "path": str(part_path),
            "size_bytes": part_path.stat().st_size,
            "committed_at": utc_now_iso(),
        }
        commits.append(str(commit_manifest(lake_root, run_id, commit)))
    run_manifest = lake_root / "_manifests" / f"{safe_part(run_id)}.json"
    run_manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {"run_id": run_id, "domain": domain, "rows": rows_done, "parts": part_index, "commits": commits, "updated_at": utc_now_iso()}
    run_manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
