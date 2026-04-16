# Generated manually for exam_absent on FinalExamMark

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0060_fix_student_session_old_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='finalexammark',
            name='exam_absent',
            field=models.BooleanField(default=False),
        ),
    ]
