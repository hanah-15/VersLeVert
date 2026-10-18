from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone


class WasteType(models.TextChoices):
    ORGANIC = "organic", "Organique"
    PLASTIC = "plastic", "Plastique"


class Status(models.TextChoices):
    REQUESTED = "requested", "Demandée"
    PLANNED = "planned", "Planifiée"
    COLLECTED = "collected", "Collectée"
    CONFIRMED = "confirmed", "Confirmée"
    REFUSED = "refused", "Refusée"
    CANCELLED = "cancelled", "Annulée"


# statuts autorisés à partir de chaque statut
ALLOWED_TRANSITIONS = {
    Status.REQUESTED: {Status.PLANNED, Status.REFUSED, Status.CANCELLED},
    Status.PLANNED: {Status.REQUESTED, Status.COLLECTED, Status.REFUSED},
    Status.COLLECTED: {Status.CONFIRMED},
    Status.CONFIRMED: set(),
    Status.REFUSED: set(),
    Status.CANCELLED: set(),
}

# (points par kg, facteur d'impact), à valider en équipe
POINTS_RULES = {
    WasteType.ORGANIC: (10, Decimal("1.0")),
    WasteType.PLASTIC: (10, Decimal("1.5")),
}


class EmissionFactor(models.Model):
    waste_type = models.CharField(max_length=10, choices=WasteType.choices, unique=True)
    kg_co2_per_kg = models.DecimalField(max_digits=6, decimal_places=3)
    source = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.get_waste_type_display()} : {self.kg_co2_per_kg} kg CO₂/kg"


class WasteRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="waste_requests")
    collector = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name="collections")
    waste_type = models.CharField(max_length=10, choices=WasteType.choices)
    estimated_weight = models.DecimalField(max_digits=7, decimal_places=2,
                                           validators=[MinValueValidator(Decimal("0.01"))])
    confirmed_weight = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    address = models.CharField(max_length=255)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    collector_latitude = models.FloatField(null=True, blank=True)
    collector_longitude = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    planned_date = models.DateTimeField(null=True, blank=True)
    refusal_reason = models.CharField(max_length=255, blank=True)
    co2_avoided = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(estimated_weight__gt=0),
                                   name="waste_estimated_weight_positive"),
        ]

    def __str__(self):
        return f"{self.get_waste_type_display()} {self.estimated_weight} kg ({self.get_status_display()})"

    def can_go_to(self, new_status):
        return new_status in ALLOWED_TRANSITIONS[self.status]

    def change_status(self, new_status, by_user):
        if not self.can_go_to(new_status):
            raise ValueError(f"Passage impossible : {self.status} → {new_status}")
        WasteStatusLog.objects.create(request=self, old_status=self.status,
                                      new_status=new_status, changed_by=by_user)
        self.status = new_status
        self.save()

    def claim(self, collector_user, lat, lon, planned_date):
        if lat is None or lon is None:
            raise ValueError("Choisissez votre position sur la carte.")
        if planned_date <= timezone.now():
            raise ValueError("La date doit être dans le futur.")

        with transaction.atomic():
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            if locked.status != Status.REQUESTED or locked.collector_id is not None:
                raise ValueError("Cette demande n'est plus disponible.")
            if locked.user_id == collector_user.pk:
                raise ValueError("Vous ne pouvez pas collecter votre propre demande.")
            locked.change_status(Status.PLANNED, collector_user)
            locked.collector = collector_user
            locked.collector_latitude = lat
            locked.collector_longitude = lon
            locked.planned_date = planned_date
            locked.save(update_fields=[
                "collector", "collector_latitude", "collector_longitude", "planned_date"
            ])

        self.refresh_from_db()

    def release(self, by_user):
        with transaction.atomic():
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            if locked.status != Status.PLANNED or locked.collector_id != by_user.pk:
                raise ValueError("Vous ne pouvez pas vous désister de cette demande.")
            locked.change_status(Status.REQUESTED, by_user)
            locked.collector = None
            locked.collector_latitude = None
            locked.collector_longitude = None
            locked.planned_date = None
            locked.save(update_fields=[
                "collector", "collector_latitude", "collector_longitude", "planned_date"
            ])

        self.refresh_from_db()


class WasteStatusLog(models.Model):
    request = models.ForeignKey(WasteRequest, on_delete=models.CASCADE, related_name="logs")
    old_status = models.CharField(max_length=10)
    new_status = models.CharField(max_length=10)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at"]