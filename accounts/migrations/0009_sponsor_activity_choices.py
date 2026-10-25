import unicodedata

from django.db import migrations, models


ACTIVITY_ALIASES = {
    "alimentation et commerces locaux": "food_local",
    "alimentation": "food_local",
    "commerce": "food_local",
    "commerce local": "food_local",
    "reparation et reemploi": "repair_reuse",
    "recyclage": "repair_reuse",
    "reemploi": "repair_reuse",
    "mobilite durable": "sustainable_mobility",
    "energie et environnement": "energy_environment",
    "environnement": "energy_environment",
    "agriculture et espaces verts": "agriculture_green_spaces",
    "agriculture": "agriculture_green_spaces",
    "associations et economie sociale": "social_economy",
    "association": "social_economy",
    "autre": "other",
}
VALID_ACTIVITIES = {
    "food_local",
    "repair_reuse",
    "sustainable_mobility",
    "energy_environment",
    "agriculture_green_spaces",
    "social_economy",
    "other",
}


def normalize_activity(value):
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().strip().lower()


def convert_existing_activities(apps, schema_editor):
    SponsorAccount = apps.get_model("accounts", "SponsorAccount")
    for sponsor in SponsorAccount.objects.all().only("pk", "activity").iterator():
        activity = normalize_activity(sponsor.activity)
        if activity not in VALID_ACTIVITIES:
            activity = ACTIVITY_ALIASES.get(activity, "other")
        if sponsor.activity != activity:
            SponsorAccount.objects.filter(pk=sponsor.pk).update(activity=activity)


class Migration(migrations.Migration):
    # atomic=False: RunPython + AddConstraint in the same migration causes
    # a PostgreSQL "pending trigger events" error when run inside a transaction.
    atomic = False

    dependencies = [
        ("accounts", "0008_merge_0005_delete_collectorprofile_0007_user_city"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sponsoraccount",
            name="activity",
            field=models.CharField(
                choices=[
                    ("food_local", "Alimentation et commerces locaux"),
                    ("repair_reuse", "Réparation et réemploi"),
                    ("sustainable_mobility", "Mobilité durable"),
                    ("energy_environment", "Énergie et environnement"),
                    ("agriculture_green_spaces", "Agriculture et espaces verts"),
                    ("social_economy", "Associations et économie sociale"),
                    ("other", "Autre"),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(convert_existing_activities, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="sponsoraccount",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    activity__in=[
                        "food_local",
                        "repair_reuse",
                        "sustainable_mobility",
                        "energy_environment",
                        "agriculture_green_spaces",
                        "social_economy",
                        "other",
                    ]
                ),
                name="accounts_sponsor_activity_valid",
            ),
        ),
    ]
