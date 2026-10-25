from django.contrib import admin
from .models import CollectionOffer, EmissionFactor, WasteRequest, WasteStatusLog


@admin.register(WasteRequest)
class WasteRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "waste_type", "estimated_weight", "status",
                    "collector", "planned_date")
    list_filter = ("status", "waste_type")
    search_fields = ("user__username", "collector__username")


@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ("waste_type", "kg_co2_per_kg", "source")


admin.site.register(WasteStatusLog)


@admin.register(CollectionOffer)
class CollectionOfferAdmin(admin.ModelAdmin):
    list_display = ("waste_request", "collector", "status", "proposed_date", "created_at")
    list_filter = ("status",)
    search_fields = ("collector__username", "waste_request__user__username")