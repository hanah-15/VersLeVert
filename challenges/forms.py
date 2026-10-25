from decimal import Decimal
from django import forms
from .models import Challenge, ProgressEntry


class PersonalChallengeForm(forms.ModelForm):
    """
    Formulaire pour créer un défi personnel (C-03).
    Objectif chiffré et unité obligatoires, aucun point attribué.
    """
    class Meta:
        model = Challenge
        fields = ("title", "description", "goal_value", "unit", "start_date", "end_date")
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "ui-input",
                "placeholder": "Ex. Aller au travail à vélo pendant un mois",
            }),
            "description": forms.Textarea(attrs={
                "class": "ui-textarea",
                "rows": 3,
                "placeholder": "Décrivez votre objectif personnel...",
            }),
            "goal_value": forms.NumberInput(attrs={
                "class": "ui-input",
                "step": "0.1",
                "min": "0.1",
                "placeholder": "Ex. 30",
            }),
            "unit": forms.TextInput(attrs={
                "class": "ui-input",
                "placeholder": "Ex. km, kg, repas, trajets",
            }),
            "start_date": forms.DateInput(attrs={
                "class": "ui-input",
                "type": "date",
            }),
            "end_date": forms.DateInput(attrs={
                "class": "ui-input",
                "type": "date",
            }),
        }

    def clean_goal_value(self):
        val = self.cleaned_data.get("goal_value")
        if val is None or val <= Decimal("0"):
            raise forms.ValidationError("L'objectif chiffré doit être supérieur à zéro.")
        return val

    def clean_unit(self):
        unit = self.cleaned_data.get("unit", "").strip()
        if not unit:
            raise forms.ValidationError("L'unité est obligatoire (ex. km, kg).")
        return unit


class AdminChallengeForm(forms.ModelForm):
    """
    Formulaire pour l'administrateur créant un défi à points (C-06).
    """
    class Meta:
        model = Challenge
        fields = (
            "title",
            "description",
            "goal_value",
            "unit",
            "points_reward",
            "is_community",
            "start_date",
            "end_date",
            "status",
        )
        widgets = {
            "title": forms.TextInput(attrs={"class": "ui-input"}),
            "description": forms.Textarea(attrs={"class": "ui-textarea", "rows": 3}),
            "goal_value": forms.NumberInput(attrs={"class": "ui-input", "step": "0.1", "min": "0.1"}),
            "unit": forms.TextInput(attrs={"class": "ui-input", "placeholder": "km, kg..."}),
            "points_reward": forms.NumberInput(attrs={"class": "ui-input", "min": "0"}),
            "is_community": forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-olive text-forest"}),
            "start_date": forms.DateInput(attrs={"class": "ui-input", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "ui-input", "type": "date"}),
            "status": forms.Select(attrs={"class": "ui-select"}),
        }


class ProgressEntryForm(forms.ModelForm):
    """
    Formulaire pour enregistrer un avancement (C-04).
    """
    class Meta:
        model = ProgressEntry
        fields = ("value", "note")
        widgets = {
            "value": forms.NumberInput(attrs={
                "class": "ui-input",
                "step": "0.1",
                "min": "0.01",
                "placeholder": "Ex. 5",
            }),
            "note": forms.TextInput(attrs={
                "class": "ui-input",
                "placeholder": "Ex. Trajet domicile-travail aller/retour",
            }),
        }

    def clean_value(self):
        val = self.cleaned_data.get("value")
        if val is None or val <= Decimal("0"):
            raise forms.ValidationError("La valeur ajoutée doit être strictement positive.")
        return val


class ChallengeFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "class": "ui-input",
        "placeholder": "Rechercher par titre ou mot-clé...",
    }))
    challenge_type = forms.ChoiceField(
        required=False,
        choices=[("", "Tous les types"), ("points", "Défis à points"), ("personnel", "Défis personnels")],
        widget=forms.Select(attrs={"class": "ui-select"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "Tous les statuts"), ("active", "Actifs"), ("closed", "Clôturés")],
        widget=forms.Select(attrs={"class": "ui-select"}),
    )
