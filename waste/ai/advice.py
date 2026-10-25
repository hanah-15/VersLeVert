"""Personalized eco-advice generation and caching."""

import hashlib
import json
import re
import time
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum
from django.utils import timezone
from google import genai
from google.genai.errors import APIError, ClientError, ServerError
from google.genai.types import GenerateContentConfig, HttpOptions

from django.conf import settings

from .service import AIInvalidResponseError, AIUnavailableError
from ..models import EcoAdvice, Status, WasteRequest, WasteType
from ..services import user_impact


SYSTEM_PROMPT = """Tu es un conseiller de tri écologique. Réponds uniquement en JSON
avec un summary d'une seule phrase et exactement trois conseils courts dans tips.
Chaque conseil contient title et text, en français.
Tu ne dois jamais inventer un chiffre, une équivalence (arbres, kilomètres), ni donner
un conseil médical ou juridique. Utilise seulement les statistiques fournies.
N'ajoute aucun nombre qui ne figure pas dans les statistiques."""

ADVICE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "tips": {
            "type": "ARRAY",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "text": {"type": "STRING"},
                },
                "required": ["title", "text"],
            },
        },
    },
    "required": ["summary", "tips"],
}


def _number(value):
    return float(value or 0)


def build_stats(user):
    """Build only aggregate confirmed statistics for a user."""
    confirmed = WasteRequest.objects.filter(user=user, status=Status.CONFIRMED)
    recent = confirmed.filter(
        confirmed_at__gte=timezone.now() - timedelta(days=30)
    )
    impact = user_impact(user)["declared"]
    totals = confirmed.aggregate(kg=Sum("confirmed_weight"), count=Count("pk"))
    by_type = {
        row["waste_type"]: _number(row["kg"])
        for row in confirmed.values("waste_type").annotate(kg=Sum("confirmed_weight"))
    }
    recent_total = recent.aggregate(kg=Sum("confirmed_weight"))["kg"]
    return {
        "co2_total_kg": _number(impact["co2"]),
        "kg_sorted": _number(totals["kg"]),
        "collections_count": totals["count"],
        "organic_kg": by_type.get(WasteType.ORGANIC, 0.0),
        "plastic_kg": by_type.get(WasteType.PLASTIC, 0.0),
        "kg_last_30_days": _number(recent_total),
    }


def _validate_advice(advice):
    if not isinstance(advice, dict) or not isinstance(advice.get("summary"), str):
        raise ValueError("Réponse de conseil invalide.")
    tips = advice.get("tips")
    if (
        not isinstance(tips, list)
        or len(tips) != 3
        or any(
            not isinstance(tip, dict)
            or not isinstance(tip.get("title"), str)
            or not isinstance(tip.get("text"), str)
            or not tip["title"].strip()
            or not tip["text"].strip()
            for tip in tips
        )
    ):
        raise ValueError("La réponse doit contenir exactement trois conseils.")
    return {
        "summary": advice["summary"].strip(),
        "tips": [
            {"title": tip["title"].strip(), "text": tip["text"].strip()}
            for tip in tips
        ],
    }


def generate_advice(stats):
    """Generate and validate grounded advice through Gemini."""
    if not settings.GEMINI_API_KEY:
        raise AIUnavailableError("La clé API Gemini n'est pas configurée.")
    try:
        client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=HttpOptions(
                timeout=int(settings.GEMINI_TIMEOUT_SECONDS * 1000)
            ),
        )
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=json.dumps(stats, ensure_ascii=False),
            config=GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ADVICE_SCHEMA,
            ),
        )
        return _validate_advice(json.loads(response.text))
    except (APIError, OSError, TimeoutError) as exc:
        raise AIUnavailableError("Le service Gemini est indisponible.") from exc
    except (AttributeError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise AIInvalidResponseError("La réponse du conseil n'est pas un JSON valide.") from exc


def validate_grounding(stats, advice):
    """Check every number in advice against an aggregate statistic."""
    allowed = [float(value) for value in stats.values() if isinstance(value, (int, float, Decimal))]
    text = json.dumps(advice, ensure_ascii=False)
    numbers = [float(value.replace(",", ".")) for value in re.findall(r"(?<![\w.])-?\d+(?:[,.]\d+)?", text)]
    unanchored = [
        number for number in numbers
        if not any(abs(number - candidate) <= 0.1 for candidate in allowed)
    ]
    return (not unanchored, unanchored)


def fallback_advice(stats):
    """Return exactly three rule-based, number-grounded tips."""
    if stats["plastic_kg"] > stats["organic_kg"]:
        first = {
            "title": "Réduire le plastique",
            "text": "Privilégiez les emballages réutilisables et triez chaque emballage plastique.",
        }
    elif stats["organic_kg"] > 0:
        first = {
            "title": "Valoriser l'organique",
            "text": "Séparez les déchets organiques pour faciliter leur valorisation.",
        }
    else:
        first = {
            "title": "Commencer progressivement",
            "text": "Triez chaque déchet dans la filière adaptée dès que possible.",
        }
    return {
        "summary": "Votre bilan confirme vos efforts de tri.",
        "tips": [
            first,
            {
                "title": "Garder le rythme",
                "text": "Conservez vos bonnes habitudes de tri au quotidien.",
            },
            {
                "title": "Vérifier les consignes",
                "text": "Consultez les consignes locales avant de déposer un déchet.",
            },
        ],
    }


def _stats_hash(stats):
    return hashlib.sha256(
        json.dumps(stats, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def get_or_create_advice(user):
    """Return the cached advice for unchanged stats, otherwise generate it."""
    stats = build_stats(user)
    stats_hash = _stats_hash(stats)
    latest = EcoAdvice.objects.filter(user=user).first()
    if latest and latest.stats_hash == stats_hash:
        return latest

    started = time.perf_counter()
    source = "ai"
    grounded = True
    try:
        advice = generate_advice(stats)
        grounded, _ = validate_grounding(stats, advice)
        if not grounded:
            advice = generate_advice(stats)
            grounded, _ = validate_grounding(stats, advice)
        if not grounded:
            raise ValueError("Conseil non ancré.")
    except (AIUnavailableError, AIInvalidResponseError, OSError, TimeoutError, ValueError):
        advice = fallback_advice(stats)
        source = "fallback"
        grounded = True

    return EcoAdvice.objects.create(
        user=user,
        payload=advice,
        stats_hash=stats_hash,
        source=source,
        grounded=grounded,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
