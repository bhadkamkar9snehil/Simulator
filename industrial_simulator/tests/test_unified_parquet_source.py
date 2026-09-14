from __future__ import annotations

import asyncio

import pyarrow as pa
import pyarrow.parquet as pq

from app.simulation.models import SourceBinding
from app.simulation.sources import IndexedParquetRows, ParquetSimulationSource, create_source


def test_indexed_parquet_rows_spans_files_with_max_rows(tmp_path) -> None:
    first = pa.table({"timestamp": ["t1", "t2"], "pressure": [1.1, 1.2]})
    second = pa.table({"timestamp": ["t3", "t4"], "pressure": [1.3, 1.4]})
    pq.write_table(first, tmp_path / "part-001.parquet", row_group_size=1)
    pq.write_table(second, tmp_path / "part-002.parquet", row_group_size=1)

    rows = IndexedParquetRows(tmp_path, max_rows=3)

    assert rows.row_count == 3
    assert rows.columns == ["timestamp", "pressure"]
    assert rows.row(0)["pressure"] == 1.1
    assert rows.row(2)["timestamp"] == "t3"


def test_parquet_source_emits_canonical_frames(tmp_path) -> None:
    table = pa.table({"timestamp": ["2026-09-13T05:00:00Z"], "pressure": [4.2], "pressure_unit": ["bar"]})
    path = tmp_path / "source.parquet"
    pq.write_table(table, path)

    source = create_source(SourceBinding(kind="parquet", config={"path": str(path)}), "sim_parquet")
    assert isinstance(source, ParquetSimulationSource)

    async def exercise() -> None:
        await source.open()
        assert source.count == 1
        frame = await source.next_frame()
        assert frame is not None
        assert frame.source_timestamp == "2026-09-13T05:00:00Z"
        assert frame.values["pressure"].value == 4.2
        assert frame.values["pressure"].unit == "bar"
        assert await source.next_frame() is None
        await source.close()

    asyncio.run(exercise())
