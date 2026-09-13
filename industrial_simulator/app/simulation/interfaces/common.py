from __future__ import annotations

import re

from app.models import TagMapping

from ..models import SignalDefinition


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._-")
    return cleaned or "item"


def tag_mapping(signal: SignalDefinition, node_id: str, tag_name: str | None = None) -> TagMapping:
    return TagMapping(
        enabled=True,
        csv_column=signal.name,
        tag_name=tag_name or signal.name,
        node_id=node_id,
        data_type=signal.data_type,
        initial_value=signal.initial_value,
        writable=signal.writable,
    )
