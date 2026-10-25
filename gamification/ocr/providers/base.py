"""Shared types and errors for document extraction providers."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ProviderResult:
    provider: str
    model: str | None
    transcript: str
    mean_confidence: float | None
    fields: dict | None = None
    flags: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    latency_ms: int = 0
    raw_excerpt: str | None = None


class OcrProvider(Protocol):
    name: str

    def extract(self, pages: list[bytes], proof_type) -> ProviderResult: ...


class ProviderError(Exception):
    """Base class for expected provider failures."""

    def __init__(self, message, request_count=1):
        super().__init__(message)
        self.request_count = request_count


class ProviderTimeout(ProviderError):
    pass


class ProviderQuotaExceeded(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class ProviderBadResponse(ProviderError):
    pass
