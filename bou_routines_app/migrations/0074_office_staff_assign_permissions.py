from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0073_teacher_can_chair_examination'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='teacher',
            options={
                'permissions': [
                    ('can_mark_attendance', 'Can mark class attendance'),
                    ('can_manage_ca', 'Can manage continuous assessment'),
                    ('can_manage_final_marks', 'Can manage semester final marks'),
                    (
                        'can_chair_examination',
                        'Can act as examination chairman (e.g. enter lab viva marks)',
                    ),
                    ('can_assign_course_teacher', 'Can assign course teachers'),
                    ('can_assign_examiners', 'Can assign final exam examiners'),
                ],
            },
        ),
    ]
