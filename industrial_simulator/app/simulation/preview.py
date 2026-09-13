from __future__ import annotations

from typing import Any

from .mapping import map_frame, map_schema
from .models import SimulationDefinition
from .sources import create_source


async def preview_definition(definition: SimulationDefinition) -> dict[str, Any]:
    """Open one configured source without starting targets and return its effective schema.

    The preview path deliberately uses the same source and canonical mapping code as
    the runtime so the UI does not need source-specific schema logic.
    """

    source = create_source(definition.source, definition.simulation_id)
    await source.open()
    try:
        source_schema = source.schema()
        mapped_schema = map_schema(
            source_schema,
            definition.mappings,
            definition.drop_unmapped_signals,
        )
        sample = await source.next_frame()
        mapped_sample = (
            map_frame(sample, definition.mappings, definition.drop_unmapped_signals)
            if sample is not None
            else None
        )
        return {
            "simulation_id": definition.simulation_id,
            "source_kind": definition.source.kind,
            "source_count": source.count,
            "source_position": source.position,
            "source_schema": [item.model_dump() for item in source_schema],
            "effective_schema": [item.model_dump() for item in mapped_schema],
            "sample_frame": mapped_sample.model_dump() if mapped_sample is not None else None,
        }
    finally:
        await source.close()
