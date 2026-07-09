from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from app.models import GeneratorSpec, GenerateRequest


def historian_datetime_text(value: datetime) -> str:
    milliseconds = value.microsecond // 1000
    return f"{value:%Y-%m-%d %H:%M:%S}.{milliseconds:03d}"


class DomainGenerator(ABC):
    domain_id: str
    display_name: str
    description: str

    @abstractmethod
    def get_spec(self) -> GeneratorSpec:
        raise NotImplementedError

    @abstractmethod
    def generate(self, request: GenerateRequest) -> list[dict[str, Any]]:
        raise NotImplementedError
