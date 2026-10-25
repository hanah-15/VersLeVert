"""Gemini-backed waste description analysis."""

import json
import socket
from typing import Any

import httpx
from django.conf import settings
from google import genai
from google.genai.errors import APIError, ClientError, ServerError
from google.genai.types import GenerateContentConfig, HttpOptions


SYSTEM_PROMPT = """Tu es un assistant de tri des déchets.
Analyse la description fournie et réponds uniquement avec le JSON demandé.
Les catégories autorisées sont organic, plastic, mixed et not_accepted.
N'invente jamais une quantité : si la phrase n'en indique pas une explicitement,
utilise null pour quantity.value et quantity.unit.
L'explication doit être une seule phrase en français."""

ALLOWED_WASTE_TYPES = frozenset({"organic", "plastic", "mixed", "not_accepted"})
ALLOWED_UNITS = frozenset({"liter", "item", "bag", "kg"})


class AIUnavailableError(Exception):
    """Raised when Gemini cannot be reached or used."""


class AIInvalidResponseError(Exception):
    """Raised when Gemini returns an invalid analysis."""


def _validate_response(response: Any) -> dict[str, Any]:
    try:
        payload = json.loads(response.text)
    except (AttributeError, TypeError, json.JSONDecodeError) as exc:
        raise AIInvalidResponseError("La réponse de l'IA n'est pas un JSON valide.") from exc

    if not isinstance(payload, dict):
        raise AIInvalidResponseError("La réponse de l'IA doit être un objet JSON.")

    waste_type = payload.get("waste_type")
    confidence = payload.get("confidence")
    quantity = payload.get("quantity")
    explanation = payload.get("explanation")
    if (
        waste_type not in ALLOWED_WASTE_TYPES
        or isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
        or not isinstance(quantity, dict)
        or not isinstance(explanation, str)
        or not explanation.strip()
    ):
        raise AIInvalidResponseError("La réponse de l'IA ne respecte pas le format attendu.")

    value = quantity.get("value")
    unit = quantity.get("unit")
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise AIInvalidResponseError("La quantité retournée est invalide.")
    if unit is not None and unit not in ALLOWED_UNITS:
        raise AIInvalidResponseError("L'unité retournée est invalide.")
    if (value is None) != (unit is None):
        raise AIInvalidResponseError("La valeur et l'unité doivent être nulles ensemble.")

    return {
        "waste_type": waste_type,
        "confidence": float(confidence),
        "quantity": {"value": value, "unit": unit},
        "explanation": explanation.strip(),
    }


def analyze_description(text: str) -> dict[str, Any]:
    """Classify a waste description using Gemini's structured JSON output."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("La description du déchet ne peut pas être vide.")
    if len(text) > 500:
        raise ValueError("La description du déchet ne peut pas dépasser 500 caractères.")

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise AIUnavailableError("La clé API Gemini n'est pas configurée.")

    config = GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema={
            "type": "OBJECT",
            "properties": {
                "waste_type": {"type": "STRING", "enum": sorted(ALLOWED_WASTE_TYPES)},
                "confidence": {"type": "NUMBER"},
                "quantity": {
                    "type": "OBJECT",
                    "properties": {
                        "value": {"type": "NUMBER", "nullable": True},
                        "unit": {
                            "type": "STRING",
                            "enum": sorted(ALLOWED_UNITS),
                            "nullable": True,
                        },
                    },
                    "required": ["value", "unit"],
                },
                "explanation": {"type": "STRING"},
            },
            "required": ["waste_type", "confidence", "quantity", "explanation"],
        },
    )

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=HttpOptions(
                timeout=int(settings.GEMINI_TIMEOUT_SECONDS * 1000)
            ),
        )
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=text,
            config=config,
        )
    except (
        APIError,
        ClientError,
        ServerError,
        httpx.HTTPError,
        OSError,
        socket.timeout,
        TimeoutError,
    ) as exc:
        if isinstance(exc, ServerError) and getattr(exc, "code", None) in {503, 504}:
            message = "Gemini est temporairement très sollicité. Réessayez dans quelques instants."
        elif isinstance(exc, ClientError) and getattr(exc, "code", None) in {401, 403}:
            message = "La clé Gemini est invalide ou n'a pas accès à ce modèle."
        else:
            message = "Le service Gemini est indisponible. Vérifiez votre clé et votre connexion."
        raise AIUnavailableError(message) from exc

    return _validate_response(response)
