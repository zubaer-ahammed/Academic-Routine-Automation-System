# Generated migration to populate SemesterCourse.teacher from Course.teacher

from django.db import migrations

def populate_semestercourse_teachers(apps, schema_editor):
    """Populate SemesterCourse.teacher from Course.teacher for existing records"""
    SemesterCourse = apps.get_model('bou_routines_app', 'SemesterCourse')
    Course = apps.get_model('bou_routines_app', 'Course')
    
    for semester_course in SemesterCourse.objects.all():
        if not semester_course.teacher and semester_course.course.teacher:
            semester_course.teacher = semester_course.course.teacher
            semester_course.save()

def reverse_populate_semestercourse_teachers(apps, schema_editor):
    """Reverse migration - clear teacher from SemesterCourse"""
    SemesterCourse = apps.get_model('bou_routines_app', 'SemesterCourse')
    SemesterCourse.objects.all().update(teacher=None)

class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0043_add_teacher_to_semestercourse'),
    ]

    operations = [
        migrations.RunPython(populate_semestercourse_teachers, reverse_populate_semestercourse_teachers),
    ]

