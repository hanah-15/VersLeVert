from django.contrib import admin
from django.utils import timezone
from .models import (
    Challenge,
    ChallengeMilestone,
    ChallengeMilestoneAchievement,
    ChallengeParticipation,
    ChallengeReminder,
    ProgressEntry,
)


class ProgressEntryInline(admin.TabularInline):
    model = ProgressEntry
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "challenge_type",
        "goal_value",
        "unit",
        "points_reward",
        "is_community",
        "status",
        "start_date",
        "end_date",
        "created_by",
        "created_at",
    )
    list_filter = ("challenge_type", "status", "unit", "created_at")
    search_fields = ("title", "description", "created_by__username", "created_by__email")
    date_hierarchy = "created_at"
    actions = ["close_challenges", "activate_challenges"]

    @admin.action(description="Clôturer les défis sélectionnés")
    def close_challenges(self, request, queryset):
        updated = queryset.update(status=Challenge.Status.CLOSED)
        self.message_user(request, f"{updated} défi(s) clôturé(s).")

    @admin.action(description="Activer les défis sélectionnés")
    def activate_challenges(self, request, queryset):
        updated = queryset.update(status=Challenge.Status.ACTIVE)
        self.message_user(request, f"{updated} défi(s) activé(s).")

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ChallengeParticipation)
class ChallengeParticipationAdmin(admin.ModelAdmin):
    list_display = (
        "challenge",
        "user",
        "progress_value",
        "goal_display",
        "percentage_display",
        "completed_at",
        "points_awarded",
        "joined_at",
    )
    list_filter = ("points_awarded", "challenge__challenge_type", "joined_at")
    search_fields = ("challenge__title", "user__username", "user__email")
    readonly_fields = ("joined_at", "completed_at", "points_awarded")
    inlines = [ProgressEntryInline]

    @admin.display(description="Objectif")
    def goal_display(self, obj):
        return f"{obj.challenge.goal_value} {obj.challenge.unit}"

    @admin.display(description="Avancement")
    def percentage_display(self, obj):
        return f"{obj.percentage}%"


@admin.register(ProgressEntry)
class ProgressEntryAdmin(admin.ModelAdmin):
    list_display = ("participation", "value", "note", "created_at")
    list_filter = ("created_at",)
    search_fields = (
        "participation__challenge__title",
        "participation__user__username",
        "participation__user__email",
        "note",
    )
    readonly_fields = ("created_at",)


@admin.register(ChallengeMilestone)
class ChallengeMilestoneAdmin(admin.ModelAdmin):
    list_display = ("challenge", "title", "threshold", "reward_points")
    list_filter = ("threshold",)
    search_fields = ("challenge__title", "title")


@admin.register(ChallengeReminder)
class ChallengeReminderAdmin(admin.ModelAdmin):
    list_display = ("user", "challenge", "frequency", "enabled", "last_sent_at")
    list_filter = ("frequency", "enabled")
    search_fields = ("user__email", "challenge__title")


@admin.register(ChallengeMilestoneAchievement)
class ChallengeMilestoneAchievementAdmin(admin.ModelAdmin):
    list_display = ("user", "milestone", "achieved_at")
    list_filter = ("achieved_at",)
    search_fields = ("user__email", "milestone__title")
