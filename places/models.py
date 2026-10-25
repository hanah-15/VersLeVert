from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse


class Place(models.Model):
    class Category(models.TextChoices):
        PARK = "park", "Parc"
        CAFE = "cafe", "Café responsable"
        ZERO_WASTE_SHOP = "zero_waste_shop", "Magasin zéro déchet"
        RECYCLING_POINT = "recycling_point", "Point de recyclage"

    name = models.CharField("Nom", max_length=150)
    category = models.CharField("Catégorie", max_length=30, choices=Category.choices)
    description = models.TextField("Description", max_length=3000, blank=True)
    address = models.CharField("Adresse", max_length=255)
    latitude = models.DecimalField("Latitude", max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField("Longitude", max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)])
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_places", verbose_name="Créé par")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "pk")
        verbose_name = "lieu"
        verbose_name_plural = "lieux"
        indexes = [models.Index(fields=["category", "name"], name="places_category_name_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(latitude__gte=-90, latitude__lte=90), name="place_valid_latitude"),
            models.CheckConstraint(condition=models.Q(longitude__gte=-180, longitude__lte=180), name="place_valid_longitude"),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("places:detail", args=[self.pk])


class ProductRecommendation(models.Model):
    class Category(models.TextChoices):
        FOOD = "food", "Alimentation"
        PERSONAL_CARE = "personal_care", "Hygiène et beauté"
        HOME = "home", "Maison"
        FASHION = "fashion", "Mode et textile"
        MOBILITY = "mobility", "Mobilité"
        OTHER = "other", "Autre"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        APPROVED = "approved", "Publiée"
        REJECTED = "rejected", "Refusée"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="product_recommendations", verbose_name="Auteur")
    place = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="recommendations", verbose_name="Lieu associé")
    product_name = models.CharField("Nom du produit", max_length=150)
    description = models.TextField("Pourquoi le recommandez-vous ?", max_length=3000)
    category = models.CharField("Catégorie", max_length=30, choices=Category.choices)
    status = models.CharField("Statut", max_length=12, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField("Motif du refus", max_length=1000, blank=True)
    moderated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="moderated_recommendations", verbose_name="Modéré par")
    moderated_at = models.DateTimeField("Date de modération", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "recommandation de produit"
        verbose_name_plural = "recommandations de produits"
        indexes = [models.Index(fields=["status", "-created_at"], name="places_rec_status_date_idx")]
        constraints = [models.CheckConstraint(
            condition=~models.Q(status="rejected") | ~models.Q(rejection_reason=""),
            name="recommendation_rejection_has_reason",
        )]

    def clean(self):
        super().clean()
        self.rejection_reason = self.rejection_reason.strip()
        if self.status == self.Status.REJECTED and not self.rejection_reason:
            raise ValidationError({"rejection_reason": "Indiquez un motif de refus."})

    def __str__(self):
        return self.product_name

    def get_absolute_url(self):
        return reverse("places:recommendation-detail", args=[self.pk])


class RecommendationLike(models.Model):
    recommendation = models.ForeignKey(ProductRecommendation, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recommendation_likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["recommendation", "user"], name="one_like_per_user_recommendation")]
        verbose_name = "mention J’aime"
        verbose_name_plural = "mentions J’aime"
