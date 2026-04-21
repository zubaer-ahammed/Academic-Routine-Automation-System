from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bou_routines_app", "0062_semestercourse_final_exam_evaluators"),
    ]

    operations = [
        migrations.AddField(
            model_name="semestercourse",
            name="attendance_midterm_override_dates",
            field=models.TextField(
                blank=True,
                null=True,
                help_text="Attendance-only mid-term exam dates override (comma-separated YYYY-MM-DD). Used only to adjust Attendance table date columns.",
            ),
        ),
    ]

