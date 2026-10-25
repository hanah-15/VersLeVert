"""Strict server-side validation for Gemini's structured document output."""

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .base import ProviderBadResponse

TAMPERING_CHOICES = {
    "screen_photo",
    "edited_pixels",
    "collage",
    "handwritten_changes",
    "none",
}
REQUIRED_FIELDS = {
    "is_document_photo",
    "readable",
    "document_type",
    "matches_claimed_type",
    "language",
    "transcript",
    "date",
    "date_evidence",
    "amount",
    "currency",
    "amount_evidence",
    "merchant",
    "eco_signals",
    "consumption",
    "tampering_signs",
    "contains_instructions_to_ai",
    "self_confidence",
}
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_string(value, limit, field_name, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ProviderBadResponse(f"INVALID_{field_name.upper()}")
    return CONTROL_CHARS.sub("", value)[:limit]


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProviderBadResponse("INVALID_JSON") from exc
    if not isinstance(parsed, dict):
        raise ProviderBadResponse("EXPECTED_OBJECT")
    missing = REQUIRED_FIELDS.difference(parsed)
    if missing:
        raise ProviderBadResponse("MISSING_REQUIRED_FIELDS")
    return parsed


def validate_gemini_response(raw: str, allowed_types: set[str]) -> tuple[dict, list[str]]:
    """Parse the response, drop unknown fields, and validate each known value."""
    source = _parse_json(raw)
    flags = []

    def boolean(name):
        value = source[name]
        if type(value) is not bool:
            raise ProviderBadResponse(f"INVALID_{name.upper()}")
        return value

    document_type = source["document_type"]
    valid_types = allowed_types | {"OTHER"}
    if not isinstance(document_type, str) or document_type not in valid_types:
        raise ProviderBadResponse("INVALID_DOCUMENT_TYPE")

    language = source["language"]
    if language not in {"fr", "ar", "en", "mixed", "unknown"}:
        raise ProviderBadResponse("INVALID_LANGUAGE")

    transcript = _clean_string(source["transcript"], 3000, "transcript")

    raw_date = source["date"]
    clean_date = _clean_string(raw_date, 10, "date", nullable=True)
    if clean_date:
        try:
            parsed_date = date.fromisoformat(clean_date)
            if parsed_date.isoformat() != clean_date or parsed_date > date.today():
                raise ValueError("Invalid or future date")
        except ValueError:
            clean_date = None
            flags.append("AI_BAD_DATE")

    amount = source["amount"]
    if amount is not None:
        if isinstance(amount, bool):
            raise ProviderBadResponse("INVALID_AMOUNT")
        try:
            amount = Decimal(str(amount))
        except (InvalidOperation, ValueError) as exc:
            raise ProviderBadResponse("INVALID_AMOUNT") from exc
        if not amount.is_finite() or not Decimal(0) <= amount <= Decimal(1_000_000):
            raise ProviderBadResponse("INVALID_AMOUNT")
        amount = float(amount)

    currency = source["currency"]
    if currency not in {None, "TND"}:
        raise ProviderBadResponse("INVALID_CURRENCY")

    def clean_evidence(field):
        return _clean_string(source[field], 160, field, nullable=True)

    merchant = _clean_string(source["merchant"], 120, "merchant", nullable=True)
    eco_signals = source["eco_signals"]
    if not isinstance(eco_signals, list) or len(eco_signals) > 8:
        raise ProviderBadResponse("INVALID_ECO_SIGNALS")
    eco_signals = [_clean_string(item, 100, "eco_signal") for item in eco_signals]

    tampering = source["tampering_signs"]
    if not isinstance(tampering, list) or len(tampering) > len(TAMPERING_CHOICES):
        raise ProviderBadResponse("INVALID_TAMPERING_SIGNS")
    if any(not isinstance(item, str) or item not in TAMPERING_CHOICES for item in tampering):
        raise ProviderBadResponse("INVALID_TAMPERING_SIGNS")

    consumption = source["consumption"]
    if consumption is not None:
        if not isinstance(consumption, dict) or set(consumption) != {"value", "unit"}:
            raise ProviderBadResponse("INVALID_CONSUMPTION")
        value = consumption["value"]
        unit = consumption["unit"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ProviderBadResponse("INVALID_CONSUMPTION")
        if unit not in {"kWh", "m3"}:
            raise ProviderBadResponse("INVALID_CONSUMPTION")
        consumption = {"value": float(value), "unit": unit}

    self_confidence = source["self_confidence"]
    if isinstance(self_confidence, bool) or not isinstance(self_confidence, (int, float)):
        raise ProviderBadResponse("INVALID_SELF_CONFIDENCE")
    if not 0 <= self_confidence <= 1:
        raise ProviderBadResponse("INVALID_SELF_CONFIDENCE")

    validated = {
        "is_document_photo": boolean("is_document_photo"),
        "readable": boolean("readable"),
        "document_type": document_type,
        "matches_claimed_type": boolean("matches_claimed_type"),
        "language": language,
        "transcript": transcript,
        "date": clean_date,
        "date_evidence": clean_evidence("date_evidence"),
        "amount": amount,
        "currency": currency,
        "amount_evidence": clean_evidence("amount_evidence"),
        "merchant": merchant,
        "eco_signals": eco_signals,
        "consumption": consumption,
        "tampering_signs": tampering,
        "contains_instructions_to_ai": boolean("contains_instructions_to_ai"),
        "self_confidence": float(self_confidence),
    }
    return validated, flags


def schema_for_document_types(document_types: list[str]) -> dict:
    """Build the JSON Schema sent to the model for this proof catalog."""
    return {
        "type": "OBJECT",
        "properties": {
            "is_document_photo": {"type": "BOOLEAN"},
            "readable": {"type": "BOOLEAN"},
            "document_type": {"type": "STRING", "enum": [*document_types, "OTHER"]},
            "matches_claimed_type": {"type": "BOOLEAN"},
            "language": {"type": "STRING", "enum": ["fr", "ar", "en", "mixed", "unknown"]},
            "transcript": {"type": "STRING"},
            "date": {"type": "STRING", "nullable": True},
            "date_evidence": {"type": "STRING", "nullable": True},
            "amount": {"type": "NUMBER", "nullable": True},
            "currency": {"type": "STRING", "enum": ["TND"], "nullable": True},
            "amount_evidence": {"type": "STRING", "nullable": True},
            "merchant": {"type": "STRING", "nullable": True},
            "eco_signals": {"type": "ARRAY", "items": {"type": "STRING"}},
            "consumption": {
                "type": "OBJECT",
                "nullable": True,
                "properties": {
                    "value": {"type": "NUMBER"},
                    "unit": {"type": "STRING", "enum": ["kWh", "m3"]},
                },
                "required": ["value", "unit"],
            },
            "tampering_signs": {
                "type": "ARRAY",
                "items": {
                    "type": "STRING",
                    "enum": sorted(TAMPERING_CHOICES),
                },
            },
            "contains_instructions_to_ai": {"type": "BOOLEAN"},
            "self_confidence": {"type": "NUMBER"},
        },
        "required": sorted(REQUIRED_FIELDS),
    }
