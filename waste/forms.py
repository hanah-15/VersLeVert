from django import forms
from .models import WasteRequest


class WasteRequestForm(forms.ModelForm):
    class Meta:
        model = WasteRequest
        fields = ("waste_type", "estimated_weight", "address")
        labels = {
            "waste_type": "Type de déchet",
            "estimated_weight": "Poids estimé (kg)",
            "address": "Adresse de collecte",
        }
        error_messages = {"address": {"required": "Ce champ est obligatoire."}}