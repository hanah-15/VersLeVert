from django import forms

from .models import Place, ProductRecommendation


INPUT_CLASS = "w-full min-h-[46px] rounded-xl border-2 border-palm bg-white px-3 py-2 text-carbon focus:border-forest focus:outline-none focus:ring-4 focus:ring-sky"


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = INPUT_CLASS
            if field.help_text:
                field.widget.attrs["aria-describedby"] = f"{self[name].auto_id}_helptext"
            if self.is_bound and name in self.errors:
                field.widget.attrs["aria-invalid"] = "true"
                field.widget.attrs["aria-describedby"] = f"{self[name].auto_id}_error"

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "content_type"):
            if image.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Choisissez une photo de moins de 5 Mo.")
            if getattr(image, "image", None) and image.image.format not in {"JPEG", "PNG", "WEBP"}:
                raise forms.ValidationError("Choisissez une photo JPG, PNG ou WebP.")
        return image

    def save(self, *args, **kwargs):
        if "image" in self.changed_data:
            self.instance.image_credit = ""
            self.instance.image_source = ""
        return super().save(*args, **kwargs)


class PlaceForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Place
        fields = ("name", "category", "description", "image", "address", "latitude", "longitude")
        widgets = {"description": forms.Textarea(attrs={"rows": 4}), "latitude": forms.HiddenInput, "longitude": forms.HiddenInput,
                   "image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"})}
        help_texts = {"image": "Une photo du lieu. JPG, PNG ou WebP, 5 Mo maximum."}


class PlaceFilterForm(StyledFormMixin, forms.Form):
    q = forms.CharField(label="Rechercher un lieu", required=False, max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Nom, adresse, mot-clé…", "type": "search"}))
    category = forms.ChoiceField(label="Catégorie", required=False, choices=[("", "Toutes les catégories"), *Place.Category.choices])
    city = forms.CharField(label="Ville ou quartier", required=False, max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Ex. Tunis, La Marsa…"}))
    near_place = forms.ModelChoiceField(label="Autour de ce lieu", required=False,
        queryset=Place.objects.all(), empty_label="Choisir un lieu du catalogue")
    latitude = forms.DecimalField(required=False, min_value=-90, max_value=90, max_digits=9, decimal_places=6, widget=forms.HiddenInput)
    longitude = forms.DecimalField(required=False, min_value=-180, max_value=180, max_digits=9, decimal_places=6, widget=forms.HiddenInput)
    location_token = forms.CharField(required=False, max_length=1000, widget=forms.HiddenInput)
    radius = forms.DecimalField(label="Distance", required=False, min_value=0.1, max_value=500, max_digits=5, decimal_places=1,
        widget=forms.Select(choices=[("", "Toutes les distances"), (1, "À moins de 1 km"), (5, "À moins de 5 km"), (10, "À moins de 10 km"), (25, "À moins de 25 km"), (50, "À moins de 50 km")]))

    def clean(self):
        data = super().clean()
        if data.get("near_place"):
            data["latitude"] = data["near_place"].latitude
            data["longitude"] = data["near_place"].longitude
        lat, lon = data.get("latitude"), data.get("longitude")
        if (lat is None) != (lon is None):
            self.add_error(None, "Choisissez un lieu de départ ou utilisez « Autour de moi ».")
        if data.get("radius") is not None and (lat is None or lon is None):
            self.add_error("radius", "Choisissez un lieu de départ ou utilisez « Autour de moi » pour rechercher à proximité.")
        return data

    @property
    def location_label(self):
        if not self.is_bound or not self.is_valid():
            return ""
        if self.cleaned_data.get("near_place"):
            return self.cleaned_data["near_place"].name
        if self.cleaned_data.get("latitude") is not None:
            from .geolocation import read_location_label
            return read_location_label(self.cleaned_data) or "Ma position"
        return ""


class RecommendationForm(StyledFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.place_id and not self.instance.purchase_location:
            self.initial["purchase_location"] = self.instance.place.name

    def clean(self):
        data = super().clean()
        location = data.get("purchase_location", "").strip()
        if location:
            matches = list(Place.objects.filter(name__iexact=location)[:2])
            data["place"] = matches[0] if len(matches) == 1 else None
        elif data.get("place") and "purchase_location" not in self.data:
            location = data["place"].name
        else:
            data["place"] = None
        data["purchase_location"] = location
        return data

    class Meta:
        model = ProductRecommendation
        fields = ("product_name", "category", "description", "image", "purchase_location", "place")
        widgets = {"description": forms.Textarea(attrs={"rows": 4, "placeholder": "Ce que vous avez aimé, comment vous l'utilisez, ce qui vous semble intéressant…"}),
                   "image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
                   "place": forms.HiddenInput,
                   "purchase_location": forms.TextInput(attrs={"placeholder": "Ex. Monoprix, Nouvelle Médina, ou une boutique en ligne"})}
        labels = {"description": "Votre avis", "purchase_location": "Où le trouver ? (facultatif)"}
        help_texts = {"description": "Quelques phrases suffisent.", "image": "Ajoutez une photo pour reconnaître le produit. JPG, PNG ou WebP, 5 Mo maximum.",
                      "purchase_location": "Écrivez le magasin, l'adresse ou le site. L'IA peut reprendre un lieu mentionné dans votre avis."}


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


class GuideForm(PlaceFilterForm):
    # Reuse the catalogue's validated coordinate-pair and radius rules.
    q = None
    category = forms.ChoiceField(required=False, choices=[("", "Toutes les catégories"), *Place.Category.choices], widget=forms.HiddenInput)
    activity = forms.ChoiceField(label="Votre envie", required=False, choices=[
        ("walk", "Se promener"), ("coffee", "Boire un café"), ("bulk", "Acheter en vrac"),
        ("recycle", "Recycler"), ("products", "Trouver un produit"),
    ], widget=forms.RadioSelect)
    query = forms.CharField(label="Une envie plus précise ?", required=False, max_length=500,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Ex. Un parc pour un pique-nique et une boutique en vrac à proximité."}))

    def clean(self):
        data = super().clean()
        requests = {"walk": "Un parc ou un jardin pour une promenade", "coffee": "Un café responsable pour boire un café sur place", "bulk": "Une boutique en vrac pour réduire les emballages", "recycle": "Un point de recyclage pour déposer des emballages", "products": "Des produits réutilisables recommandés par la communauté"}
        if not data.get("query"):
            data["query"] = requests.get(data.get("activity"), "")
        if not data["query"]:
            self.add_error("activity", "Choisissez une envie ou précisez votre recherche.")
        return data


class RecommendationPreparationForm(forms.Form):
    product_name = forms.CharField(required=False, max_length=150)
    description = forms.CharField(min_length=20, max_length=3000)


class LocationLookupForm(forms.Form):
    latitude = forms.DecimalField(min_value=-90, max_value=90, max_digits=9, decimal_places=6)
    longitude = forms.DecimalField(min_value=-180, max_value=180, max_digits=9, decimal_places=6)
