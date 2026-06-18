from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0072_clear_legacy_zero_teacher_marks'),
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
                ],
            },
        ),
    ]
