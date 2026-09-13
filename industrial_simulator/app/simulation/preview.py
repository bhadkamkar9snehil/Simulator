from __future__ import annotations

from typing import Any

from .mapping import map_frame, map_schema
from .models import SimulationDefinition
from .sources import create_source


async def preview_definition(definition: SimulationDefinition) -> dict[str, Any]:
    """Inspect a configured source without starting targets.

    Raw source schema/sample data is always returned when the source itself is
    valid. Mapping errors are reported separately so changing a source does not
    make the editor unusable merely because mappings from the previous source are
    stale.
    """

    source = create_source(definition.source, definition.simulation_id)
    await source.open()
    try:
        source_schema = source.schema()
        sample = await source.next_frame()
        effective_schema = []
        mapped_sample = None
        mapping_error: str | None = None
        try:
            effective_schema = map_schema(
                source_schema,
                definition.mappings,
                definition.drop_unmapped_signals,
            )
            mapped_sample = (
                map_frame(sample, definition.mappings, definition.drop_unmapped_signals)
                if sample is not None
                else None
            )
        except ValueError as exc:
            mapping_error = str(exc)

        return {
            "simulation_id": definition.simulation_id,
            "source_kind": definition.source.kind,
            "source_count": source.count,
            "source_position": source.position,
            "source_schema": [item.model_dump() for item in source_schema],
            "effective_schema": [item.model_dump() for item in effective_schema],
            "sample_frame": mapped_sample.model_dump() if mapped_sample is not None else None,
            "raw_sample_frame": sample.model_dump() if sample is not None else None,
            "mapping_error": mapping_error,
        }
    finally:
        await source.close()
