from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from gamification.models import EcoProof
from gamification.services.pipeline import _stored_file
from gamification.services.storage import delete_legacy_file, get_storage


class Command(BaseCommand):
    help = "Delete private files for old rejected proofs while retaining their hashes."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=settings.PROOF_REJECTED_RETENTION_DAYS)
        proofs = EcoProof.objects.filter(
            status=EcoProof.Status.REJECTED,
            file_purged_at__isnull=True,
            processed_at__lt=cutoff,
        )
        storage = get_storage()
        purged = 0
        for proof in proofs.iterator():
            public_ids = [proof.cloudinary_public_id, *proof.extra_page_ids]
            for public_id in filter(None, public_ids):
                try:
                    storage.delete(_stored_file(
                        proof,
                        public_id,
                        proof.cloudinary_version if public_id == proof.cloudinary_public_id else None,
                    ))
                except Exception as exc:
                    self.stderr.write(
                        self.style.ERROR(f"Could not purge proof {proof.pk} ({type(exc).__name__}); retaining database record.")
                    )
                    break
            else:
                try:
                    delete_legacy_file(proof.legacy_file_path)
                except Exception as exc:
                    self.stderr.write(
                        self.style.ERROR(f"Could not purge legacy file for proof {proof.pk} ({type(exc).__name__}); retaining database record.")
                    )
                    continue
                proof.file_purged_at = timezone.now()
                proof.cloudinary_public_id = ""
                proof.extra_page_ids = []
                proof.legacy_file_path = ""
                proof.save(update_fields=[
                    "file_purged_at", "cloudinary_public_id", "extra_page_ids",
                    "legacy_file_path", "updated_at",
                ])
                purged += 1
        self.stdout.write(self.style.SUCCESS(f"Purged files for {purged} rejected proof(s)."))
