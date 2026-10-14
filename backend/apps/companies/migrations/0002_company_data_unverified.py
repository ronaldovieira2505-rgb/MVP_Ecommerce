from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="data_unverified",
            field=models.BooleanField(
                default=False,
                help_text="A consulta de CNPJ falhou no cadastro: o admin deve conferir os dados.",
                verbose_name="dados não conferidos",
            ),
        ),
    ]
