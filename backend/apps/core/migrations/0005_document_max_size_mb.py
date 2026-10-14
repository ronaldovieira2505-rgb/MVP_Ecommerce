from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_cnpj_lookup_timeout"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformparameters",
            name="document_max_size_mb",
            field=models.PositiveIntegerField(
                default=5, verbose_name="tamanho máximo de cada documento/selfie (MB)"
            ),
        ),
    ]
