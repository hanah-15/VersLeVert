from django.db.models import Count, Q
from accounts.utils import distance_km
from .models import Place, ProductRecommendation


def find_places(data):
    queryset = Place.objects.annotate(product_count=Count("recommendations", filter=Q(
        recommendations__status=ProductRecommendation.Status.APPROVED))).order_by("name", "pk")
    if data.get("q"):
        queryset = queryset.filter(Q(name__icontains=data["q"]) | Q(address__icontains=data["q"]) | Q(description__icontains=data["q"]))
    if data.get("category"):
        queryset = queryset.filter(category=data["category"])
    if data.get("latitude") is None or data.get("longitude") is None:
        return queryset
    places = list(queryset)
    for place in places:
        place.distance = distance_km(float(data["latitude"]), float(data["longitude"]), float(place.latitude), float(place.longitude))
    if data.get("radius") is not None:
        places = [place for place in places if place.distance <= float(data["radius"])]
    return sorted(places, key=lambda place: (place.distance, place.name, place.pk))


def suggest_from_catalogue(query, *, filters=None, user_id=None):
    """Synchronous HTML adapter; the fetch endpoint awaits the same pipeline."""
    from asgiref.sync import async_to_sync
    from .guide import search_catalogue

    return async_to_sync(search_catalogue)({**(filters or {}), "query": query}, user_id=user_id)
