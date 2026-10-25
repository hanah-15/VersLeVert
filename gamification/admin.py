"""
Gamification admin — M1-A
Registers all six models with useful list_display, filters, and actions.
PointsTransaction is read-only (immutable ledger — BR-01).
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import Badge, EcoProof, ImpactFactor, OcrAnalysis, PointsTransaction, UserBadge


# ---------------------------------------------------------------------------
# EcoProof
# ---------------------------------------------------------------------------

@admin.register(EcoProof)
class EcoProofAdmin(admin.ModelAdmin):
    list_display  = ["id", "user", "proof_type", "proof_date", "status_badge", "submitted_at"]
    list_filter   = ["status", "proof_type"]
    search_fields = ["user__email", "user__username"]
    readonly_fields = ["file_hash", "submitted_at", "reviewed_by", "reviewed_at", "created_at", "updated_at"]
    ordering      = ["-submitted_at"]

    actions = ["action_approve", "action_needs_review"]

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colours = {
            "PENDING":      "orange",
            "APPROVED":     "green",
            "NEEDS_REVIEW": "blue",
            "REJECTED":     "red",
        }
        color = colours.get(obj.status, "grey")
        return format_html(
            '<span style="color:{};font-weight:bold">{}</span>',
            color, obj.get_status_display(),
        )

    @admin.action(description="Approuver les preuves sélectionnées")
    def action_approve(self, request, queryset):
        from gamification.services import PointsService
        approved = 0
        for proof in queryset.filter(status=EcoProof.Status.PENDING):
            proof.approve(request.user)
            PointsService.credit(
                user=proof.user,
                action_type=proof.proof_type,
                quantity=1,
                source_type="eco_proof",
                source_id=proof.pk,
                reason=f"Preuve approuvée : {proof.get_proof_type_display()}",
            )
            approved += 1
        self.message_user(request, f"{approved} preuve(s) approuvée(s) et points crédités.")

    @admin.action(description="Marquer comme 'à revoir'")
    def action_needs_review(self, request, queryset):
        count = 0
        for proof in queryset.filter(status=EcoProof.Status.PENDING):
            proof.flag_for_review(request.user)
            count += 1
        self.message_user(request, f"{count} preuve(s) marquée(s) 'À examiner'.")


# ---------------------------------------------------------------------------
# OcrAnalysis
# ---------------------------------------------------------------------------

@admin.register(OcrAnalysis)
class OcrAnalysisAdmin(admin.ModelAdmin):
    list_display  = ["id", "eco_proof", "decision", "confidence_score", "engine", "processed_at"]
    readonly_fields = [f.name for f in OcrAnalysis._meta.get_fields() if hasattr(f, "name")]
    list_filter   = ["decision", "engine"]


# ---------------------------------------------------------------------------
# ImpactFactor
# ---------------------------------------------------------------------------

@admin.register(ImpactFactor)
class ImpactFactorAdmin(admin.ModelAdmin):
    list_display  = ["action_type", "label", "unit", "points_per_unit", "co2_kg_per_unit", "is_active"]
    list_editable = ["points_per_unit", "co2_kg_per_unit", "is_active"]
    list_filter   = ["is_active", "unit"]
    search_fields = ["action_type", "label"]
    ordering      = ["action_type"]


# ---------------------------------------------------------------------------
# PointsTransaction — read-only ledger
# ---------------------------------------------------------------------------

@admin.register(PointsTransaction)
class PointsTransactionAdmin(admin.ModelAdmin):
    list_display  = ["id", "user", "direction_badge", "points", "action_type", "balance_after", "created_at"]
    list_filter   = ["direction", "action_type"]
    search_fields = ["user__email", "user__username", "reason"]
    ordering      = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Sens")
    def direction_badge(self, obj):
        colours = {"CREDIT": "green", "DEBIT": "red", "ADJUSTMENT": "blue"}
        color   = colours.get(obj.direction, "grey")
        sign    = "+" if obj.points >= 0 else ""
        return format_html(
            '<span style="color:{};font-weight:bold">{}{} pts</span>',
            color, sign, obj.points,
        )


# ---------------------------------------------------------------------------
# Badge
# ---------------------------------------------------------------------------

@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display  = ["icon", "name", "code", "tier", "criteria_type", "threshold", "is_active"]
    list_editable = ["is_active"]
    list_filter   = ["tier", "criteria_type", "is_active"]
    search_fields = ["code", "name"]
    ordering      = ["tier", "threshold"]


# ---------------------------------------------------------------------------
# UserBadge
# ---------------------------------------------------------------------------

@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display  = ["user", "badge", "awarded_at"]
    list_filter   = ["badge__tier"]
    search_fields = ["user__email", "badge__name"]
    ordering      = ["-awarded_at"]

    def has_add_permission(self, request):
        return False
