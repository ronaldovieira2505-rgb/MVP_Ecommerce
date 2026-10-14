import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

RENAMES = [
    ("min_publish_lead_hours", "min_publish_lead_minutes"),
    ("payment_deadline_hours", "payment_deadline_minutes"),
    ("applications_close_hours_before", "applications_close_minutes_before"),
    ("auto_checkout_hours_after_end", "auto_checkout_minutes_after_end"),
    ("contest_window_hours", "contest_window_minutes"),
    ("free_cancel_hours_before", "free_cancel_minutes_before"),
]


def _convert(apps, factor_numerator, factor_denominator):
    PlatformParameters = apps.get_model("core", "PlatformParameters")
    for params in PlatformParameters.objects.all():
        # O estado já tem os campos renomeados (*_minutes) quando este passo roda.
        for _, name in RENAMES:
            value = getattr(params, name)
            setattr(params, name, value * factor_numerator // factor_denominator)
        params.save()


def hours_to_minutes(apps, schema_editor):
    _convert(apps, 60, 1)


def minutes_to_hours(apps, schema_editor):
    _convert(apps, 1, 60)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0002_default_platform_parameters"),
    ]

    operations = [
        *[
            migrations.RenameField("platformparameters", old, new)
            for old, new in RENAMES
        ],
        migrations.RunPython(hours_to_minutes, minutes_to_hours),
        migrations.AlterField(
            model_name="platformparameters",
            name="min_publish_lead_minutes",
            field=models.PositiveIntegerField(
                default=720, verbose_name="antecedência mínima de publicação (min)"
            ),
        ),
        migrations.AlterField(
            model_name="platformparameters",
            name="payment_deadline_minutes",
            field=models.PositiveIntegerField(
                default=1440, verbose_name="prazo para pagar a vaga (min)"
            ),
        ),
        migrations.AlterField(
            model_name="platformparameters",
            name="applications_close_minutes_before",
            field=models.PositiveIntegerField(
                default=120, verbose_name="encerramento de candidaturas (min antes do início)"
            ),
        ),
        migrations.AlterField(
            model_name="platformparameters",
            name="auto_checkout_minutes_after_end",
            field=models.PositiveIntegerField(
                default=120, verbose_name="check-out automático (min após o fim)"
            ),
        ),
        migrations.AlterField(
            model_name="platformparameters",
            name="contest_window_minutes",
            field=models.PositiveIntegerField(
                default=1440, verbose_name="janela de contestação (min)"
            ),
        ),
        migrations.AlterField(
            model_name="platformparameters",
            name="free_cancel_minutes_before",
            field=models.PositiveIntegerField(
                default=1440, verbose_name="cancelamento sem penalidade (min antes) [pós-MVP]"
            ),
        ),
        migrations.CreateModel(
            name="PlatformParametersChange",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("field", models.CharField(max_length=60, verbose_name="parâmetro")),
                ("old_value", models.CharField(max_length=40, verbose_name="valor anterior")),
                ("new_value", models.CharField(max_length=40, verbose_name="valor novo")),
                (
                    "changed_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="alterado em"
                    ),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="alterado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "alteração de parâmetro",
                "verbose_name_plural": "alterações de parâmetros",
                "ordering": ["-changed_at", "-id"],
            },
        ),
    ]
