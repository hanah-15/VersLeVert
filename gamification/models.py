"""
Gamification models — M1-A
Covers: EcoProof, OcrAnalysis, ImpactFactor, PointsTransaction, Badge, UserBadge.

Naming conventions (from projectsummary.md §5):
  - All tables carry id, created_at, updated_at.
  - FK to User always uses settings.AUTH_USER_MODEL.
  - Model names in English, UI labels in French.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# EcoProof — preuves écologiques soumises par le citoyen (PT-01)
# ---------------------------------------------------------------------------

class EcoProof(models.Model):

    class ProofType(models.TextChoices):
        ELECTRICITY_BILL   = "ELECTRICITY_BILL",  "Facture d'électricité"
        TRANSPORT_TICKET   = "TRANSPORT_TICKET",  "Ticket de transport"
        TEXTILE_LABEL      = "TEXTILE_LABEL",     "Étiquette textile"
        OTHER              = "OTHER",              "Autre"

    class Status(models.TextChoices):
        PENDING      = "PENDING",      "En attente"
        APPROVED     = "APPROVED",     "Approuvée"
        NEEDS_REVIEW = "NEEDS_REVIEW", "À examiner"
        REJECTED     = "REJECTED",     "Rejetée"

    user         = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eco_proofs",
        verbose_name="utilisateur",
    )
    proof_type   = models.CharField(
        max_length=30,
        choices=ProofType.choices,
        verbose_name="type de preuve",
    )
    file         = models.FileField(
        upload_to="eco_proofs/%Y/%m/",
        verbose_name="fichier",
    )
    source_url   = models.URLField(
        blank=True,
        verbose_name="URL source (optionnel)",
    )
    proof_date   = models.DateField(verbose_name="date de la preuve")
    # SHA-256 of the uploaded file — enforces BR-06 (no duplicate file)
    file_hash    = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="empreinte du fichier",
    )
    status       = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="statut",
    )
    rejection_reason = models.TextField(
        blank=True,
        verbose_name="motif de rejet",
    )
    reviewed_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_proofs",
        verbose_name="examiné par",
    )
    reviewed_at  = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="examiné le",
    )
    submitted_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="soumis le",
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Preuve écologique"
        verbose_name_plural = "Preuves écologiques"

    def __str__(self):
        return f"{self.get_proof_type_display()} — {self.user} ({self.get_status_display()})"

    def approve(self, admin_user):
        """Approve the proof and record the reviewer."""
        self.status = self.Status.APPROVED
        self.rejection_reason = ""
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"])

    def reject(self, admin_user, reason):
        """Reject the proof with a mandatory reason."""
        self.status = self.Status.REJECTED
        self.rejection_reason = reason
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"])

    def flag_for_review(self, admin_user):
        """Flag the proof as needing manual review."""
        self.status = self.Status.NEEDS_REVIEW
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])


# ---------------------------------------------------------------------------
# OcrAnalysis — résultat de l'analyse OCR liée à une EcoProof (PT-02)
# ---------------------------------------------------------------------------

class OcrAnalysis(models.Model):
    eco_proof        = models.OneToOneField(
        EcoProof,
        on_delete=models.CASCADE,
        related_name="ocr_analysis",
        verbose_name="preuve liée",
    )
    raw_text         = models.TextField(
        blank=True,
        verbose_name="texte brut extrait",
    )
    extracted_date   = models.DateField(
        null=True,
        blank=True,
        verbose_name="date extraite",
    )
    extracted_merchant = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="marchand extrait",
    )
    extracted_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="montant extrait",
    )
    confidence_score = models.FloatField(
        default=0.0,
        verbose_name="score de confiance",
    )
    # Decision: APPROVED, NEEDS_REVIEW, REJECTED
    decision         = models.CharField(
        max_length=15,
        blank=True,
        verbose_name="décision OCR",
    )
    engine           = models.CharField(
        max_length=50,
        default="manual",
        verbose_name="moteur OCR",
    )
    processed_at     = models.DateTimeField(
        default=timezone.now,
        verbose_name="traité le",
    )
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Analyse OCR"
        verbose_name_plural = "Analyses OCR"

    def __str__(self):
        return f"OCR #{self.eco_proof_id} — confiance {self.confidence_score:.0%}"


# ---------------------------------------------------------------------------
# ImpactFactor — barème admin (PT-09): action_type → pts & CO2 per unit
# ---------------------------------------------------------------------------

class ImpactFactor(models.Model):

    class Unit(models.TextChoices):
        KG    = "kg",    "Kilogramme"
        COUNT = "count", "Unité"
        PROOF = "proof", "Preuve"

    action_type      = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="type d'action",
        help_text="Identifiant unique de l'action (ex: WASTE_ORGANIC, TRANSPORT_TICKET).",
    )
    label            = models.CharField(
        max_length=120,
        verbose_name="libellé",
    )
    unit             = models.CharField(
        max_length=10,
        choices=Unit.choices,
        verbose_name="unité",
    )
    points_per_unit  = models.PositiveIntegerField(
        verbose_name="points par unité",
    )
    co2_kg_per_unit  = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=0,
        verbose_name="kg CO₂ évité par unité",
    )
    is_active        = models.BooleanField(
        default=True,
        verbose_name="actif",
    )
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["action_type"]
        verbose_name = "Facteur d'impact"
        verbose_name_plural = "Facteurs d'impact (barème)"

    def __str__(self):
        return f"{self.label} ({self.action_type}) — {self.points_per_unit} pts/{self.unit}"


# ---------------------------------------------------------------------------
# PointsTransaction — ledger immuable (BR-01, BR-02, PT-08)
# ---------------------------------------------------------------------------

class PointsTransaction(models.Model):

    class Direction(models.TextChoices):
        CREDIT     = "CREDIT",     "Crédit"
        DEBIT      = "DEBIT",      "Débit"
        ADJUSTMENT = "ADJUSTMENT", "Ajustement"

    user             = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="points_transactions",
        verbose_name="utilisateur",
    )
    direction        = models.CharField(
        max_length=12,
        choices=Direction.choices,
        verbose_name="sens",
    )
    # Semantic type: WASTE_ORGANIC, TRANSPORT_TICKET, CHALLENGE_BONUS, REWARD_REDEEM, etc.
    action_type      = models.CharField(
        max_length=50,
        verbose_name="type d'action",
    )
    quantity         = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        verbose_name="quantité",
    )
    # Positive for credit, negative for debit/adjustment
    points           = models.IntegerField(verbose_name="points (signé)")
    balance_after    = models.IntegerField(verbose_name="solde après")
    # Generic FK-like fields to trace the origin (waste collection, event, etc.)
    source_type      = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="type source",
    )
    source_id        = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="id source",
    )
    reason           = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="raison",
    )
    # Snapshot of the ImpactFactor values at the time of the transaction
    factor_snapshot  = models.JSONField(
        null=True,
        blank=True,
        verbose_name="snapshot du facteur",
    )
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        # BR-02: each (user, source_type, source_id, reason) is unique → no double-credit
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source_type", "source_id", "reason"],
                condition=models.Q(source_type__gt=""),
                name="gamification_tx_unique_source",
            )
        ]
        verbose_name = "Transaction de points"
        verbose_name_plural = "Transactions de points"

    def __str__(self):
        sign = "+" if self.points >= 0 else ""
        return f"{self.user} {sign}{self.points} pts ({self.action_type}) → solde {self.balance_after}"

    # Transactions are immutable — no save() after creation.
    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("PointsTransaction is immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("PointsTransaction cannot be deleted.")


# ---------------------------------------------------------------------------
# Badge — définition d'un badge (PT-10, PT-11)
# ---------------------------------------------------------------------------

class Badge(models.Model):

    class Tier(models.TextChoices):
        BRONZE = "BRONZE", "Bronze"
        SILVER = "SILVER", "Argent"
        GOLD   = "GOLD",   "Or"

    class CriteriaType(models.TextChoices):
        TOTAL_POINTS    = "TOTAL_POINTS",    "Total de points"
        ACTION_COUNT    = "ACTION_COUNT",    "Nombre d'actions"
        ACTION_QUANTITY = "ACTION_QUANTITY", "Quantité d'actions"

    code                 = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="code",
    )
    name                 = models.CharField(
        max_length=120,
        verbose_name="nom",
    )
    description          = models.TextField(
        blank=True,
        verbose_name="description",
    )
    # Emoji or image path for the badge icon
    icon                 = models.CharField(
        max_length=10,
        default="🏅",
        verbose_name="icône (emoji)",
    )
    tier                 = models.CharField(
        max_length=8,
        choices=Tier.choices,
        verbose_name="palier",
    )
    criteria_type        = models.CharField(
        max_length=20,
        choices=CriteriaType.choices,
        verbose_name="type de critère",
    )
    # Restrict to a specific action_type (nullable = any action counts)
    criteria_action_type = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="action_type requis (optionnel)",
    )
    threshold            = models.PositiveIntegerField(
        verbose_name="seuil",
        help_text="Valeur à atteindre pour débloquer ce badge.",
    )
    is_active            = models.BooleanField(
        default=True,
        verbose_name="actif",
    )
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tier", "threshold"]
        verbose_name = "Badge"
        verbose_name_plural = "Badges"

    def __str__(self):
        return f"{self.icon} {self.name} ({self.get_tier_display()})"


# ---------------------------------------------------------------------------
# UserBadge — badges obtenus par un utilisateur (PT-10)
# ---------------------------------------------------------------------------

class UserBadge(models.Model):
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_badges",
        verbose_name="utilisateur",
    )
    badge      = models.ForeignKey(
        Badge,
        on_delete=models.CASCADE,
        related_name="user_badges",
        verbose_name="badge",
    )
    awarded_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="obtenu le",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "badge"],
                name="gamification_userbadge_unique",
            )
        ]
        ordering = ["-awarded_at"]
        verbose_name = "Badge utilisateur"
        verbose_name_plural = "Badges utilisateurs"

    def __str__(self):
        return f"{self.user} → {self.badge}"
