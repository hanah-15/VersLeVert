"""Services d'intelligence artificielle Gemini pour le module Événements écologiques."""

import json
import logging
import re
from decimal import Decimal

import httpx
from django.conf import settings
from google import genai
from google.genai import types
from google.genai._gaos.lib.compat_errors import APIConnectionError, APIError

logger = logging.getLogger(__name__)


class GeminiUnavailableError(Exception):
    """Exception levée lorsque Gemini n'est pas disponible ou non configuré."""


def generate_text(prompt: str, *, max_output_tokens: int = 1024) -> str:
    """Appelle l'API Gemini pour générer une réponse textuelle."""
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise GeminiUnavailableError("GEMINI_API_KEY est absent de la configuration.")
    if not prompt.strip():
        raise ValueError("Le prompt ne peut pas être vide.")

    timeout = getattr(settings, "EVENTS_GEMINI_TIMEOUT_SECONDS", 0) or settings.GEMINI_TIMEOUT_SECONDS
    model = getattr(settings, "EVENTS_GEMINI_MODEL", "") or settings.GEMINI_MODEL

    try:
        with genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=timeout * 1000,
                retry_options=types.HttpRetryOptions(attempts=0),
            ),
        ) as client:
            response = client.interactions.create(
                model=model,
                input=prompt,
                generation_config={
                    "max_output_tokens": max_output_tokens,
                    "thinking_level": "low",
                },
                store=False,
                timeout=timeout,
            )
    except (APIConnectionError, httpx.HTTPError) as exc:
        logger.warning("Gemini injoignable: %s", exc)
        raise GeminiUnavailableError("Gemini n'a pas pu être contacté dans les délais.") from None
    except APIError as exc:
        logger.warning("Erreur API Gemini: %s", exc)
        if exc.status_code == 429:
            message = "Quota Gemini dépassé. Veuillez réessayer ultérieurement."
        elif exc.status_code in (401, 403):
            message = "Accès refusé par Gemini. Vérifiez votre clé API."
        else:
            message = f"Échec de l'appel Gemini (HTTP {exc.status_code})."
        raise GeminiUnavailableError(message) from None
    except Exception as exc:
        logger.warning("Erreur inattendue Gemini: %s", exc)
        raise GeminiUnavailableError(f"Erreur Gemini: {exc}") from None

    text = getattr(response, "output_text", None)
    if not text or not text.strip():
        raise GeminiUnavailableError("Gemini a renvoyé une réponse vide.")
    return text.strip()


# ==============================================================================
# Fonctions d'assistance et d'analyse écologique par IA (avec secours intelligent)
# ==============================================================================

def generate_event_proposal_ai(topic: str, location: str = "") -> dict:
    """Génère un titre optimisé, un objectif détaillé, une checklist matérielle et une capacité conseillée."""
    prompt = (
        "Tu es l'assistant expert en écologie et en mobilisation citoyenne de VersLeVert. "
        "À partir de l'idée brute d'un utilisateur et éventuellement d'un lieu, génère un plan complet pour un événement écologique. "
        "Réponds exclusivement avec un objet JSON valide de la forme suivante :\n"
        "{\n"
        '  "title": "Titre accrocheur et précis",\n'
        '  "objective": "Description détaillée de l\'action, déroulé étape par étape et impact attendu (environ 3 à 4 paragraphes courts)",\n'
        '  "checklist": ["Élément 1", "Élément 2", "Élément 3", "Consigne sécurité/zéro-déchet"],\n'
        '  "suggested_capacity": 25,\n'
        '  "impact_focus": "Description en une phrase de l\'impact écologique principal"\n'
        "}\n\n"
        f"Idée: {topic}\n"
        f"Lieu envisagé: {location or 'Non précisé'}\n"
    )

    try:
        raw = generate_text(prompt, max_output_tokens=1500)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
        data = json.loads(raw)
        return {
            "title": str(data.get("title", f"Action citoyenne : {topic}"))[:200],
            "objective": str(data.get("objective", topic)),
            "checklist": list(data.get("checklist", []))[:8],
            "suggested_capacity": int(data.get("suggested_capacity", 20)),
            "impact_focus": str(data.get("impact_focus", "Mobilisation éco-citoyenne")),
            "source": "gemini",
        }
    except Exception:
        # Moteur heuristique écologique de secours (fallback toujours fiable)
        cleaned_topic = topic.strip()
        loc_str = f" à {location}" if location else ""
        return {
            "title": f"Opération collective : {cleaned_topic.capitalize()}{loc_str}",
            "objective": (
                f"Cette action citoyenne a pour but d'agir concrètement pour notre environnement local à travers l'initiative suivante : {cleaned_topic}.\n\n"
                "Déroulement prévu :\n"
                "1. Accueil des participants et briefing sur les consignes de sécurité et de tri.\n"
                "2. Répartition par petits groupes d'action sur le terrain.\n"
                "3. Regroupement, pesée/comptage des réalisations et débriefing convivial.\n\n"
                "Ensemble, nous rendons notre communauté plus propre, plus verte et plus résiliente !"
            ),
            "checklist": [
                "Gants de protection et sacs réutilisables ou cabas solides",
                "Gourde d'eau individuelle (zéro plastique à usage unique)",
                "Tenue adaptée et chaussures fermées confortables",
                "Trousse de premiers secours et gel hydroalcoolique",
                "Bonne humeur et engagement écocitoyen !",
            ],
            "suggested_capacity": 25,
            "impact_focus": f"Action locale éco-responsable axée sur {cleaned_topic}",
            "source": "fallback",
        }


def analyze_environmental_impact_ai(event) -> dict:
    """Analyse l'impact environnemental réel d'un événement clôturé (estimation CO2, équivalences concrètes)."""
    collected = event.collected_quantity or "Action collective"
    participants = event.actual_participants_count or event.confirmed_attendees_count or 1
    prompt = (
        "Tu es l'analyste carbone et impact environnemental de la plateforme VersLeVert. "
        "Analyse les résultats de cet événement écologique et calcule une estimation réaliste de l'impact écologique. "
        "Réponds exclusivement avec un objet JSON valide de la forme suivante :\n"
        "{\n"
        '  "estimated_co2_kg": 42.5,\n'
        '  "equivalences": ["Équivalent à 210 km de voiture thermique évitée", "Équivalent à 350 bouteilles en plastique recyclées"],\n'
        '  "analysis_summary": "Synthèse valorisante de 2 à 3 phrases sur l\'impact direct de l\'action",\n'
        '  "eco_badge_title": "Titre du badge symbolique attribué (ex: Gardiens du Littoral, Planteurs d\'Avenir)"\n'
        "}\n\n"
        f"Titre de l'événement: {event.title}\n"
        f"Objectif: {event.objective}\n"
        f"Lieu: {event.location}\n"
        f"Quantité collectée / Impact mesuré: {collected}\n"
        f"Nombre de participants: {participants}\n"
    )

    try:
        raw = generate_text(prompt, max_output_tokens=1000)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
        data = json.loads(raw)
        co2_val = Decimal(str(data.get("estimated_co2_kg", "25.0"))).quantize(Decimal("0.1"))
        return {
            "estimated_co2_kg": float(co2_val),
            "equivalences": list(data.get("equivalences", []))[:4],
            "analysis_summary": str(data.get("analysis_summary", "")),
            "eco_badge_title": str(data.get("eco_badge_title", "Éco-Héros de la Communauté")),
            "source": "gemini",
        }
    except Exception:
        # Calculateur de secours basé sur des facteurs d'émission réels
        # 1 kg de déchet collecté/recyclé évite en moyenne environ 1.5 kg CO2
        numbers = re.findall(r"\d+(?:[\.,]\d+)?", collected)
        quantity_num = float(numbers[0].replace(",", ".")) if numbers else float(participants * 2.5)
        estimated_co2 = round(quantity_num * 1.5, 1)
        km_auto = int(estimated_co2 * 5.2)  # 1 kg CO2 ~ 5.2 km voiture citadine
        return {
            "estimated_co2_kg": estimated_co2,
            "equivalences": [
                f"Équivaut à environ {km_auto} km de trajet en voiture thermique évités",
                f"Environ {int(quantity_num * 15)} contenants ou emballages détournés de la nature",
                f"Mobilisation citoyenne exemplaire de {participants} participant(s)",
            ],
            "analysis_summary": (
                f"Grâce à l'effort collectif de {participants} bénévoles, cette action a permis de traiter {collected}. "
                f"Un résultat concret qui préserve la biodiversité locale et allège la pression environnementale sur {event.location}."
            ),
            "eco_badge_title": "Bâtisseurs d'Avenir Vert",
            "source": "fallback",
        }


def generate_social_media_kit_ai(event) -> dict:
    """Génère un kit de communication (post Instagram/Facebook, tweet, communiqué court) pour valoriser l'action."""
    collected = event.collected_quantity or "Impact collectif fort"
    participants = event.actual_participants_count or event.confirmed_attendees_count or "Plusieurs"
    prompt = (
        "Tu es le chargé de communication éco-responsable de VersLeVert. "
        "Rédige un kit de partage pour les réseaux sociaux valorisant la réussite de cet événement écologique. "
        "Réponds exclusivement avec un objet JSON valide de la forme suivante :\n"
        "{\n"
        '  "instagram_post": "Texte engageant pour Instagram avec émojis et hashtags pertinents",\n'
        '  "x_post": "Tweet court et percutant de moins de 280 caractères",\n'
        '  "press_snippet": "Paragraphe institutionnel pour un blog ou communiqué de presse local"\n'
        "}\n\n"
        f"Titre: {event.title}\n"
        f"Lieu: {event.location}\n"
        f"Date: {event.date.strftime('%d/%m/%Y')}\n"
        f"Résultat: {collected}\n"
        f"Participants: {participants}\n"
    )

    try:
        raw = generate_text(prompt, max_output_tokens=1000)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
        data = json.loads(raw)
        return {
            "instagram_post": str(data.get("instagram_post", "")),
            "x_post": str(data.get("x_post", ""))[:280],
            "press_snippet": str(data.get("press_snippet", "")),
            "source": "gemini",
        }
    except Exception:
        return {
            "instagram_post": (
                f"🌿 VICTOIRE ÉCOLOGIQUE : {event.title} ! 🌍\n\n"
                f"Un immense merci aux {participants} citoyen(ne)s venu(e)s agir à {event.location}. "
                f"Bilan de notre mobilisation : {collected} !\n\n"
                "Chaque geste compte, ensemble nous passons à l'action concrète. Bravo à toutes et à tous ! 💚\n\n"
                "#VersLeVert #Ecologie #ActionCitoyenne #TransitionEcologique #ZeroDechet"
            ),
            "x_post": (
                f"🌿 Bravo aux {participants} bénévoles mobilisés à {event.location} pour « {event.title} » ! "
                f"Bilan : {collected}. L'action locale fonctionne ! 🌍 #VersLeVert"
            )[:280],
            "press_snippet": (
                f"Le {event.date.strftime('%d/%m/%Y')}, des citoyens engagés de la communauté VersLeVert se sont réunis à {event.location} "
                f"dans le cadre de l'événement « {event.title} ». L'action s'est soldée par un bilan de {collected}, "
                f"démontrant la vitalité et l'impact direct des initiatives écologiques locales."
            ),
            "source": "fallback",
        }


def moderate_event_ai(title: str, objective: str, location: str) -> dict:
    """Analyse un événement pour assister les administrateurs dans leur modération."""
    prompt = (
        "Tu es l'assistant de modération éthique et écologique de VersLeVert. "
        "Évalue la pertinence environnementale et la faisabilité sécuritaire d'une proposition d'événement. "
        "Réponds exclusivement avec un objet JSON valide de la forme suivante :\n"
        "{\n"
        '  "is_eco_relevant": true,\n'
        '  "score": 95,\n'
        '  "recommendation": "APPROVE" ou "REVIEW" ou "REJECT",\n'
        '  "commentary": "Explication claire en 2 phrases pour l\'administrateur",\n'
        '  "safety_tips": ["Conseil 1", "Conseil 2"]\n'
        "}\n\n"
        f"Titre: {title}\n"
        f"Objectif: {objective}\n"
        f"Lieu: {location}\n"
    )

    try:
        raw = generate_text(prompt, max_output_tokens=800)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
        data = json.loads(raw)
        return {
            "is_eco_relevant": bool(data.get("is_eco_relevant", True)),
            "score": int(data.get("score", 90)),
            "recommendation": str(data.get("recommendation", "APPROVE")),
            "commentary": str(data.get("commentary", "Événement conforme aux objectifs environnementaux de la plateforme.")),
            "safety_tips": list(data.get("safety_tips", []))[:3],
            "source": "gemini",
        }
    except Exception:
        # Modération heuristique de secours
        is_relevant = len(objective.strip()) >= 20
        return {
            "is_eco_relevant": is_relevant,
            "score": 90 if is_relevant else 60,
            "recommendation": "APPROVE" if is_relevant else "REVIEW",
            "commentary": (
                "La proposition semble alignée avec la mission écologique de VersLeVert."
                if is_relevant
                else "L'objectif est court : vérifiez les détails avant validation."
            ),
            "safety_tips": [
                "Vérifier l'accessibilité du point de rendez-vous pour les piétons",
                "Recommander des sacs étanches et des gants adaptés",
            ],
            "source": "fallback",
        }
