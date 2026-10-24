"""Server-side Gemini access for the places and recommendations module."""

import httpx
from django.conf import settings
from google import genai
from google.genai import types
# google-genai 2.33 exposes Interactions errors through this compatibility module.
from google.genai._gaos.lib.compat_errors import APIConnectionError, APIError


class GeminiUnavailableError(Exception):
    """An AI request could not be completed; its message contains no credentials."""


def generate_text(prompt, *, max_output_tokens=1024):
    if not settings.GEMINI_API_KEY:
        raise GeminiUnavailableError("GEMINI_API_KEY is missing from the local .env file.")
    if not prompt.strip():
        raise ValueError("A non-empty prompt is required.")

    try:
        with genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=settings.GEMINI_TIMEOUT_SECONDS * 1000,
                retry_options=types.HttpRetryOptions(attempts=0),
            ),
        ) as client:
            response = client.interactions.create(
                model=settings.GEMINI_MODEL,
                input=prompt,
                generation_config={
                    "max_output_tokens": max_output_tokens,
                    "thinking_level": "low",
                },
                store=False,
                timeout=settings.GEMINI_TIMEOUT_SECONDS,
            )
    except (APIConnectionError, httpx.HTTPError):
        raise GeminiUnavailableError("Gemini could not be reached within the configured timeout.") from None
    except APIError as exc:
        if exc.status_code == 429:
            message = "Gemini quota or rate limit reached. Retry later or check your AI Studio quota."
        elif exc.status_code in (401, 403):
            message = "Gemini refused access. Check the API key and project permissions."
        else:
            message = f"Gemini request failed (HTTP {exc.status_code}). Check the configured model and API status."
        raise GeminiUnavailableError(message) from None

    text = response.output_text
    if not text or not text.strip():
        raise GeminiUnavailableError("Gemini returned no text. Retry with a different prompt.")
    return text.strip()
