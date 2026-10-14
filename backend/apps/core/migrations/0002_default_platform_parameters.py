from django.db import migrations


def create_default_parameters(apps, schema_editor):
    PlatformParameters = apps.get_model("core", "PlatformParameters")
    # Os padrões vêm dos defaults dos campos (docs/regras-de-negocio.md).
    PlatformParameters.objects.get_or_create(pk=1)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_parameters, migrations.RunPython.noop),
    ]
