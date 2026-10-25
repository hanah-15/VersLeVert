from django.contrib import admin, messages
from django.utils import timezone
from .models import Event, EventRegistration


@admin.action(description="Valider et publier les événements sélectionnés")
def publish_events(modeladmin, request, queryset):
    updated = queryset.filter(status=Event.Status.PENDING).update(status=Event.Status.PUBLISHED)
    modeladmin.message_user(
        request,
        f"{updated} événement(s) validé(s) et publié(s).",
        messages.SUCCESS,
    )


@admin.action(description="Refuser les événements sélectionnés")
def refuse_events(modeladmin, request, queryset):
    updated = queryset.filter(status=Event.Status.PENDING).update(status=Event.Status.REFUSED)
    modeladmin.message_user(
        request,
        f"{updated} événement(s) refusé(s).",
        messages.WARNING,
    )


@admin.action(description="Générer l'analyse IA de modération pour les événements sélectionnés")
def run_ai_moderation(modeladmin, request, queryset):
    count = 0
    for ev in queryset:
        try:
            ev.generate_moderation_ai()
            count += 1
        except Exception:
            pass
    modeladmin.message_user(
        request,
        f"Analyse IA effectuée pour {count} événement(s).",
        messages.INFO,
    )


class EventRegistrationInline(admin.TabularInline):
    model = EventRegistration
    extra = 0
    readonly_fields = ("registered_at", "points_awarded", "points_amount")
    can_delete = True


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "organizer",
        "date",
        "location",
        "status",
        "capacity",
        "registrations_count",
        "confirmed_attendees_count",
        "co2_avoided",
        "points_reward",
    )
    list_filter = ("status", "date")
    search_fields = (
        "title",
        "objective",
        "location",
        "organizer__email",
        "organizer__username",
    )
    actions = [publish_events, refuse_events, run_ai_moderation]
    inlines = [EventRegistrationInline]

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    "title",
                    "objective",
                    "location",
                    "date",
                    "capacity",
                    "organizer",
                    "status",
                    "points_reward",
                )
            },
        ),
        (
            "Résultats (après clôture)",
            {
                "fields": (
                    "collected_quantity",
                    "actual_participants_count",
                    "result_summary",
                    "closed_at",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Fonctionnalités & Données IA",
            {
                "fields": (
                    "co2_avoided",
                    "ai_impact_analysis",
                    "ai_checklist",
                    "ai_moderation_notes",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        # E-02 : Événement admin créé directement publié immédiatement
        if not change:
            if not obj.organizer_id:
                obj.organizer = request.user
            if request.user.is_staff or request.user.is_superuser or getattr(request.user, "is_admin_user", False):
                obj.status = Event.Status.PUBLISHED
        super().save_model(request, obj, form, change)


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "user",
        "registered_at",
        "present",
        "points_awarded",
        "points_amount",
    )
    list_filter = ("present", "points_awarded", "event__status")
    search_fields = (
        "event__title",
        "user__email",
        "user__username",
    )
    readonly_fields = ("registered_at",)
