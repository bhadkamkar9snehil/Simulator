from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any


def apply_simple_query(
    rows: list[dict[str, Any]],
    filter_text: str = "",
    top: int | None = None,
    skip: int = 0,
    watermark: str | None = None,
    watermark_field: str = "ModifiedUTC",
) -> list[dict[str, Any]]:
    result = list(rows)
    if filter_text:
        match = re.match(r"\s*(\w+)\s+eq\s+'?([^']+)'?\s*$", filter_text, re.IGNORECASE)
        if not match:
            raise ValueError("Only simple equality filters are supported, for example: Plant eq '1001-BHR'.")
        field, value = match.groups()
        result = [row for row in result if str(row.get(field, "")) == value]
    if watermark:
        result = [row for row in result if str(row.get(watermark_field, "")) > watermark]
    if skip:
        result = result[skip:]
    if top is not None:
        result = result[:top]
    return result


class SourceSimulator(ABC):
    connector_id: str
    display_name: str
    description: str

    @abstractmethod
    def spec(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def entities(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def query(
        self,
        entity: str,
        filter_text: str = "",
        top: int | None = None,
        skip: int = 0,
        watermark: str | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def run_cycle(self, **_: Any) -> dict[str, Any]:
        raise ValueError(f"{self.display_name} does not support run_cycle.")
