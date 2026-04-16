# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0061_final_exam_mark_exam_absent'),
    ]

    operations = [
        migrations.AddField(
            model_name='semestercourse',
            name='final_exam_evaluator1',
            field=models.ForeignKey(
                blank=True,
                help_text='First examiner (e.g. DRC) for final exam marking',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='semester_courses_as_final_exam_evaluator1',
                to='bou_routines_app.teacher',
            ),
        ),
        migrations.AddField(
            model_name='semestercourse',
            name='final_exam_evaluator2',
            field=models.ForeignKey(
                blank=True,
                help_text='Second examiner (e.g. DUET) for final exam marking',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='semester_courses_as_final_exam_evaluator2',
                to='bou_routines_app.teacher',
            ),
        ),
        migrations.AddField(
            model_name='semestercourse',
            name='final_exam_evaluator3',
            field=models.ForeignKey(
                blank=True,
                help_text='Third examiner if required (large T1/T2 discrepancy)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='semester_courses_as_final_exam_evaluator3',
                to='bou_routines_app.teacher',
            ),
        ),
    ]
