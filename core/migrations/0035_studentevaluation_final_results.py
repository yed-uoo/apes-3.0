from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0034_studentevaluation_ese_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentevaluation",
            name="final_total",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="studentevaluation",
            name="percentage",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="studentevaluation",
            name="grade",
            field=models.CharField(blank=True, max_length=2, null=True),
        ),
        migrations.AddField(
            model_name="studentevaluation",
            name="result_calculated",
            field=models.BooleanField(default=False),
        ),
    ]
