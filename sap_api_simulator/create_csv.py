from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .sap_data import DATA_DIR, write_csv_files
except ImportError:
    from sap_data import DATA_DIR, write_csv_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Create CSV files for the SAP API simulator.")
    parser.add_argument("--out", default=str(DATA_DIR), help="Output directory for generated CSV files.")
    args = parser.parse_args()

    output_dir = Path(args.out).resolve()
    manifest = write_csv_files(output_dir)
    print(f"Created {len(manifest['datasets'])} SAP CSV datasets in {output_dir}")
    for entity_set, info in manifest["datasets"].items():
        print(f"{entity_set}: {info['rows']} rows -> {info['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
