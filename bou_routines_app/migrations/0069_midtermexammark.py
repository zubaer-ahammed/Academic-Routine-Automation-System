# Generated manually for MidtermExamMark

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bou_routines_app", "0068_alter_camark_lab_practical_mark_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="MidtermExamMark",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("q1", models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=5, null=True)),
                ("q2", models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=5, null=True)),
                ("q3", models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=5, null=True)),
                ("q4", models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=5, null=True)),
                ("q5", models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=5, null=True)),
                ("q6", models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=5, null=True)),
                ("marked_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "course",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="bou_routines_app.course"),
                ),
                (
                    "marked_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="midterm_exam_marks_marked_by",
                        to="bou_routines_app.teacher",
                    ),
                ),
                (
                    "semester",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="bou_routines_app.semester"),
                ),
                (
                    "student",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="bou_routines_app.student"),
                ),
            ],
            options={
                "ordering": ["student__id"],
                "unique_together": {("student", "course", "semester")},
            },
        ),
    ]
