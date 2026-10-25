"""Provider registry for proof-document extraction."""

from django.conf import settings

from .base import (
    OcrProvider,
    ProviderBadResponse,
    ProviderQuotaExceeded,
    ProviderResult,
    ProviderTimeout,
    ProviderUnavailable,
)

_PROVIDERS = {
    "tesseract": "gamification.ocr.providers.tesseract.TesseractProvider",
    "ocrspace": "gamification.ocr.providers.ocrspace.OcrSpaceProvider",
    "gemini": "gamification.ocr.providers.gemini.GeminiProvider",
}


def get_provider(name: str) -> OcrProvider:
    """Create a configured provider by its stable registry name."""
    try:
        module_path, class_name = _PROVIDERS[name].rsplit(".", 1)
    except KeyError as exc:
        raise ValueError(f"Unknown OCR provider: {name!r}") from exc
    from importlib import import_module

    provider_class = getattr(import_module(module_path), class_name)
    return provider_class()


def get_chain() -> list[OcrProvider]:
    """Return the providers in configured fallback order."""
    names = getattr(settings, "PROOF_OCR_PROVIDERS", ["tesseract"])
    return [get_provider(name) for name in names]


__all__ = [
    "OcrProvider",
    "ProviderBadResponse",
    "ProviderQuotaExceeded",
    "ProviderResult",
    "ProviderTimeout",
    "ProviderUnavailable",
    "get_chain",
    "get_provider",
]
