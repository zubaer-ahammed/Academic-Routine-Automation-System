from django.db import migrations, models
import django.db.models.deletion


def grant_chairman_assign_to_office_staff(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ct = ContentType.objects.get(app_label='bou_routines_app', model='teacher')
    assign_teacher = Permission.objects.get(codename='can_assign_course_teacher', content_type=ct)
    assign_exam = Permission.objects.get(codename='can_assign_examiners', content_type=ct)
    assign_chairman = Permission.objects.get(codename='can_assign_chairman', content_type=ct)
    for user in User.objects.filter(user_permissions=assign_exam).distinct():
        if user.user_permissions.filter(id=assign_teacher.id).exists():
            user.user_permissions.add(assign_chairman)


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0074_office_staff_assign_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='semestercourse',
            name='lab_examination_chairman',
            field=models.ForeignKey(
                blank=True,
                help_text='Examination chairman for lab course viva (per semester/course/centre)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='semester_courses_as_lab_examination_chairman',
                to='bou_routines_app.teacher',
            ),
        ),
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
                    ('can_assign_chairman', 'Can assign lab examination chairman'),
                ],
            },
        ),
        migrations.RunPython(grant_chairman_assign_to_office_staff, migrations.RunPython.noop),
    ]
