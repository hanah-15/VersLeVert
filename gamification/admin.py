"""
Gamification admin — M1-A
Registers all six models with useful list_display, filters, and actions.
PointsTransaction is read-only (immutable ledger — BR-01).
"""

from django.contrib import admin
from django.contrib.admin.helpers import ActionForm
from django import forms
from django.urls import reverse
from django.utils.html import format_html

from .models import Badge, EcoProof, ImpactFactor, OcrAnalysis, PointsTransaction, ProofType, UserBadge


# ---------------------------------------------------------------------------
# EcoProof
# ---------------------------------------------------------------------------

@admin.register(EcoProof)
class EcoProofAdmin(admin.ModelAdmin):
    list_display  = ["id", "user", "proof_type", "status_badge", "score_display", "submitted_at", "source"]
    list_filter   = ["status", "proof_type", "source"]
    search_fields = ["user__email", "user__username"]
    readonly_fields = [
        "file_sha256", "phash", "fingerprint", "submitted_at", "reviewed_by",
        "reviewed_at", "created_at", "updated_at", "proof_preview", "ocr_summary",
        "monthly_type_count",
    ]
    fields = [
        "user", "proof_type", "status", "source", "proof_preview", "document_date",
        "merchant", "amount", "points_awarded", "rejection_code", "rejection_reason_fr",
        "monthly_type_count", "ocr_summary", "file_sha256", "phash", "fingerprint",
        "reviewed_by", "reviewed_at", "review_note", "submitted_at", "processed_at",
    ]
    ordering = ["-submitted_at"]

    actions = ["action_approve", "action_reject", "action_needs_review"]
    action_form = type(
        "ProofActionForm",
        (ActionForm,),
        {
            "rejection_reason": forms.ChoiceField(
                required=False,
                choices=[
                    ("", "Motif de rejet"),
                    ("Illisible", "Illisible"),
                    ("Mauvais type", "Mauvais type"),
                    ("Document trop ancien", "Document trop ancien"),
                    ("Doublon", "Doublon"),
                    ("Suspicion de falsification", "Suspicion de falsification"),
                    ("Autre", "Autre"),
                ],
            ),
            "rejection_detail": forms.CharField(required=False, label="Précisions", max_length=500),
        },
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if (
            getattr(request.resolver_match, "url_name", "") == "gamification_ecoproof_changelist"
            and "status__exact" not in request.GET
            and not request.GET.get("q")
        ):
            qs = qs.filter(status=EcoProof.Status.NEEDS_REVIEW)
        return qs

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

    @admin.display(description="Score")
    def score_display(self, obj):
        try:
            return f"{obj.ocr_analysis.score:.2f}"
        except OcrAnalysis.DoesNotExist:
            return "—"

    @admin.display(description="Aperçu")
    def proof_preview(self, obj):
        if not obj.has_file:
            return "Fichier indisponible"
        return format_html(
            '<img src="{}" alt="Aperçu de la preuve" style="max-width:420px;max-height:520px">',
            reverse("proofs:file", args=[obj.pk]),
        )

    @admin.display(description="Analyse OCR")
    def ocr_summary(self, obj):
        try:
            analysis = obj.ocr_analysis
        except OcrAnalysis.DoesNotExist:
            return "Analyse non disponible"
        return format_html(
            "Score : {} · Confiance : {} · Mots-clés : {}<details><summary>Texte OCR</summary><pre>{}</pre><p>Qualité : {}</p><p>Drapeaux : {}</p>",
            analysis.score,
            analysis.mean_confidence,
            ", ".join(str(i) for i in analysis.matched_groups),
            analysis.raw_text,
            analysis.quality_metrics,
            ", ".join(analysis.flags),
        )

    @admin.display(description="Preuves approuvées pour ce type ce mois-ci")
    def monthly_type_count(self, obj):
        from django.utils import timezone
        start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return EcoProof.objects.filter(
            user=obj.user,
            proof_type=obj.proof_type,
            status=EcoProof.Status.APPROVED,
            submitted_at__gte=start,
        ).count()

    @admin.action(description="Approuver les preuves sélectionnées")
    def action_approve(self, request, queryset):
        from gamification.services.pipeline import approve_proof
        approved = 0
        needs_review = 0
        for proof in queryset.filter(status__in=[EcoProof.Status.PENDING, EcoProof.Status.NEEDS_REVIEW]):
            result = approve_proof(proof.pk, admin_user=request.user)
            if result.status == EcoProof.Status.APPROVED:
                approved += 1
            else:
                needs_review += 1
        self.message_user(
            request,
            f"{approved} preuve(s) approuvée(s) ; {needs_review} refusée(s) ou à examiner "
            "(plafond atteint ou barème absent).",
        )

    @admin.action(description="Rejeter les preuves sélectionnées (motif obligatoire)")
    def action_reject(self, request, queryset):
        from accounts.models import Notification
        reason = request.POST.get("rejection_reason", "").strip()
        detail = request.POST.get("rejection_detail", "").strip()
        if not reason:
            self.message_user(request, "Choisissez un motif de rejet dans le formulaire d'action.", level="ERROR")
            return
        if reason == "Autre" and not detail:
            self.message_user(request, "Précisez le motif lorsque vous choisissez « Autre ».", level="ERROR")
            return
        description = f"{reason} — {detail}" if detail else reason
        count = 0
        for proof in queryset.exclude(status=EcoProof.Status.APPROVED):
            proof.reject("ADMIN_REJECTED", description, admin_user=request.user, note=description)
            Notification.objects.create(user=proof.user, message=f"Preuve refusée : {description}"[:255])
            count += 1
        self.message_user(request, f"{count} preuve(s) rejetée(s).")

    @admin.action(description="Marquer comme 'à revoir'")
    def action_needs_review(self, request, queryset):
        count = 0
        for proof in queryset.exclude(status=EcoProof.Status.APPROVED):
            proof.send_to_review(request.user)
            count += 1
        self.message_user(request, f"{count} preuve(s) marquée(s) 'À examiner'.")


@admin.register(ProofType)
class ProofTypeAdmin(admin.ModelAdmin):
    list_display = ["label_fr", "code", "category", "points_link", "cap_count", "cap_period", "window_days", "always_review", "is_active"]
    list_filter = ["category", "cap_period", "always_review", "is_active"]
    search_fields = ["code", "label_fr"]
    list_editable = ["cap_count", "cap_period", "window_days", "always_review", "is_active"]
    fields = [
        "code", "category", "label_fr", "description_fr", "tips_fr", "icon",
        "action_type", "keyword_groups", "min_groups", "requires_date",
        "requires_amount", "window_days", "cap_count", "cap_period",
        "always_review", "photo_only", "is_active",
    ]

    @admin.display(description="Points")
    def points_link(self, obj):
        factor = obj.get_impact_factor()
        if not factor:
            return "Facteur absent"
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:gamification_impactfactor_change", args=[factor.pk]),
            factor.points_per_unit,
        )


# ---------------------------------------------------------------------------
# OcrAnalysis
# ---------------------------------------------------------------------------

@admin.register(OcrAnalysis)
class OcrAnalysisAdmin(admin.ModelAdmin):
    list_display  = ["id", "eco_proof", "decision", "mean_confidence", "engine", "processed_at"]
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
