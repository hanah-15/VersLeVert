"""Tesseract adapter preserving the existing local OCR implementation."""

from gamification.ocr.engine import read_document

from .base import ProviderResult, ProviderUnavailable


class TesseractProvider:
    name = "tesseract"

    def extract(self, pages: list[bytes], proof_type) -> ProviderResult:
        try:
            result = read_document(pages)
        except (ImportError, OSError) as exc:
            raise ProviderUnavailable("Tesseract is unavailable.") from exc
        return ProviderResult(
            provider=self.name,
            model=None,
            transcript=result.text,
            mean_confidence=result.mean_conf,
            usage={"pages": getattr(result, "pages", len(pages))},
            latency_ms=result.duration_ms,
        )
