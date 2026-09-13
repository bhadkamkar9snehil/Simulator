from __future__ import annotations

from typing import Any

from app.type_inference import convert_value

from .models import SignalDefinition, SignalMapping, SignalValue, SimulationFrame


def map_schema(
    schema: list[SignalDefinition],
    mappings: list[SignalMapping],
    drop_unmapped: bool = False,
) -> list[SignalDefinition]:
    enabled = [mapping for mapping in mappings if mapping.enabled]
    if not enabled:
        return [] if drop_unmapped else list(schema)

    source_by_name = {signal.name: signal for signal in schema}
    mapped_sources = {mapping.source for mapping in enabled}
    result = {} if drop_unmapped else {
        name: signal for name, signal in source_by_name.items() if name not in mapped_sources
    }

    for mapping in enabled:
        source = source_by_name.get(mapping.source)
        if source is None:
            raise ValueError(f"Signal mapping source not found: {mapping.source}")
        target = mapping.target or mapping.source
        if target in result:
            raise ValueError(f"Signal mapping target conflicts with an existing signal: {target}")
        result[target] = source.model_copy(update={
            "name": target,
            "node_id": mapping.node_id or target,
            "data_type": mapping.data_type or source.data_type,
            "unit": mapping.unit if mapping.unit is not None else source.unit,
        })
    return list(result.values())


def map_frame(
    frame: SimulationFrame,
    mappings: list[SignalMapping],
    drop_unmapped: bool = False,
) -> SimulationFrame:
    enabled = [mapping for mapping in mappings if mapping.enabled]
    if not enabled:
        return frame.model_copy(update={"values": {}}) if drop_unmapped else frame

    mapped_sources = {mapping.source for mapping in enabled}
    values = {} if drop_unmapped else {
        name: signal for name, signal in frame.values.items() if name not in mapped_sources
    }

    for mapping in enabled:
        source = frame.values.get(mapping.source)
        if source is None:
            raise ValueError(f"Signal mapping source not found in frame: {mapping.source}")
        target = mapping.target or mapping.source
        if target in values:
            raise ValueError(f"Signal mapping target conflicts with an existing signal: {target}")
        values[target] = _map_value(source, mapping)

    return frame.model_copy(update={"values": values})


def _map_value(signal: SignalValue, mapping: SignalMapping) -> SignalValue:
    data_type = mapping.data_type or signal.data_type
    value = signal.value
    scaled = mapping.scale != 1.0 or mapping.offset != 0.0

    if value is not None and scaled:
        if signal.data_type == "Boolean" or data_type == "Boolean":
            raise ValueError(f"Cannot apply numeric scaling to Boolean signal: {mapping.source}")
        try:
            value = float(value) * mapping.scale + mapping.offset
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Signal mapping requires a numeric value: {mapping.source}") from exc

    if value is not None and (scaled or mapping.data_type is not None):
        value = convert_value(value, data_type)

    metadata: dict[str, Any] = {**signal.metadata, **mapping.metadata}
    return signal.model_copy(update={
        "value": value,
        "data_type": data_type,
        "unit": mapping.unit if mapping.unit is not None else signal.unit,
        "quality": mapping.quality if mapping.quality is not None else signal.quality,
        "metadata": metadata,
    })
