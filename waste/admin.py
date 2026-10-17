from django.contrib import admin
from .models import EmissionFactor, WasteRequest, WasteStatusLog


@admin.register(WasteRequest)
class WasteRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "waste_type", "estimated_weight", "confirmed_weight",
                    "status", "collector", "created_at")
    list_filter = ("status", "waste_type")
    search_fields = ("user__username", "address")


@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ("waste_type", "kg_co2_per_kg", "source")


admin.site.register(WasteStatusLog)