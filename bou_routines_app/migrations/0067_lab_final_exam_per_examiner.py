# Generated manually for lab dual-examiner final marks

from django.db import migrations, models


def copy_lab_marks_to_teacher1(apps, schema_editor):
    FinalExamMark = apps.get_model("bou_routines_app", "FinalExamMark")
    qs = FinalExamMark.objects.filter(course__is_lab=True)
    for fm in qs.iterator():
        FinalExamMark.objects.filter(pk=fm.pk).update(
            teacher1_lab_final_exam_mark=fm.lab_final_exam_mark,
            teacher1_lab_viva_mark=fm.lab_viva_mark,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("bou_routines_app", "0066_new_lab_ca_single_experiment_15"),
    ]

    operations = [
        migrations.AddField(
            model_name="finalexammark",
            name="teacher1_lab_final_exam_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                help_text="Internal examiner — problem solving / old curriculum final",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="finalexammark",
            name="teacher1_lab_viva_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                help_text="Internal examiner — viva (new curriculum)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="finalexammark",
            name="teacher2_lab_final_exam_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                help_text="External examiner — problem solving / old curriculum final",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="finalexammark",
            name="teacher2_lab_viva_mark",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                help_text="External examiner — viva (new curriculum)",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.RunPython(copy_lab_marks_to_teacher1, migrations.RunPython.noop),
    ]
