from decimal import Decimal

from django.db.models import Count, Sum

from .models import Status, WasteRequest


def _impact_for_requests(queryset):
    totals = queryset.aggregate(
        co2=Sum("co2_avoided"),
        kg=Sum("confirmed_weight"),
        count=Count("pk"),
    )
    return {
        "co2": totals["co2"] or Decimal("0"),
        "kg": totals["kg"] or Decimal("0"),
        "count": totals["count"],
    }


def user_impact(user):
    confirmed = WasteRequest.objects.filter(status=Status.CONFIRMED)
    return {
        "declared": _impact_for_requests(confirmed.filter(user=user)),
        "collected": _impact_for_requests(confirmed.filter(collector=user)),
    }
