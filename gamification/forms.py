"""
Gamification forms — M1-A
"""

from django import forms

from .models import Badge, ImpactFactor


# ---------------------------------------------------------------------------
# EcoProof upload form (PT-01)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ImpactFactor admin form (PT-09)
# ---------------------------------------------------------------------------

class ImpactFactorForm(forms.ModelForm):
    class Meta:
        model  = ImpactFactor
        fields = [
            "action_type", "label", "unit",
            "points_per_unit", "co2_kg_per_unit", "is_active",
        ]
        labels = {
            "action_type":     "Type d'action (code unique)",
            "label":           "Libellé",
            "unit":            "Unité",
            "points_per_unit": "Points par unité",
            "co2_kg_per_unit": "CO₂ évité par unité (kg)",
            "is_active":       "Actif",
        }
        help_texts = {
            "action_type": (
                "Identifiant technique utilisé par les autres modules "
                "(ex: WASTE_ORGANIC, TRANSPORT_TICKET)."
            ),
        }


# ---------------------------------------------------------------------------
# Badge admin form (PT-11)
# ---------------------------------------------------------------------------

class BadgeForm(forms.ModelForm):
    class Meta:
        model  = Badge
        fields = [
            "code", "name", "description", "icon", "tier",
            "criteria_type", "criteria_action_type", "threshold", "is_active",
        ]
        labels = {
            "code":                 "Code (unique)",
            "name":                 "Nom",
            "description":          "Description",
            "icon":                 "Icône (emoji)",
            "tier":                 "Palier",
            "criteria_type":        "Type de critère",
            "criteria_action_type": "Action requise (optionnel)",
            "threshold":            "Seuil",
            "is_active":            "Actif",
        }


# ---------------------------------------------------------------------------
# Points adjustment form — admin use only (PT-14)
# ---------------------------------------------------------------------------

class PointsAdjustmentForm(forms.Form):
    delta  = forms.IntegerField(
        label="Ajustement (positif ou négatif)",
        help_text="Entrez un nombre positif pour créditer, négatif pour débiter.",
    )
    reason = forms.CharField(
        label="Motif",
        max_length=255,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


# ---------------------------------------------------------------------------
# EcoProof review form — admin use (PT-06)
# ---------------------------------------------------------------------------

class ProofReviewForm(forms.Form):
    ACTION_CHOICES = [
        ("approve",      "Approuver"),
        ("needs_review", "Mettre en révision"),
        ("reject",       "Rejeter"),
    ]
    action           = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect,
        label="Décision",
    )
    rejection_reason = forms.CharField(
        label="Motif de rejet",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Obligatoire si vous rejetez la preuve.",
    )

    def clean(self):
        data   = super().clean()
        action = data.get("action")
        reason = data.get("rejection_reason", "").strip()
        if action == "reject" and not reason:
            raise ValidationError({"rejection_reason": "Le motif est obligatoire en cas de rejet."})
        return data
