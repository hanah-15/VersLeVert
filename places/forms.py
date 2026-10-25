from django import forms

from .models import Place, ProductRecommendation


INPUT_CLASS = "w-full min-h-[46px] rounded-xl border-2 border-palm bg-white px-3 py-2 text-carbon focus:border-forest focus:outline-none focus:ring-4 focus:ring-sky"


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = INPUT_CLASS
            if field.help_text:
                field.widget.attrs["aria-describedby"] = f"id_{name}_help"
            if self.is_bound and name in self.errors:
                field.widget.attrs["aria-invalid"] = "true"
                field.widget.attrs["aria-describedby"] = f"id_{name}_errors"


class PlaceForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Place
        fields = ("name", "category", "description", "address", "latitude", "longitude")
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}
        help_texts = {
            "latitude": "Entre -90 et 90. Exemple : 36.806500.",
            "longitude": "Entre -180 et 180. Exemple : 10.181500.",
        }


class PlaceFilterForm(StyledFormMixin, forms.Form):
    q = forms.CharField(label="Rechercher un lieu", required=False, max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Nom, adresse, mot-clé…", "type": "search"}))
    category = forms.ChoiceField(label="Catégorie", required=False, choices=[("", "Toutes les catégories"), *Place.Category.choices])
    latitude = forms.DecimalField(label="Votre latitude", required=False, min_value=-90, max_value=90, max_digits=9, decimal_places=6)
    longitude = forms.DecimalField(label="Votre longitude", required=False, min_value=-180, max_value=180, max_digits=9, decimal_places=6)
    radius = forms.DecimalField(label="Rayon maximum (km)", required=False, min_value=0.1, max_value=500, max_digits=5, decimal_places=1)

    def clean(self):
        data = super().clean()
        lat, lon = data.get("latitude"), data.get("longitude")
        if (lat is None) != (lon is None):
            self.add_error(None, "Renseignez la latitude et la longitude ensemble.")
        if data.get("radius") is not None and (lat is None or lon is None):
            self.add_error("radius", "Indiquez votre position pour filtrer par distance.")
        return data


class RecommendationForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProductRecommendation
        fields = ("product_name", "category", "description", "place")
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}
        help_texts = {"description": "Expliquez son intérêt écologique et votre expérience. Évitez les affirmations non vérifiées."}


class RecommendationFilterForm(StyledFormMixin, forms.Form):
    q = forms.CharField(label="Rechercher un produit", required=False, max_length=100,
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Produit ou mot-clé…"}))
    category = forms.ChoiceField(label="Catégorie", required=False,
        choices=[("", "Toutes les catégories"), *ProductRecommendation.Category.choices])
    sort = forms.ChoiceField(label="Trier par", required=False,
        choices=[("recent", "Les plus récentes"), ("popular", "Les plus aimées")])


class ModerationForm(StyledFormMixin, forms.Form):
    decision = forms.ChoiceField(label="Décision", choices=[("approved", "Publier"), ("rejected", "Refuser")])
    rejection_reason = forms.CharField(label="Motif du refus", required=False, max_length=1000,
        widget=forms.Textarea(attrs={"rows": 3}))

    def clean(self):
        data = super().clean()
        if data.get("decision") == "rejected" and not data.get("rejection_reason"):
            self.add_error("rejection_reason", "Indiquez un motif de refus.")
        return data


class GuideForm(StyledFormMixin, forms.Form):
    query = forms.CharField(label="Que recherchez-vous ?", max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Je cherche une boutique pour réduire les emballages et un produit réutilisable."}))
