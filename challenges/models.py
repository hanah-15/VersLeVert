from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Challenge(models.Model):
    class Type(models.TextChoices):
        POINTS = "points", "Défi à points"
        PERSONAL = "personnel", "Défi personnel"

    class Status(models.TextChoices):
        ACTIVE = "active", "Actif"
        CLOSED = "closed", "Clôturé"

    title = models.CharField("Titre", max_length=150)
    description = models.TextField("Description", max_length=2000, blank=True)
    goal_value = models.DecimalField(
        "Objectif chiffré",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Exemple : 30 pour 30 km à vélo, 5 pour 5 kg de compost.",
    )
    unit = models.CharField(
        "Unité",
        max_length=50,
        help_text="Exemple : km, kg, trajets, repas.",
    )
    challenge_type = models.CharField(
        "Type de défi",
        max_length=20,
        choices=Type.choices,
        default=Type.POINTS,
    )
    points_reward = models.PositiveIntegerField(
        "Points attribués à la réussite",
        default=0,
        help_text="Pour les défis à points uniquement. 0 pour un défi personnel.",
    )
    is_community = models.BooleanField(
        "Défi communautaire",
        default=False,
        help_text="Permet à plusieurs participants de contribuer à un objectif collectif.",
    )
    start_date = models.DateField("Date de début", null=True, blank=True)
    end_date = models.DateField("Date de fin", null=True, blank=True)
    status = models.CharField(
        "Statut",
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_challenges",
        verbose_name="Créateur",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "défi"
        verbose_name_plural = "défis"
        indexes = [
            models.Index(fields=["status", "challenge_type"], name="chall_status_type_idx"),
        ]

    def clean(self):
        super().clean()
        if self.goal_value is not None and self.goal_value <= 0:
            raise ValidationError({"goal_value": "L'objectif chiffré doit être supérieur à zéro."})
        if not self.unit or not self.unit.strip():
            raise ValidationError({"unit": "L'unité est obligatoire (ex. km, kg)."})

        # Règles métier M6 :
        # - Défi personnel : aucun point attribué
        # - Défi à points : créé par un admin / staff (ou contient des points)
        if self.challenge_type == self.Type.PERSONAL:
            self.points_reward = 0
        elif self.challenge_type == self.Type.POINTS and self.points_reward < 0:
            raise ValidationError({"points_reward": "Les points d'un défi à points doivent être positifs."})

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La date de fin doit être postérieure à la date de début."})

    def save(self, *args, **kwargs):
        if self.challenge_type == self.Type.PERSONAL:
            self.points_reward = 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.get_challenge_type_display()})"

    def get_absolute_url(self):
        return reverse("challenges:detail", args=[self.pk])

    @property
    def is_active(self):
        if self.status != self.Status.ACTIVE:
            return False
        today = timezone.now().date()
        if self.end_date and self.end_date < today:
            return False
        return True

    def can_be_joined_by(self, user):
        """Vérifie si un utilisateur donné peut rejoindre ce défi."""
        if not user.is_authenticated:
            return False, "Vous devez être connecté pour participer."
        if not self.is_active:
            return False, "Ce défi est clôturé ou expiré et ne peut plus être rejoint."
        if ChallengeParticipation.objects.filter(challenge=self, user=user).exists():
            return False, "Vous participez déjà à ce défi."
        return True, ""


class ChallengeParticipation(models.Model):
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name="participations",
        verbose_name="Défi",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_participations",
        verbose_name="Participant",
    )
    joined_at = models.DateTimeField("Date d'inscription", auto_now_add=True)
    progress_value = models.DecimalField(
        "Progression actuelle",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    completed_at = models.DateTimeField("Date de réussite", null=True, blank=True)
    points_awarded = models.BooleanField("Points attribués", default=False)

    class Meta:
        ordering = ("-joined_at", "-pk")
        verbose_name = "participation à un défi"
        verbose_name_plural = "participations aux défis"
        constraints = [
            models.UniqueConstraint(
                fields=["challenge", "user"],
                name="unique_challenge_user_participation",
            )
        ]

    def __str__(self):
        return f"{self.user} · {self.challenge.title} ({self.progress_value}/{self.challenge.goal_value} {self.challenge.unit})"

    @property
    def is_completed(self):
        return self.completed_at is not None or self.progress_value >= self.challenge.goal_value

    @property
    def percentage(self):
        if not self.challenge.goal_value or self.challenge.goal_value <= 0:
            return 0
        ratio = (self.progress_value / self.challenge.goal_value) * Decimal("100")
        return min(100, int(ratio))

    def add_progress(self, value, note=""):
        """
        Enregistre un progrès, met à jour la progression totale
        et attribue les points une seule fois via M2 si l'objectif est atteint.
        """
        if value <= 0:
            raise ValidationError("La valeur ajoutée doit être strictement positive.")

        entry = ProgressEntry.objects.create(
            participation=self,
            value=value,
            note=note or "",
        )

        self.progress_value = (self.progress_value or Decimal("0.00")) + Decimal(str(value))
        just_completed = False

        if self.progress_value >= self.challenge.goal_value:
            if not self.completed_at:
                self.completed_at = timezone.now()
                just_completed = True

            # Attribution des points via M2 si défi à points
            if (
                self.challenge.challenge_type == Challenge.Type.POINTS
                and self.challenge.points_reward > 0
                and not self.points_awarded
            ):
                self._award_points()
                self.points_awarded = True

        self.save()
        self._notify_progress(just_completed)
        return entry, just_completed

    def _notify_progress(self, just_completed):
        from accounts.models import Notification

        if just_completed:
            message = f"Bravo ! Vous avez terminé le défi « {self.challenge.title} »."
        else:
            message = f"Progression enregistrée pour « {self.challenge.title} » : {self.percentage}%."
        Notification.objects.create(user=self.user, message=message)

        for milestone in self.challenge.milestones.order_by("threshold"):
            if self.percentage >= milestone.threshold:
                _, created = ChallengeMilestoneAchievement.objects.get_or_create(
                    user=self.user,
                    milestone=milestone,
                )
                if created:
                    Notification.objects.create(
                        user=self.user,
                        message=f"Jalon atteint dans « {self.challenge.title} » : {milestone.title}.",
                    )
                    if milestone.reward_points:
                        from gamification.services import award_points

                        award_points(
                            user=self.user,
                            source_type="challenge_milestone",
                            source_id=milestone.pk,
                            base_points=milestone.reward_points,
                            description=f"Jalon atteint : {milestone.title}",
                        )

    def _award_points(self):
        """Appelle award_points du module gamification (contrat M2)."""
        try:
            from gamification.services import award_points
            award_points(
                user=self.user,
                source_type="challenge",
                source_id=self.challenge.pk,
                base_points=self.challenge.points_reward,
                impact_factor=1.0,
                description=f"Défi relevé : {self.challenge.title}",
            )
        except Exception:
            # Sécurité si M2 a un dysfonctionnement : ne bloque pas la complétion du défi
            pass


class ProgressEntry(models.Model):
    participation = models.ForeignKey(
        ChallengeParticipation,
        on_delete=models.CASCADE,
        related_name="progress_entries",
        verbose_name="Participation",
    )
    value = models.DecimalField(
        "Valeur ajoutée",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    note = models.CharField("Note ou commentaire", max_length=255, blank=True)
    created_at = models.DateTimeField("Enregistré le", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "entrée de progression"
        verbose_name_plural = "entrées de progression"

    def __str__(self):
        return f"+{self.value} {self.participation.challenge.unit} ({self.created_at.strftime('%d/%m/%Y')})"


class ChallengeMilestone(models.Model):
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name="milestones",
        verbose_name="Défi",
    )
    title = models.CharField("Nom du jalon", max_length=120)
    threshold = models.PositiveSmallIntegerField(
        "Seuil de progression (%)",
        validators=[MinValueValidator(1)],
    )
    reward_points = models.PositiveIntegerField("Points bonus", default=0)

    class Meta:
        ordering = ("threshold", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("challenge", "threshold"),
                name="unique_challenge_milestone_threshold",
            )
        ]

    def __str__(self):
        return f"{self.challenge.title} · {self.threshold}%"


class ChallengeReminder(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Chaque jour"
        WEEKLY = "weekly", "Chaque semaine"
        OFF = "off", "Désactivé"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_reminders",
    )
    challenge = models.ForeignKey(
        Challenge,
        on_delete=models.CASCADE,
        related_name="reminders",
    )
    frequency = models.CharField(
        "Fréquence",
        max_length=10,
        choices=Frequency.choices,
        default=Frequency.WEEKLY,
    )
    last_sent_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "challenge"),
                name="unique_challenge_reminder",
            )
        ]


class ChallengeMilestoneAchievement(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    milestone = models.ForeignKey(ChallengeMilestone, on_delete=models.CASCADE)
    achieved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "milestone"),
                name="unique_user_milestone_achievement",
            )
        ]
