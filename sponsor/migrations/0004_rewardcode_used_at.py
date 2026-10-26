from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('sponsor', '0003_offer_image')]

    operations = [
        migrations.AddField(
            model_name='rewardcode', name='used_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
