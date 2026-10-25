from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from gamification.models import EcoProof
from gamification.tasks import dispatch_proof_processing


class Command(BaseCommand):
    help = "Retry proof analyses that have been pending or processing for at least five minutes."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=5)
        proofs = EcoProof.objects.filter(
            status__in=[EcoProof.Status.PENDING, EcoProof.Status.PROCESSING],
            updated_at__lt=cutoff,
        ).order_by("updated_at")[:max(1, options["limit"])]
        count = 0
        for proof in proofs:
            dispatch_proof_processing(proof.pk)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Dispatched {count} pending proof(s)."))
