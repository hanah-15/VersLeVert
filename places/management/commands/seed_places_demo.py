import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from places.management.commands.evaluate_guide import DATA_PATH
from places.models import Place, ProductRecommendation


class Command(BaseCommand):
    help = "Add clearly labelled fictional guide demo entries; never overwrite existing records."

    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))["catalogue"]
        user, created = get_user_model().objects.get_or_create(
            username="places-demo-author", defaults={"email": "places-demo-author@example.test"},
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        places = {}
        added = 0
        for row in data["places"]:
            defaults = {k: value for k, value in row.items() if k not in {"id", "name"}}
            place, created = Place.objects.get_or_create(name=row["name"], defaults=defaults)
            places[row["id"]] = place
            added += int(created)
        for row in data["products"]:
            _, created = ProductRecommendation.objects.get_or_create(
                user=user, product_name=row["product_name"],
                defaults={"description": row["description"], "category": row["category"],
                          "place": places[row["place_id"]], "status": ProductRecommendation.Status.APPROVED},
            )
            added += int(created)
        self.stdout.write(f"Added {added} fictional demo records. Existing records were preserved.")
