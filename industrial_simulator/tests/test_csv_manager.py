import csv
from pathlib import Path
import pytest
from app import csv_manager


def test_safe_filename_rejects_path():
    with pytest.raises(ValueError):
        csv_manager.sanitize_filename('../bad.csv')


def test_metadata_tmp_generated(tmp_path, monkeypatch):
    monkeypatch.setitem(csv_manager.SOURCE_DIRS, 'generated', tmp_path)
    path = tmp_path / 'x.csv'
    with path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp','flow'])
        writer.writerow(['2026-01-01T00:00:00Z','1.2'])
    meta = csv_manager.metadata('x.csv', 'generated')
    assert meta.row_count == 1
    assert meta.inferred_types['flow'] == 'Double'
