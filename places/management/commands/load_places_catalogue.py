"""Install the photographed starter catalogue without touching unrelated records."""
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from places.models import Place, ProductRecommendation

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_PATH = ROOT / "catalogue.json"
PHOTO_DIR = ROOT / "static" / "places" / "catalogue"


class Command(BaseCommand):
    help = "Load named places and photographed products; replace only the known legacy placeholders."

    @transaction.atomic
    def handle(self, *args, **options):
        catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
        user, created = get_user_model().objects.get_or_create(
            username="places-catalogue", defaults={"email": "catalogue@verslevert.example.test", "first_name": "Sélection Vers le Vert"},
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        count = 0
        for kind, model in (("places", Place), ("products", ProductRecommendation)):
            name_field = "name" if kind == "places" else "product_name"
            for source in catalogue[kind]:
                row = source.copy()
                legacy_name = row.pop("replaces", None)
                filename = row.pop("image")
                image_name = "places/catalogue/" + filename
                if not default_storage.exists(image_name):
                    with (PHOTO_DIR / filename).open("rb") as photo:
                        default_storage.save(image_name, photo)
                row["image"] = image_name
                legacy = model.objects.filter(**{name_field: legacy_name}).first() if legacy_name else None
                if legacy is not None and kind == "places" and legacy.address != "Adresse fictive de démonstration":
                    legacy = None
                # A normal catalogue import never overwrites an existing real entry.
                if legacy is not None:
                    for key, value in row.items():
                        setattr(legacy, key, value)
                    if kind == "products":
                        legacy.user = user
                        legacy.place = None
                        legacy.status = ProductRecommendation.Status.APPROVED
                        legacy.rejection_reason = ""
                        legacy.moderated_at = timezone.now()
                    legacy.save()
                    count += 1
                else:
                    defaults = {key: value for key, value in row.items() if key != name_field}
                    if kind == "products":
                        defaults.update(user=user, place=None, status=ProductRecommendation.Status.APPROVED, moderated_at=timezone.now())
                    _, created = model.objects.get_or_create(**{name_field: row[name_field]}, defaults=defaults)
                    count += int(created)
        self.stdout.write(self.style.SUCCESS(f"Catalogue ready: {count} entries added or replaced. Photos included."))
