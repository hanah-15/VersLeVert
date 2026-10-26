from django import forms
from django.core.validators import URLValidator
import json

from accounts.models import SponsorAccount
from .models import Offer


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ("title", "description", "points_cost", "image", "image_url", "images_url", "active")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "images_url": forms.Textarea(attrs={"rows": 3, "placeholder": "Un lien de photo par ligne"}),
            'image': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }
        labels = {'title': "Titre de l'offre", 'description': 'Description', 'points_cost': 'Coût en points',
            'image': 'Photo de l’offre', 'image_url': 'Lien vers une photo', 'images_url': 'Autres photos', 'active': 'Proposer cette offre aux membres'}
        help_texts = {'points_cost': 'Points nécessaires pour obtenir un code. 0 pour une récompense offerte.',
            'image': 'Ajoutez une photo pour présenter la récompense.',
            'image_url': 'Vous pouvez utiliser un lien de photo à la place du fichier.',
            'images_url': 'Facultatif : un lien de photo par ligne.',
            'active': 'Une offre inactive reste dans votre espace et peut être réactivée.'}

    def clean_image_url(self):
        value = self.cleaned_data.get('image_url')
        if value:
            URLValidator(schemes=['http', 'https'])(value)
        return value

    def clean_images_url(self):
        value = (self.cleaned_data.get('images_url') or '').strip()
        if not value:
            return ''
        if value.startswith('['):
            try:
                urls = json.loads(value)
            except ValueError:
                raise forms.ValidationError('Indiquez un lien de photo valide par ligne.')
            if not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
                raise forms.ValidationError('Indiquez un lien de photo valide par ligne.')
        else:
            urls = value.splitlines()
        urls = [url.strip() for url in urls if url.strip()]
        for url in urls:
            URLValidator(schemes=['http', 'https'])(url)
        return json.dumps(list(dict.fromkeys(urls)), ensure_ascii=False)


class SponsorProfileForm(forms.ModelForm):
    class Meta:
        model = SponsorAccount
        fields = ("business_name", "activity", "description", "logo", "contact_email", "phone")
        labels = {'business_name': "Nom de l'entreprise", 'activity': 'Activité', 'description': 'Présentation',
            'logo': 'Logo', 'contact_email': 'E-mail de contact', 'phone': 'Téléphone'}
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'logo': forms.ClearableFileInput(attrs={'accept': 'image/*'})}


class CodeValidationForm(forms.Form):
    code_value = forms.CharField(label='Code présenté par le membre', max_length=64,
        widget=forms.TextInput(attrs={'placeholder': 'Saisir le code de récompense', 'autocomplete': 'off'}))

    def clean_code_value(self):
        return self.cleaned_data['code_value'].strip().upper()
