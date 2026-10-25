"""Resolve an approximate neighbourhood name; exact distances remain local."""
import hashlib
import math

import httpx
from django.conf import settings
from django.core import signing
from django.core.cache import cache


SALT = "places.detected-area.v1"


class LocationUnavailable(Exception):
    pass


def _coordinate_pair(data):
    return [f"{float(data[key]):.6f}" for key in ("latitude", "longitude")]


def read_location_label(data):
    try:
        payload = signing.loads(data.get("location_token", ""), salt=SALT, max_age=86400)
        if payload["coordinates"] == _coordinate_pair(data):
            return payload["label"]
    except (signing.BadSignature, KeyError, TypeError, ValueError, OverflowError):
        pass
    return ""


def _area_label(payload):
    address = payload.get("address")
    if not isinstance(address, dict):
        return ""
    names = []
    for group in (
        ("neighbourhood", "suburb", "quarter", "village", "town", "city", "municipality"),
        ("city", "town", "municipality", "county", "state"),
    ):
        name = next((address[key].strip() for key in group if isinstance(address.get(key), str) and address[key].strip()), "")
        if name and name.casefold() not in [value.casefold() for value in names]:
            names.append(name)
    return ", ".join(names)[:180]


def resolve_location(data):
    # Three decimals (~100 m) suffice for an area label. Do not send exact GPS
    # precision, identity, saved profile data, or the user's review to the provider.
    latitude, longitude = (round(float(data[key]), 3) for key in ("latitude", "longitude"))
    if not all(math.isfinite(value) for value in (latitude, longitude)):
        raise LocationUnavailable()
    key = "places:area:" + hashlib.sha256(f"{latitude}:{longitude}".encode()).hexdigest()
    label = cache.get(key)
    if label is None:
        # The public provider allows at most one request/second per application.
        # A multi-process deployment must use a shared, atomic cache backend.
        if not cache.add("places:geocoder-gate", True, timeout=1.1):
            raise LocationUnavailable()
        try:
            response = httpx.get(
                settings.PLACES_GEOCODER_URL,
                params={"lat": latitude, "lon": longitude, "format": "jsonv2", "zoom": 14, "addressdetails": 1, "accept-language": "fr,en"},
                headers={"User-Agent": settings.PLACES_GEOCODER_USER_AGENT},
                timeout=5,
            )
            response.raise_for_status()
            payload = response.json()
            label = _area_label(payload) if isinstance(payload, dict) else ""
            if not label:
                raise ValueError("No named area")
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            cache.set(key, "", timeout=60)
            raise LocationUnavailable() from None
        cache.set(key, label, timeout=86400)
    if not label:
        raise LocationUnavailable()
    return {
        "label": label,
        "location_token": signing.dumps({"coordinates": _coordinate_pair(data), "label": label}, salt=SALT, compress=True),
    }
