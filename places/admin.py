from django.contrib import admin
from django.utils import timezone

from .models import Place, ProductRecommendation, RecommendationLike


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "address", "created_by")
    list_filter = ("category",)
    search_fields = ("name", "address", "description")
    readonly_fields = ("created_by", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ProductRecommendation)
class ProductRecommendationAdmin(admin.ModelAdmin):
    list_display = ("product_name", "user", "category", "status", "place", "created_at")
    list_filter = ("status", "category")
    search_fields = ("product_name", "description", "user__email", "place__name")
    readonly_fields = ("user", "moderated_by", "moderated_at", "created_at", "updated_at")
    list_select_related = ("user", "place")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.user = request.user
        if obj.status != ProductRecommendation.Status.PENDING:
            obj.moderated_by = request.user
            obj.moderated_at = timezone.now()
        if obj.status != ProductRecommendation.Status.REJECTED:
            obj.rejection_reason = ""
        super().save_model(request, obj, form, change)


@admin.register(RecommendationLike)
class RecommendationLikeAdmin(admin.ModelAdmin):
    list_display = ("recommendation", "user", "created_at")
    readonly_fields = ("recommendation", "user", "created_at")
    search_fields = ("recommendation__product_name", "user__email")

    def has_add_permission(self, request):
        return False
