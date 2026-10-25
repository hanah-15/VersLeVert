from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Notification
from challenges.models import ChallengeParticipation, ChallengeReminder


class Command(BaseCommand):
    help = "Envoie les rappels des défis actifs dont la fréquence est arrivée à échéance."

    def handle(self, *args, **options):
        now = timezone.now()
        sent = 0
        reminders = ChallengeReminder.objects.filter(
            enabled=True,
            challenge__status="active",
        ).select_related("challenge", "user")
        for reminder in reminders:
            participation = ChallengeParticipation.objects.filter(
                user=reminder.user,
                challenge=reminder.challenge,
                completed_at__isnull=True,
            ).first()
            if not participation:
                continue
            interval = timedelta(days=1 if reminder.frequency == "daily" else 7)
            if reminder.last_sent_at and now - reminder.last_sent_at < interval:
                continue
            Notification.objects.create(
                user=reminder.user,
                message=(
                    f"Rappel : ajoutez votre progression au défi "
                    f"« {reminder.challenge.title} » ({participation.percentage}%)."
                ),
            )
            reminder.last_sent_at = now
            reminder.save(update_fields=["last_sent_at"])
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"{sent} rappel(s) envoyé(s)."))
