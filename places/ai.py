"""Server-side Gemini access for the places and recommendations module."""

import asyncio
import logging

import httpx
from django.conf import settings
from google import genai
from google.genai import types
from google.genai.errors import APIError as ContentAPIError
# google-genai 2.33 exposes Interactions errors through this compatibility module.
from google.genai._gaos.lib.compat_errors import APIConnectionError, APIError

logger = logging.getLogger(__name__)


class GeminiUnavailableError(Exception):
    """An AI request could not be completed; its message contains no credentials."""


async def generate_json(question, *, system_instruction, schema):
    """One bounded asynchronous request, with a schema enforced by Gemini.

    Only query interpretation is generated. No catalogue or account data is sent.
    """
    if not settings.GEMINI_API_KEY:
        raise GeminiUnavailableError("Gemini is not configured.")
    timeout = max(10, min(float(settings.PLACES_GEMINI_TIMEOUT_SECONDS), 20))
    try:
        with genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=int(timeout * 1000), retry_options=types.HttpRetryOptions(attempts=0)),
        ) as client:
            async with client.aio as async_client:
                response = await asyncio.wait_for(async_client.models.generate_content(
                    model=settings.PLACES_GEMINI_MODEL,
                    contents=question,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction, response_mime_type="application/json",
                        response_json_schema=schema, max_output_tokens=1200,
                        thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                    ),
                ), timeout=timeout)
    except (TimeoutError, APIConnectionError, APIError, ContentAPIError, httpx.HTTPError, OSError) as exc:
        logger.warning("Places guide provider unavailable (%s, HTTP %s).", type(exc).__name__, getattr(exc, "code", "n/a"))
        raise GeminiUnavailableError("Gemini is temporarily unavailable.") from None
    if not isinstance(response.text, str) or not response.text.strip():
        raise GeminiUnavailableError("Gemini returned no structured search.")
    return response.text


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
