"""
Gamification models — M1-A (extended for OCR proof module)

Models:
  ProofType          — DB table of proof types + verification rules (editable by admin)
  EcoProof           — citizen eco-proof submission (Cloudinary storage, full anti-fraud fields)
  OcrAnalysis        — OCR pipeline result, 1:1 with EcoProof
  ImpactFactor       — barème admin: action_type → pts & CO2 per unit
  PointsTransaction  — immutable ledger
  Badge / UserBadge  — badge definitions and awards

Naming: English identifiers, French labels (verbose_name).
"""

from __future__ import annotations

import hashlib
import io
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
# ProofType — reference table, seeded by seed_proof_types (§5 / §6.1)
# ─────────────────────────────────────────────────────────────────────────────

class ProofType(models.Model):

    class Category(models.TextChoices):
        MOBILITY     = "MOBILITY",     "Mobilité"
        ENERGY       = "ENERGY",       "Énergie"
        WATER        = "WATER",        "Eau"
        CONSUMPTION  = "CONSUMPTION",  "Consommation"
        TEXTILE      = "TEXTILE",      "Textile"
        WASTE        = "WASTE",        "Déchets"
        ENGAGEMENT   = "ENGAGEMENT",   "Engagement"

    class CapPeriod(models.TextChoices):
        MONTH       = "MONTH",       "Par mois"
        QUARTER     = "QUARTER",     "Par trimestre"
        YEAR        = "YEAR",        "Par an"
        TWO_YEARS   = "TWO_YEARS",   "Tous les 2 ans"

    code            = models.SlugField(max_length=50, unique=True, verbose_name="code")
    category        = models.CharField(max_length=15, choices=Category.choices, verbose_name="catégorie")
    label_fr        = models.CharField(max_length=200, verbose_name="libellé (FR)")
    description_fr  = models.TextField(blank=True, verbose_name="description (FR)")
    tips_fr         = models.TextField(blank=True, verbose_name="conseils photo (FR)")
    icon            = models.CharField(max_length=50, default="camera", verbose_name="icône SVG")

    # Link to ImpactFactor (points barème, single source of truth)
    action_type     = models.CharField(
        max_length=50,
        verbose_name="action_type ImpactFactor",
        help_text="Doit correspondre à un ImpactFactor.action_type actif.",
    )

    # Keyword-based verification
    keyword_groups  = models.JSONField(
        default=list,
        verbose_name="groupes de mots-clés",
        help_text='[{"terms": ["steg", "electricite"], "required": true}, ...]',
    )
    min_groups      = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="groupes min à valider",
    )

    # Document rules
    requires_date   = models.BooleanField(default=True, verbose_name="date obligatoire")
    requires_amount = models.BooleanField(default=False, verbose_name="montant obligatoire")
    window_days     = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="fenêtre de validité (jours)",
        help_text="Laissez vide = pas de restriction de date.",
    )

    # Caps
    cap_count       = models.PositiveSmallIntegerField(verbose_name="nb max de preuves")
    cap_period      = models.CharField(max_length=10, choices=CapPeriod.choices, verbose_name="période du cap")

    # Special modes
    photo_only      = models.BooleanField(
        default=False,
        verbose_name="photo uniquement (pas d'OCR)",
    )
    is_active       = models.BooleanField(default=True, verbose_name="actif")

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "label_fr"]
        verbose_name = "Type de preuve"
        verbose_name_plural = "Types de preuves"

    def __str__(self) -> str:
        return f"{self.label_fr} [{self.code}]"

    def get_impact_factor(self):
        """Return the linked ImpactFactor or None."""
        try:
            return ImpactFactor.objects.get(action_type=self.action_type, is_active=True)
        except ImpactFactor.DoesNotExist:
            return None

    def points_awarded(self) -> int:
        factor = self.get_impact_factor()
        return factor.points_per_unit if factor else 0


# ─────────────────────────────────────────────────────────────────────────────
# EcoProof — citizen proof submission (full OCR-ready, Cloudinary storage)
# ─────────────────────────────────────────────────────────────────────────────

class EcoProof(models.Model):

    class Status(models.TextChoices):
        PENDING      = "PENDING",      "En attente"
        PROCESSING   = "PROCESSING",   "En cours d'analyse"
        APPROVED     = "APPROVED",     "Approuvée"
        REJECTED     = "REJECTED",     "Rejetée"

    class Source(models.TextChoices):
        UPLOAD = "UPLOAD", "Fichier uploadé"
        CAMERA = "CAMERA", "Photo caméra"

    # ── Core relations ────────────────────────────────────────────────────────
    user            = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eco_proofs",
        verbose_name="utilisateur",
    )
    proof_type      = models.ForeignKey(
        ProofType,
        on_delete=models.PROTECT,
        related_name="eco_proofs",
        verbose_name="type de preuve",
    )

    # ── Cloudinary storage (proof files, authenticated, never public) ─────────
    # null after purge (hashes are kept for duplicate detection)
    cloudinary_public_id    = models.CharField(
        max_length=255, blank=True, default="",
        verbose_name="public_id Cloudinary (page 1)",
    )
    legacy_file_path        = models.CharField(
        max_length=500, blank=True, default="",
        verbose_name="ancien chemin du fichier",
    )
    legacy_source_url       = models.URLField(
        blank=True,
        default="",
        verbose_name="ancienne URL source",
    )
    extra_page_ids          = models.JSONField(
        default=list,
        verbose_name="public_ids pages 2-3 (PDF)",
    )
    cloudinary_version      = models.PositiveBigIntegerField(
        null=True, blank=True,
        verbose_name="version Cloudinary",
    )
    stored_bytes            = models.PositiveIntegerField(null=True, blank=True, verbose_name="taille (octets)")
    image_width             = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="largeur (px)")
    image_height            = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="hauteur (px)")
    file_purged_at          = models.DateTimeField(null=True, blank=True, verbose_name="fichier purgé le")

    # ── Submission metadata ───────────────────────────────────────────────────
    source          = models.CharField(
        max_length=8, choices=Source.choices, default=Source.UPLOAD,
        verbose_name="source",
    )
    status          = models.CharField(
        max_length=15, choices=Status.choices, default=Status.PENDING,
        verbose_name="statut",
    )

    # ── Anti-fraud fingerprints (kept even after purge) ───────────────────────
    file_sha256     = models.CharField(
        max_length=64, db_index=True, blank=True, default="",
        verbose_name="SHA-256 du fichier nettoyé",
    )
    phash           = models.CharField(
        max_length=16, db_index=True, blank=True, default="",
        verbose_name="hash perceptuel (dHash hex)",
    )
    # SHA-256(merchant+date+amount+type) — catches same document, different photo
    fingerprint     = models.CharField(
        max_length=64, db_index=True, blank=True, default="",
        verbose_name="empreinte de contenu",
    )

    # ── Extracted document fields (from OCR) ──────────────────────────────────
    document_date   = models.DateField(null=True, blank=True, verbose_name="date du document")
    amount          = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True,
        verbose_name="montant extrait",
    )
    merchant        = models.CharField(max_length=255, blank=True, default="", verbose_name="marchand")

    # ── Decision outcome ──────────────────────────────────────────────────────
    rejection_code      = models.CharField(
        max_length=30, blank=True, default="",
        verbose_name="code de rejet",
        help_text="DUPLICATE, TOO_OLD, BLURRY, WRONG_TYPE, CAP_REACHED, NO_DATE, LOW_CONFIDENCE, …",
    )
    rejection_reason_fr = models.TextField(
        blank=True, default="",
        verbose_name="motif de rejet (FR, montré à l'utilisateur)",
    )

    # ── Points outcome ────────────────────────────────────────────────────────
    points_awarded      = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="points accordés")
    points_transaction  = models.OneToOneField(
        "PointsTransaction",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="eco_proof",
        verbose_name="transaction de points",
    )

    # ── Admin review audit ────────────────────────────────────────────────────
    reviewed_by     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="reviewed_proofs",
        verbose_name="examiné par",
    )
    reviewed_at     = models.DateTimeField(null=True, blank=True, verbose_name="examiné le")
    review_note     = models.TextField(blank=True, default="", verbose_name="note de l'examinateur")

    # ── Timestamps ────────────────────────────────────────────────────────────
    submitted_at    = models.DateTimeField(default=timezone.now, verbose_name="soumis le")
    processed_at    = models.DateTimeField(null=True, blank=True, verbose_name="traité le")
    processing_attempts = models.PositiveSmallIntegerField(default=0, verbose_name="tentatives de traitement")
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["user", "status", "submitted_at"]),
            models.Index(fields=["user", "proof_type", "submitted_at"]),
        ]
        # Unique sha256 excluding REJECTED (allow resubmission after rejection)
        constraints = [
            models.UniqueConstraint(
                fields=["file_sha256"],
                condition=models.Q(file_sha256__gt="") & ~models.Q(status="REJECTED"),
                name="gamification_ecoproof_unique_sha256",
            ),
            models.UniqueConstraint(
                fields=["fingerprint"],
                condition=models.Q(fingerprint__gt="") & ~models.Q(status="REJECTED"),
                name="gamification_ecoproof_unique_fingerprint",
            ),
        ]
        verbose_name = "Preuve écologique"
        verbose_name_plural = "Preuves écologiques"

    def __str__(self) -> str:
        return f"{self.proof_type.label_fr if self.proof_type_id else '?'} — {self.user} ({self.get_status_display()})"

    def get_proof_type_display(self) -> str:
        """Compatibility label for templates built against the earlier proof model."""
        return self.proof_type.label_fr

    @property
    def proof_date(self):
        return self.document_date

    @property
    def rejection_reason(self):
        return self.rejection_reason_fr

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def is_purged(self) -> bool:
        return self.file_purged_at is not None

    @property
    def has_file(self) -> bool:
        return bool(self.cloudinary_public_id or self.legacy_file_path) and not self.is_purged

    # ── State transitions (keep business logic out of views) ──────────────────

    def mark_processing(self) -> None:
        self.status = self.Status.PROCESSING
        self.save(update_fields=["status", "updated_at"])

# ─────────────────────────────────────────────────────────────────────────────
# OcrAnalysis — full OCR pipeline result, 1:1 with EcoProof
# ─────────────────────────────────────────────────────────────────────────────

class OcrAnalysis(models.Model):

    eco_proof           = models.OneToOneField(
        EcoProof,
        on_delete=models.CASCADE,
        related_name="ocr_analysis",
        verbose_name="preuve liée",
    )

    # Raw OCR output
    raw_text            = models.TextField(blank=True, default="", verbose_name="texte brut")
    mean_confidence     = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        verbose_name="confiance OCR moyenne (0-1)",
    )

    # Composite score and breakdown
    score               = models.FloatField(default=0.0, verbose_name="score global (0-1)")
    score_breakdown     = models.JSONField(
        default=dict,
        verbose_name="détail du score",
        help_text="{'ocr_confidence': 0.x, 'keyword': 0.x, 'date': 0.x, …}",
    )
    matched_groups      = models.JSONField(default=list, verbose_name="groupes de mots-clés validés")

    # Quality measurements
    quality_metrics     = models.JSONField(
        default=dict,
        verbose_name="métriques de qualité",
        help_text="{'blur': float, 'brightness': float, 'width': int, 'height': int}",
    )

    # Pipeline metadata
    engine              = models.CharField(max_length=80, default="tesseract", verbose_name="moteur OCR")
    provider            = models.CharField(max_length=30, blank=True, default="", verbose_name="fournisseur OCR")
    provider_model      = models.CharField(max_length=100, blank=True, default="", verbose_name="modèle fournisseur")
    structured_result   = models.JSONField(default=dict, blank=True, verbose_name="résultat structuré validé")
    latency_ms          = models.PositiveIntegerField(null=True, blank=True, verbose_name="latence fournisseur (ms)")
    fallback_chain      = models.JSONField(default=list, blank=True, verbose_name="chaîne de repli")
    error_code          = models.CharField(max_length=50, blank=True, default="", verbose_name="code d'erreur IA")
    usage               = models.JSONField(default=dict, blank=True, verbose_name="consommation fournisseur")
    lang_used           = models.CharField(max_length=20, blank=True, default="", verbose_name="langue OCR")
    duration_ms         = models.PositiveIntegerField(null=True, blank=True, verbose_name="durée (ms)")
    flags               = models.JSONField(
        default=list,
        verbose_name="drapeaux anti-fraude",
        help_text="['EXIF_EDITOR', 'NEAR_DUPLICATE', 'OCR_FAILED', …]",
    )

    # Decision (mirrors EcoProof.status at decision time)
    decision            = models.CharField(max_length=15, blank=True, default="", verbose_name="décision OCR")

    processed_at        = models.DateTimeField(default=timezone.now, verbose_name="traité le")
    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Analyse OCR"
        verbose_name_plural = "Analyses OCR"

    def __str__(self) -> str:
        return f"OCR #{self.eco_proof_id} — score {self.score:.0%}"


class AiCallLog(models.Model):
    class Status(models.TextChoices):
        OK = "OK", "Succès"
        TIMEOUT = "TIMEOUT", "Délai dépassé"
        QUOTA = "QUOTA", "Quota dépassé"
        ERROR = "ERROR", "Erreur fournisseur"
        BAD_RESPONSE = "BAD_RESPONSE", "Réponse invalide"
        CACHED = "CACHED", "Résultat réutilisé"
        SKIPPED = "SKIPPED", "Appel ignoré"

    provider = models.CharField(max_length=30)
    proof = models.ForeignKey(
        EcoProof,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_call_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="proof_ai_call_logs",
    )
    status = models.CharField(max_length=20, choices=Status.choices)
    latency_ms = models.PositiveIntegerField(default=0)
    request_count = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["created_at", "provider"])]
        ordering = ["-created_at"]
        verbose_name = "Appel IA des preuves"
        verbose_name_plural = "Appels IA des preuves"

    def __str__(self):
        return f"{self.provider} · {self.status} · {self.created_at:%Y-%m-%d %H:%M}"


# ─────────────────────────────────────────────────────────────────────────────
# ImpactFactor — barème admin (single source of truth for points)
# ─────────────────────────────────────────────────────────────────────────────

class ImpactFactor(models.Model):

    class Unit(models.TextChoices):
        KG    = "kg",    "Kilogramme"
        COUNT = "count", "Unité"
        PROOF = "proof", "Preuve"

    action_type     = models.CharField(
        max_length=60, unique=True,
        verbose_name="type d'action",
        help_text="Identifiant unique (ex: PROOF_TRANSPORT_TICKET, ORGANIC_WASTE_KG).",
    )
    label           = models.CharField(max_length=150, verbose_name="libellé")
    unit            = models.CharField(max_length=10, choices=Unit.choices, verbose_name="unité")
    points_per_unit = models.PositiveIntegerField(verbose_name="points par unité")
    co2_kg_per_unit = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        verbose_name="kg CO₂ évité par unité",
        help_text="Laisser vide jusqu'à sourcer (ADEME/IPCC).",
    )
    is_active       = models.BooleanField(default=True, verbose_name="actif")
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["action_type"]
        verbose_name = "Facteur d'impact"
        verbose_name_plural = "Facteurs d'impact (barème)"

    def __str__(self) -> str:
        return f"{self.label} ({self.action_type}) — {self.points_per_unit} pts/{self.unit}"


# ─────────────────────────────────────────────────────────────────────────────
# PointsTransaction — immutable ledger (BR-01, BR-02)
# ─────────────────────────────────────────────────────────────────────────────

class PointsTransaction(models.Model):

    class Direction(models.TextChoices):
        CREDIT     = "CREDIT",     "Crédit"
        DEBIT      = "DEBIT",      "Débit"
        ADJUSTMENT = "ADJUSTMENT", "Ajustement"

    user            = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="points_transactions",
        verbose_name="utilisateur",
    )
    direction       = models.CharField(max_length=12, choices=Direction.choices, verbose_name="sens")
    action_type     = models.CharField(max_length=60, verbose_name="type d'action")
    quantity        = models.DecimalField(max_digits=10, decimal_places=2, default=1, verbose_name="quantité")
    points          = models.IntegerField(verbose_name="points (signé)")
    balance_after   = models.IntegerField(verbose_name="solde après")
    source_type     = models.CharField(max_length=60, blank=True, default="", verbose_name="type source")
    source_id       = models.PositiveIntegerField(null=True, blank=True, verbose_name="id source")
    reason          = models.CharField(max_length=255, blank=True, default="", verbose_name="raison")
    factor_snapshot = models.JSONField(null=True, blank=True, verbose_name="snapshot du facteur")
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source_type", "source_id", "reason"],
                condition=models.Q(source_type__gt=""),
                name="gamification_tx_unique_source",
            )
        ]
        verbose_name = "Transaction de points"
        verbose_name_plural = "Transactions de points"

    def __str__(self) -> str:
        sign = "+" if self.points >= 0 else ""
        return f"{self.user} {sign}{self.points} pts ({self.action_type}) → solde {self.balance_after}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("PointsTransaction est immuable — pas de modification possible.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("PointsTransaction ne peut pas être supprimée.")


# ─────────────────────────────────────────────────────────────────────────────
# Badge / UserBadge
# ─────────────────────────────────────────────────────────────────────────────

class Badge(models.Model):

    class Tier(models.TextChoices):
        BRONZE = "BRONZE", "Bronze"
        SILVER = "SILVER", "Argent"
        GOLD   = "GOLD",   "Or"

    class CriteriaType(models.TextChoices):
        TOTAL_POINTS    = "TOTAL_POINTS",    "Total de points"
        ACTION_COUNT    = "ACTION_COUNT",    "Nombre d'actions"
        ACTION_QUANTITY = "ACTION_QUANTITY", "Quantité d'actions"

    code                 = models.CharField(max_length=50, unique=True, verbose_name="code")
    name                 = models.CharField(max_length=120, verbose_name="nom")
    description          = models.TextField(blank=True, verbose_name="description")
    icon                 = models.CharField(max_length=50, default="award", verbose_name="icône SVG")
    tier                 = models.CharField(max_length=8, choices=Tier.choices, verbose_name="palier")
    criteria_type        = models.CharField(max_length=20, choices=CriteriaType.choices, verbose_name="type de critère")
    criteria_action_type = models.CharField(max_length=60, blank=True, verbose_name="action_type requis (optionnel)")
    threshold            = models.PositiveIntegerField(verbose_name="seuil")
    is_active            = models.BooleanField(default=True, verbose_name="actif")
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tier", "threshold"]
        verbose_name = "Badge"
        verbose_name_plural = "Badges"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_tier_display()})"


class UserBadge(models.Model):
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_badges",
        verbose_name="utilisateur",
    )
    badge      = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="user_badges")
    awarded_at = models.DateTimeField(default=timezone.now, verbose_name="obtenu le")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "badge"], name="gamification_userbadge_unique")
        ]
        ordering = ["-awarded_at"]
        verbose_name = "Badge utilisateur"
        verbose_name_plural = "Badges utilisateurs"

    def __str__(self) -> str:
        return f"{self.user} → {self.badge}"
