from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class Event(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        PUBLISHED = "published", "Publié"
        CLOSED = "closed", "Clôturé"
        CANCELLED = "cancelled", "Annulé"
        REFUSED = "refused", "Refusé"

    title = models.CharField(max_length=200, verbose_name="Titre de l'événement")
    objective = models.TextField(verbose_name="Objectif")
    location = models.CharField(max_length=255, verbose_name="Lieu")
    date = models.DateTimeField(verbose_name="Date et heure de l'événement")
    capacity = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="Capacité maximale (optionnelle)"
    )
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organized_events",
        verbose_name="Organisateur",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Statut",
    )

    # Résultats publiés à la clôture (E-06)
    collected_quantity = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Quantité collectée",
        help_text="Ex : 45 kg de déchets, 120 arbres plantés...",
    )
    actual_participants_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Nombre de participants réels",
    )
    result_summary = models.TextField(
        blank=True,
        verbose_name="Compte-rendu du résultat",
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de clôture",
    )
    points_reward = models.PositiveIntegerField(
        default=50,
        verbose_name="Points par participant confirmé",
    )

    # Innovations IA pour l'action écologique
    co2_avoided = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="CO₂ évité estimé (kg)",
    )
    ai_impact_analysis = models.TextField(
        blank=True,
        verbose_name="Analyse d'impact IA (synthèse & équivalences)",
    )
    ai_checklist = models.TextField(
        blank=True,
        verbose_name="Checklist et consignes éco-responsables IA",
    )
    ai_moderation_notes = models.TextField(
        blank=True,
        verbose_name="Analyse IA de modération (Admin)",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    class Meta:
        ordering = ["date"]
        verbose_name = "Événement écologique"
        verbose_name_plural = "Événements écologiques"

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    @property
    def is_upcoming(self):
        return self.date > timezone.now()

    @property
    def is_past(self):
        return self.date <= timezone.now()

    @property
    def registrations_count(self):
        return self.registrations.count()

    @property
    def confirmed_attendees_count(self):
        return self.registrations.filter(present=True).count()

    @property
    def is_full(self):
        if self.capacity is None:
            return False
        return self.registrations.count() >= self.capacity

    @property
    def available_spots(self):
        if self.capacity is None:
            return None
        return max(0, self.capacity - self.registrations.count())

    @property
    def checklist_items(self):
        """Retourne la liste des éléments de la checklist éco-responsable."""
        if not self.ai_checklist:
            return []
        try:
            import json
            data = json.loads(self.ai_checklist)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return [item.strip("- *• \t") for item in self.ai_checklist.splitlines() if item.strip()]

    @property
    def impact_analysis_dict(self):
        """Retourne l'analyse d'impact IA sous forme de dictionnaire."""
        if not self.ai_impact_analysis:
            return None
        try:
            import json
            data = json.loads(self.ai_impact_analysis)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {"analysis_summary": self.ai_impact_analysis}

    @property
    def moderation_dict(self):
        """Retourne l'analyse IA de modération pour les administrateurs."""
        if not self.ai_moderation_notes:
            return None
        try:
            import json
            data = json.loads(self.ai_moderation_notes)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {"commentary": self.ai_moderation_notes}

    def generate_impact_report_ai(self):
        """Calcule l'analyse d'impact écologique par IA et enregistre le résultat."""
        from .ai import analyze_environmental_impact_ai
        import json
        data = analyze_environmental_impact_ai(self)
        self.ai_impact_analysis = json.dumps(data, ensure_ascii=False)
        self.co2_avoided = data.get("estimated_co2_kg")
        self.save(update_fields=["ai_impact_analysis", "co2_avoided"])
        return data

    def generate_moderation_ai(self):
        """Génère une note d'analyse pour assister l'administrateur lors de la modération."""
        from .ai import moderate_event_ai
        import json
        data = moderate_event_ai(self.title, self.objective, self.location)
        self.ai_moderation_notes = json.dumps(data, ensure_ascii=False)
        self.save(update_fields=["ai_moderation_notes"])
        return data

    def can_register(self, user):
        """Vérifie si un utilisateur peut s'inscrire."""
        if not user or not user.is_authenticated:
            return False
        if self.status != self.Status.PUBLISHED:
            return False
        if not self.is_upcoming:
            return False
        if self.is_full:
            return False
        if self.registrations.filter(user=user).exists():
            return False
        return True

    def can_unregister(self, user):
        """Vérifie si un utilisateur peut se désinscrire."""
        if not user or not user.is_authenticated:
            return False
        if not self.is_upcoming:
            return False
        return self.registrations.filter(user=user).exists()

    def register(self, user):
        """Inscrit l'utilisateur si les conditions sont remplies (CA E-03)."""
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=self.pk)
            if event.status != self.Status.PUBLISHED:
                raise ValidationError("L'inscription n'est possible que sur un événement publié.")
            if not event.is_upcoming:
                raise ValidationError("Impossible de s'inscrire à un événement passé.")
            if event.is_full:
                raise ValidationError("Cet événement a atteint sa capacité maximale.")
            if event.registrations.filter(user=user).exists():
                raise ValidationError("Vous êtes déjà inscrit à cet événement.")

            registration = EventRegistration.objects.create(event=event, user=user)
            return registration

    def unregister(self, user):
        """Désinscrit l'utilisateur (CA E-03)."""
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=self.pk)
            if not event.is_upcoming:
                raise ValidationError("Impossible de se désinscrire d'un événement passé.")
            reg = event.registrations.filter(user=user).first()
            if not reg:
                raise ValidationError("Vous n'êtes pas inscrit à cet événement.")
            reg.delete()

    def confirm_attendance(self, present_user_ids, by_user):
        """Confirme la présence des inscrits après la date (CA E-04)."""
        if not self.is_past:
            raise ValidationError("La confirmation de présence n'est possible qu'après la date de l'événement.")
        if by_user != self.organizer and not (by_user.is_staff or by_user.is_superuser or getattr(by_user, "is_admin_user", False)):
            raise ValidationError("Seul l'organisateur ou un administrateur peut confirmer les présences.")

        with transaction.atomic():
            registrations = self.registrations.select_for_update().all()
            user_id_set = {int(uid) for uid in present_user_ids if uid}
            for reg in registrations:
                is_present = reg.user_id in user_id_set
                if reg.present != is_present:
                    reg.present = is_present
                    reg.save(update_fields=["present"])

    def close_and_award_points(self, collected_quantity=None, participants_count=None, result_summary=None, by_user=None):
        """Clôture l'événement, publie le résultat et attribue les points (CA E-05, E-06)."""
        if not self.is_past:
            raise ValidationError("Un événement ne peut être clôturé qu'après sa date de tenue.")
        if by_user and by_user != self.organizer and not (by_user.is_staff or by_user.is_superuser or getattr(by_user, "is_admin_user", False)):
            raise ValidationError("Seul l'organisateur ou un administrateur peut clôturer cet événement.")

        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=self.pk)
            event.status = self.Status.CLOSED
            event.closed_at = timezone.now()

            if collected_quantity is not None:
                event.collected_quantity = collected_quantity
            if result_summary is not None:
                event.result_summary = result_summary

            present_regs = event.registrations.filter(present=True)
            if participants_count is not None:
                event.actual_participants_count = participants_count
            elif event.actual_participants_count is None:
                event.actual_participants_count = present_regs.count()

            event.save()

            # E-05 : Points attribués une seule fois, à la clôture, via M2
            for reg in present_regs:
                if not reg.points_awarded:
                    reg.award_points(amount=event.points_reward)

        self.refresh_from_db()
        try:
            self.generate_impact_report_ai()
        except Exception:
            pass
        return self


class EventRegistration(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="registrations",
        verbose_name="Événement",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_registrations",
        verbose_name="Participant",
    )
    registered_at = models.DateTimeField(auto_now_add=True, verbose_name="Date d'inscription")
    present = models.BooleanField(default=False, verbose_name="Présence confirmée")
    points_awarded = models.BooleanField(default=False, verbose_name="Points attribués")
    points_amount = models.PositiveIntegerField(default=0, verbose_name="Points obtenus")

    class Meta:
        ordering = ["registered_at"]
        verbose_name = "Inscription à un événement"
        verbose_name_plural = "Inscriptions aux événements"
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                name="unique_registration_per_user_per_event",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.event.title} ({'Présent' if self.present else 'Inscrit'})"

    def award_points(self, amount=None):
        """Attribue les points une seule fois via M2 si présent."""
        if self.points_awarded:
            return False
        if not self.present:
            return False

        pts = amount if amount is not None else self.event.points_reward
        self.points_awarded = True
        self.points_amount = pts
        self.save(update_fields=["points_awarded", "points_amount"])

        # Appel au module gamification (M2) s'il existe
        try:
            from gamification.services import award_points
            award_points(
                user=self.user,
                source="event",
                source_id=self.event_id,
                base_points=pts,
                description=f"Participation à l'événement : {self.event.title}",
            )
        except (ImportError, Exception):
            pass

        return True


# Alias compatibles
EcoEvent = Event
EventParticipant = EventRegistration
