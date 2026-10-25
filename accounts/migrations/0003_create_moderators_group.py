from django.db import migrations


def create_moderators_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    SponsorAccount = apps.get_model("accounts", "SponsorAccount")
    group, _ = Group.objects.get_or_create(name="Moderators")
    permissions = Permission.objects.filter(
        content_type__app_label="accounts",
        content_type__model=SponsorAccount._meta.model_name,
        codename__in={"view_sponsoraccount", "change_sponsoraccount"},
    )
    group.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_sponsoraccount"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_moderators_group, migrations.RunPython.noop),
    ]
