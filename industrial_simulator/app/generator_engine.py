from __future__ import annotations

from app import csv_manager
from app.generator_registry import get_generator
from app.models import GenerateRequest, GenerateResponse

MAX_ROWS = 1_000_000


def generate_csv(domain_id: str, request: GenerateRequest) -> GenerateResponse:
    safe = csv_manager.sanitize_filename(request.output_filename)
    generator = get_generator(domain_id)
    spec = generator.get_spec()
    if request.scenario not in {s.id for s in spec.scenarios}:
        raise ValueError("Invalid scenario for selected generator.")
    duration = float(request.parameters.get("duration_minutes", 1))
    rate = float(request.parameters.get("sample_rate_hz", 1))
    if duration <= 0 or rate <= 0:
        raise ValueError("Duration and sample rate must be positive.")
    if duration * 60 * rate > MAX_ROWS:
        raise ValueError(f"Generated row count exceeds maximum of {MAX_ROWS}.")
    rows = generator.generate(request)
    csv_manager.write_rows(safe, rows, source="generated")
    meta = csv_manager.metadata(safe, "generated")
    return GenerateResponse(
        status="generated",
        filename=safe,
        row_count=meta.row_count,
        column_count=meta.column_count,
        columns=meta.columns,
        preview=meta.preview,
        loaded_into_replay=request.load_into_replay,
        default_tag_mappings=meta.default_tag_mappings if request.load_into_replay else [],
    )
