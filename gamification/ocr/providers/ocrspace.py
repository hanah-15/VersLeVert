"""OCR.space REST provider using multipart requests and explicit error mapping."""

import json
import logging
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .base import (
    ProviderBadResponse,
    ProviderQuotaExceeded,
    ProviderResult,
    ProviderTimeout,
    ProviderUnavailable,
)
from .prepare import prepare_for_provider

logger = logging.getLogger(__name__)
API_URL = "https://api.ocr.space/parse/image"


class OcrSpaceProvider:
    name = "ocrspace"

    def extract(self, pages: list[bytes], proof_type) -> ProviderResult:
        if not settings.OCRSPACE_API_KEY:
            raise ProviderUnavailable("OCR.space API key is not configured.")
        started = time.perf_counter()
        deadline = time.monotonic() + settings.PROOF_AI_TIMEOUT_SECONDS
        texts = []
        for request_count, page in enumerate(pages[:3], start=1):
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ProviderTimeout("OCR.space request timed out.")
                image = prepare_for_provider(page, self.name)
                payload = self._request(image, timeout=remaining)
                parsed_results = payload.get("ParsedResults")
                if not isinstance(parsed_results, list):
                    raise ProviderBadResponse("MISSING_PARSED_RESULTS")
                texts.extend(
                    item.get("ParsedText", "")
                    for item in parsed_results
                    if isinstance(item, dict) and isinstance(item.get("ParsedText", ""), str)
                )
            except (ProviderQuotaExceeded, ProviderBadResponse, ProviderTimeout, ProviderUnavailable) as exc:
                exc.request_count = request_count
                raise

        transcript = "\n\n".join(text for text in texts if text).strip()
        return ProviderResult(
            provider=self.name,
            model="ocrspace-engine-2",
            transcript=transcript,
            mean_confidence=None,
            usage={"requests": min(len(pages), 3)},
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def _request(self, image_bytes: bytes, timeout=None) -> dict:
        boundary = f"----VersLeVert{uuid.uuid4().hex}"
        fields = {
            "language": "fre",
            "OCREngine": "2",
            "isOverlayRequired": "false",
            "scale": "true",
            "detectOrientation": "true",
        }
        body = bytearray()
        for key, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
            body.extend(f"{value}\r\n".encode())
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            b'Content-Disposition: form-data; name="file"; filename="proof.jpg"\r\n'
            b"Content-Type: image/jpeg\r\n\r\n"
        )
        body.extend(image_bytes)
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        request = Request(
            API_URL,
            data=bytes(body),
            headers={
                "apikey": settings.OCRSPACE_API_KEY,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urlopen(
                request,
                timeout=timeout or settings.PROOF_AI_TIMEOUT_SECONDS,
            ) as response:
                response_body = response.read()
        except HTTPError as exc:
            if exc.code == 429:
                raise ProviderQuotaExceeded("OCR.space quota exceeded.") from exc
            if exc.code >= 500:
                raise ProviderUnavailable("OCR.space service is unavailable.") from exc
            raise ProviderBadResponse(f"HTTP_{exc.code}") from exc
        except TimeoutError as exc:
            raise ProviderTimeout("OCR.space request timed out.") from exc
        except URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, TimeoutError):
                raise ProviderTimeout("OCR.space request timed out.") from exc
            raise ProviderUnavailable("OCR.space network request failed.") from exc
        except OSError as exc:
            raise ProviderUnavailable("OCR.space network request failed.") from exc

        try:
            result = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderBadResponse("INVALID_JSON") from exc
        if not isinstance(result, dict):
            raise ProviderBadResponse("INVALID_RESPONSE")
        if result.get("IsErroredOnProcessing"):
            message = result.get("ErrorMessage", "")
            text = " ".join(message) if isinstance(message, list) else str(message)
            if any(marker in text.lower() for marker in ("quota", "limit", "429", "apikey")):
                raise ProviderQuotaExceeded("OCR.space reported a quota or key error.")
            raise ProviderBadResponse("PROCESSING_ERROR")
        return result
