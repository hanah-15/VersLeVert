"""Server-side Groq recommendations for the challenges module."""

import httpx
from django.conf import settings


class GroqUnavailableError(Exception):
    """Raised when Groq cannot return a recommendation."""


def recommend_challenges(profile, challenges, *, timeout=None):
    if not settings.GROQ_API_KEY:
        raise GroqUnavailableError("GROQ_API_KEY est absent du fichier .env.")

    challenge_data = [
        {
            "title": challenge.title,
            "description": challenge.description,
            "goal": f"{challenge.goal_value} {challenge.unit}",
            "type": challenge.get_challenge_type_display(),
            "points": challenge.points_reward,
            "participants": challenge.participations.count(),
        }
        for challenge in challenges
    ]
    if not challenge_data:
        return "Aucun défi actif n'est disponible pour le moment."

    prompt = (
        "Tu es le coach écologique de Vers le Vert. "
        "Recommande au maximum trois défis parmi la liste fournie. "
        "Réponds en français, avec une recommandation par ligne : "
        "titre exact, raison courte et conseil pratique. "
        "N'invente aucun défi et ne donne pas de données personnelles.\n\n"
        f"Profil utilisateur : {profile}\n"
        f"Défis disponibles : {challenge_data}"
    )
    payload = {
        "model": settings.GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Tu produis des recommandations brèves, positives et vérifiables.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": settings.GROQ_MAX_TOKENS,
    }
    try:
        response = httpx.post(
            settings.GROQ_API_URL,
            headers={
                "Authorization": "Bearer " + settings.GROQ_API_KEY,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout or settings.GROQ_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            message = "La clé Groq est refusée. Vérifiez GROQ_API_KEY."
        elif exc.response.status_code == 404:
            message = (
                f"Le modèle Groq « {settings.GROQ_MODEL} » est introuvable ou retiré. "
                "Mettez à jour GROQ_MODEL dans le fichier .env."
            )
        elif exc.response.status_code == 429:
            message = "Le quota Groq est atteint. Réessayez plus tard."
        else:
            message = f"Groq a retourné une erreur HTTP {exc.response.status_code}."
        raise GroqUnavailableError(message) from None
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise GroqUnavailableError(
            "Le service de recommandations Groq est temporairement indisponible."
        ) from exc

    if not text:
        raise GroqUnavailableError("Groq n'a retourné aucune recommandation.")
    return text
