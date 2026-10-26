from django.contrib import admin

from .models import Offer, RewardCode


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("title", "sponsor", "points_cost", "active", "created_at")
    list_filter = ("active", "created_at")
    search_fields = ("title", "description", "sponsor__business_name")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("sponsor", "title", "description", "points_cost", "active")}),
        ("Images", {"fields": ("image", "image_url", "images_url")}),
        ("Dates", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(RewardCode)
class RewardCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "offer", "redeemed_by", "redeemed_at", 'used_at')
    list_filter = ("redeemed_at", 'used_at')
    search_fields = ("code", "offer__title")
    readonly_fields = ('code', 'offer', 'redeemed_by', 'redeemed_at', 'used_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
