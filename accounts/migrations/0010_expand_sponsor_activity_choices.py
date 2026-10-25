from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_sponsor_activity_choices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sponsoraccount",
            name="activity",
            field=models.CharField(
                choices=[
                    ("food_local", "Alimentation et commerces locaux"),
                    ("clothing", "Vêtements et mode"),
                    ("food_and_beverages", "Alimentation et boissons"),
                    ("technology", "Technologie et numérique"),
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
        migrations.RemoveConstraint(
            model_name="sponsoraccount",
            name="accounts_sponsor_activity_valid",
        ),
        migrations.AddConstraint(
            model_name="sponsoraccount",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    activity__in=[
                        "food_local",
                        "clothing",
                        "food_and_beverages",
                        "technology",
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
