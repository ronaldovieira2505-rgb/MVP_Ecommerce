from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_deadlines_in_minutes_and_parameter_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformparameters",
            name="cnpj_lookup_timeout_seconds",
            field=models.PositiveIntegerField(default=5, verbose_name="limite da consulta de CNPJ (s)"),
        ),
    ]
