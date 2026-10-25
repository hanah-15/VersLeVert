from django import forms

from accounts.models import SponsorAccount
from .models import Offer


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ("title", "description", "points_cost", "image", "image_url", "images_url", "active")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "images_url": forms.Textarea(attrs={"rows": 3, "placeholder": "https://...\nhttps://... or [\"https://...\"]"}),
        }


class SponsorProfileForm(forms.ModelForm):
    class Meta:
        model = SponsorAccount
        fields = ("business_name", "activity", "description", "logo", "contact_email", "phone")
