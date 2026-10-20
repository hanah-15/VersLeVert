from django import forms

from accounts.models import SponsorAccount
from .models import Offer


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ("title", "description", "points_cost", "active")


class SponsorProfileForm(forms.ModelForm):
    class Meta:
        model = SponsorAccount
        fields = ("business_name", "activity", "description", "logo", "contact_email", "phone")
