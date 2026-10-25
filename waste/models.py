from decimal import ROUND_HALF_UP, Decimal

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
MAX_WEIGHT_RATIO = Decimal("3")   # poids confirmé <= 3 x poids estimé


def compute_points(waste_type, weight):
    base, factor = POINTS_RULES[waste_type]
    return int((Decimal(weight) * base * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


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

    # photo du déchet
    image = models.ImageField(upload_to="waste/images/", blank=True, null=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    collector_latitude = models.FloatField(null=True, blank=True)
    collector_longitude = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    planned_date = models.DateTimeField(null=True, blank=True)
    refusal_reason = models.CharField(max_length=255, blank=True)
    co2_avoided = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    points_awarded = models.PositiveIntegerField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
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

    def accept_offer(self, offer, by_user):
        with transaction.atomic():
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            locked_offer = CollectionOffer.objects.select_for_update().get(pk=offer.pk)
            if locked.user_id != by_user.pk:
                raise ValueError("Seul le déposant peut accepter cette proposition.")
            if locked_offer.waste_request_id != locked.pk or locked_offer.status != CollectionOffer.Status.PENDING:
                raise ValueError("Cette proposition n'est plus en attente.")
            if locked.status != Status.REQUESTED or locked.collector_id is not None:
                raise ValueError("Cette demande n'est plus ouverte.")
            locked.change_status(Status.PLANNED, by_user)
            locked.collector = locked_offer.collector
            locked.collector_latitude = locked_offer.latitude
            locked.collector_longitude = locked_offer.longitude
            locked.planned_date = locked_offer.proposed_date
            locked.save(update_fields=[
                "collector", "collector_latitude", "collector_longitude", "planned_date"
            ])
            locked_offer.status = CollectionOffer.Status.ACCEPTED
            locked_offer.decided_at = timezone.now()
            locked_offer.save(update_fields=["status", "decided_at"])
            CollectionOffer.objects.filter(
                waste_request=locked, status=CollectionOffer.Status.PENDING
            ).exclude(pk=locked_offer.pk).update(
                status=CollectionOffer.Status.DECLINED,
                decision_note="Une autre proposition a été acceptée.",
                decided_at=timezone.now(),
            )
        self.refresh_from_db()

    def decline_offer(self, offer, by_user, note=""):
        with transaction.atomic():
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            locked_offer = CollectionOffer.objects.select_for_update().get(pk=offer.pk)
            if locked.user_id != by_user.pk:
                raise ValueError("Seul le déposant peut refuser cette proposition.")
            if locked_offer.waste_request_id != locked.pk or locked_offer.status != CollectionOffer.Status.PENDING:
                raise ValueError("Cette proposition n'est plus en attente.")
            if locked.status != Status.REQUESTED:
                raise ValueError("Cette demande n'est plus ouverte.")
            locked_offer.status = CollectionOffer.Status.DECLINED
            locked_offer.decision_note = note
            locked_offer.decided_at = timezone.now()
            locked_offer.save(update_fields=["status", "decision_note", "decided_at"])

    def cancel_request(self, by_user):
        with transaction.atomic():
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            if locked.user_id != by_user.pk:
                raise ValueError("Seul le déposant peut annuler cette demande.")
            if locked.status != Status.REQUESTED:
                raise ValueError("Cette demande ne peut plus être annulée.")
            locked.change_status(Status.CANCELLED, by_user)
            CollectionOffer.objects.filter(
                waste_request=locked, status=CollectionOffer.Status.PENDING
            ).update(
                status=CollectionOffer.Status.DECLINED,
                decision_note="La demande a été annulée.",
                decided_at=timezone.now(),
            )

    def confirm(self, weight, by_user):
        """Le collecteur confirme le poids réel : planned -> collected -> confirmed.
        Calcule le CO2 et les points, une seule fois. Retourne la demande à jour."""
        try:
            weight = Decimal(str(weight))
        except Exception:
            raise ValueError("Poids invalide.")

        with transaction.atomic():
            # verrou : deux confirmations simultanées ne peuvent pas passer toutes les deux
            req = WasteRequest.objects.select_for_update().get(pk=self.pk)

            if req.status != Status.PLANNED:
                raise ValueError("Cette collecte n'est pas planifiée ou a déjà été confirmée.")
            if req.collector_id != by_user.pk:
                raise ValueError("Seul le collecteur de cette demande peut confirmer le poids.")
            if weight <= 0:
                raise ValueError("Le poids doit être supérieur à zéro.")
            if weight > req.estimated_weight * MAX_WEIGHT_RATIO:
                raise ValueError(
                    f"Le poids confirmé ne peut pas dépasser {MAX_WEIGHT_RATIO} fois "
                    f"le poids estimé ({req.estimated_weight} kg)."
                )
            try:
                factor = EmissionFactor.objects.get(waste_type=req.waste_type)
            except EmissionFactor.DoesNotExist:
                raise ValueError("Facteur d'émission manquant : contactez un administrateur.")

            req.confirmed_weight = weight
            req.co2_avoided = (weight * factor.kg_co2_per_kg).quantize(Decimal("0.001"))
            req.points_awarded = compute_points(req.waste_type, weight)
            req.confirmed_at = timezone.now()

            # deux changements de statut journalisés dans WasteStatusLog
            req.change_status(Status.COLLECTED, by_user)
            req.change_status(Status.CONFIRMED, by_user)
            req._award_points()

        self.refresh_from_db()
        return self

    def _award_points(self):
        """Envoie les points au module gamification s'il est disponible."""
        try:
            from gamification.services import award_points
        except ImportError:
            return   # M2 pas encore livré : les points restent stockés sur la demande
        base, factor = POINTS_RULES[self.waste_type]
        award_points(
            self.user, "waste", self.pk,
            base_points=self.confirmed_weight * base,
            impact_factor=factor,
            description=f"Collecte confirmée : {self.confirmed_weight} kg",
            action_type=f"WASTE_{self.waste_type.upper()}",
            quantity=self.confirmed_weight,
        )


class EcoAdvice(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eco_advices",
    )
    payload = models.JSONField()
    stats_hash = models.CharField(max_length=64)
    source = models.CharField(max_length=8, choices=(("ai", "IA"), ("fallback", "Repli")))
    grounded = models.BooleanField()
    duration_ms = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"])]
        ordering = ["-created_at"]


class CollectionOffer(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ACCEPTED = "accepted", "Acceptée"
        DECLINED = "declined", "Refusée"
        WITHDRAWN = "withdrawn", "Retirée"

    waste_request = models.ForeignKey(
        WasteRequest, on_delete=models.CASCADE, related_name="offers"
    )
    collector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE, related_name="collection_offers"
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    proposed_date = models.DateTimeField()
    message = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decision_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["waste_request", "collector"],
                name="unique_offer_per_collector_per_request",
            )
        ]

    def __str__(self):
        return f"{self.collector.username} · {self.waste_request}"

    def withdraw(self, by_user):
        with transaction.atomic():
            offer = type(self).objects.select_for_update().get(pk=self.pk)
            if offer.collector_id != by_user.pk:
                raise ValueError("Vous ne pouvez pas retirer cette proposition.")
            if offer.status != self.Status.PENDING:
                raise ValueError("Seule une proposition en attente peut être retirée.")
            offer.status = self.Status.WITHDRAWN
            offer.decided_at = timezone.now()
            offer.save(update_fields=["status", "decided_at"])

    def release(self, by_user):
        with transaction.atomic():
            current = type(self).objects.get(pk=self.pk)
            request = WasteRequest.objects.select_for_update().get(pk=current.waste_request_id)
            offer = type(self).objects.select_for_update().get(pk=self.pk)
            if offer.collector_id != by_user.pk:
                raise ValueError("Vous ne pouvez pas vous désister de cette proposition.")
            if offer.status != self.Status.ACCEPTED or request.status != Status.PLANNED:
                raise ValueError("Cette proposition acceptée ne peut plus être libérée.")
            request.change_status(Status.REQUESTED, by_user)
            request.collector = None
            request.collector_latitude = None
            request.collector_longitude = None
            request.planned_date = None
            request.save(update_fields=[
                "collector", "collector_latitude", "collector_longitude", "planned_date"
            ])
            offer.status = self.Status.WITHDRAWN
            offer.decided_at = timezone.now()
            offer.save(update_fields=["status", "decided_at"])


class WasteStatusLog(models.Model):
    request = models.ForeignKey(WasteRequest, on_delete=models.CASCADE, related_name="logs")
    old_status = models.CharField(max_length=10)
    new_status = models.CharField(max_length=10)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at"]