import hashlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_WINDOW_DAYS = 16
CACHE_SECONDS = 30 * 60

WEATHER_DESCRIPTIONS = {
    0: "Ciel dégagé",
    1: "Majoritairement dégagé",
    2: "Partiellement nuageux",
    3: "Couvert",
    45: "Brouillard",
    48: "Brouillard givrant",
    51: "Bruine légère",
    53: "Bruine modérée",
    55: "Bruine dense",
    56: "Bruine verglaçante légère",
    57: "Bruine verglaçante dense",
    61: "Pluie légère",
    63: "Pluie modérée",
    65: "Forte pluie",
    66: "Pluie verglaçante légère",
    67: "Forte pluie verglaçante",
    71: "Faibles chutes de neige",
    73: "Chutes de neige modérées",
    75: "Fortes chutes de neige",
    77: "Grains de neige",
    80: "Averses légères",
    81: "Averses modérées",
    82: "Fortes averses",
    85: "Faibles averses de neige",
    86: "Fortes averses de neige",
    95: "Orage",
    96: "Orage avec faible grêle",
    99: "Orage avec forte grêle",
}


class WeatherUnavailableError(Exception):
    """Raised when the weather provider cannot supply a forecast."""


def _get_json(url, *, params):
    try:
        response = httpx.get(url, params=params, timeout=5.0)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Weather provider request failed: %s", exc)
        raise WeatherUnavailableError(
            "La météo est momentanément indisponible. Réessayez plus tard."
        ) from None


def get_event_forecast(event):
    if event.date <= timezone.now():
        return {
            "available": False,
            "message": "Les prévisions météo sont disponibles uniquement pour les événements à venir.",
        }

    cache_key = "event-weather:" + hashlib.sha256(
        f"{event.location.strip().casefold()}:{event.date.isoformat()}".encode("utf-8")
    ).hexdigest()
    cached_forecast = cache.get(cache_key)
    if cached_forecast is not None:
        return cached_forecast

    location = _get_json(
        GEOCODING_URL,
        params={"name": event.location, "count": 1, "language": "fr", "format": "json"},
    )
    locations = location.get("results") or []
    if not locations:
        return {
            "available": False,
            "message": "Impossible de localiser ce lieu pour obtenir une prévision météo.",
        }

    place = locations[0]
    forecast = _get_json(
        FORECAST_URL,
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "hourly": (
                "temperature_2m,apparent_temperature,precipitation_probability,"
                "weather_code,wind_speed_10m"
            ),
            "forecast_days": FORECAST_WINDOW_DAYS,
            "timezone": "auto",
        },
    )

    try:
        local_timezone = ZoneInfo(forecast["timezone"])
        event_local_time = event.date.astimezone(local_timezone)
        hourly = forecast["hourly"]
        forecast_times = hourly["time"]
        nearest_index = min(
            range(len(forecast_times)),
            key=lambda index: abs(
                (
                    datetime.fromisoformat(forecast_times[index]).replace(tzinfo=local_timezone)
                    - event_local_time
                ).total_seconds()
            ),
        )
        forecast_time = datetime.fromisoformat(forecast_times[nearest_index]).replace(
            tzinfo=local_timezone
        )
        if abs((forecast_time - event_local_time).total_seconds()) > 30 * 60:
            raise ValueError("No hourly forecast for the event time")

        weather_code = int(hourly["weather_code"][nearest_index])
        result = {
            "available": True,
            "location": ", ".join(
                value for value in (place.get("name"), place.get("country")) if value
            ),
            "forecast_time": event_local_time.strftime("%d/%m/%Y à %H:%M"),
            "description": WEATHER_DESCRIPTIONS.get(weather_code, "Conditions variables"),
            "temperature_c": hourly["temperature_2m"][nearest_index],
            "feels_like_c": hourly["apparent_temperature"][nearest_index],
            "precipitation_probability": hourly["precipitation_probability"][nearest_index],
            "wind_speed_kmh": hourly["wind_speed_10m"][nearest_index],
        }
    except (KeyError, IndexError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        logger.warning("Weather provider returned an unusable forecast: %s", exc)
        raise WeatherUnavailableError(
            "Aucune prévision horaire n'est disponible pour cette date. "
            "Les prévisions sont limitées à environ 16 jours."
        ) from None

    cache.set(cache_key, result, CACHE_SECONDS)
    return result
