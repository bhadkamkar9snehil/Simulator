from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from app.models import GeneratorSpec, GenerateRequest


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
