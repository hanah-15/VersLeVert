from django import forms
from django.utils import timezone

from .models import WasteRequest

HIDDEN_COORDS = {"latitude": forms.HiddenInput, "longitude": forms.HiddenInput}


class RequiresPositionMixin:
    def clean(self):
        data = super().clean()
        if data.get("latitude") in (None, "") or data.get("longitude") in (None, ""):
            self.add_error(None, "Choisissez la position sur la carte.")
        return data


class WasteRequestForm(RequiresPositionMixin, forms.ModelForm):
    class Meta:
        model = WasteRequest
        fields = ("waste_type", "estimated_weight", "address", "image", "latitude", "longitude")
        widgets = HIDDEN_COORDS
        labels = {
            "waste_type": "Type de déchet",
            "estimated_weight": "Poids estimé (kg)",
            "address": "Adresse de collecte",
        }
        error_messages = {"address": {"required": "Ce champ est obligatoire."}}

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and image.name.lower().split(".")[-1] not in {"jpg", "jpeg", "png"}:
            raise forms.ValidationError("Formats acceptés : JPG, JPEG ou PNG.")
        return image


class OfferForm(forms.Form):
    planned_date = forms.DateTimeField(
        label="Date et heure de passage proposées",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    latitude = forms.FloatField(required=False, widget=forms.HiddenInput)
    longitude = forms.FloatField(required=False, widget=forms.HiddenInput)
    message = forms.CharField(
        required=False,
        max_length=300,
        label="Message pour le déposant (facultatif)",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean(self):
        data = super().clean()
        planned_date = data.get("planned_date")
        if planned_date and planned_date <= timezone.now():
            self.add_error("planned_date", "La date doit être dans le futur.")
        if data.get("latitude") is None or data.get("longitude") is None:
            self.add_error(None, "Choisissez votre position sur la carte.")
        return data


class DeclineForm(forms.Form):
    note = forms.CharField(
        required=False,
        max_length=255,
        label="Motif (facultatif)",
    )


class MarketFilterForm(forms.Form):
    waste_type = forms.ChoiceField(
        required=False,
        choices=(("", "Tous"),) + tuple(WasteRequest._meta.get_field("waste_type").choices),
        label="Type de déchet",
    )
    latitude = forms.FloatField(required=False, widget=forms.HiddenInput)
    longitude = forms.FloatField(required=False, widget=forms.HiddenInput)