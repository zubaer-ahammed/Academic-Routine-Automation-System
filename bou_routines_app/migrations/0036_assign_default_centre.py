# Generated manually

from django.db import migrations


def assign_default_centre(apps, schema_editor):
    """
    Assign DRC Centre as default centre to all existing teachers and semesters
    that don't have a centre assigned.
    """
    Centre = apps.get_model('bou_routines_app', 'Centre')
    Teacher = apps.get_model('bou_routines_app', 'Teacher')
    Semester = apps.get_model('bou_routines_app', 'Semester')
    
    # Get or create DRC Centre (should already exist from setup_centres command)
    drc_centre, created = Centre.objects.get_or_create(
        code='DRC',
        defaults={
            'name': 'Dhaka Regional Center',
            'description': 'Dhaka Regional Center',
            'is_active': True
        }
    )
    
    # Assign DRC Centre to all teachers without a centre
    teachers_without_centre = Teacher.objects.filter(centre__isnull=True)
    updated_teachers = teachers_without_centre.update(centre=drc_centre)
    
    # Assign DRC Centre to all semesters without a centre
    semesters_without_centre = Semester.objects.filter(centre__isnull=True)
    updated_semesters = semesters_without_centre.update(centre=drc_centre)
    
    print(f"Assigned DRC Centre to {updated_teachers} teachers and {updated_semesters} semesters")


def reverse_assign_default_centre(apps, schema_editor):
    """
    Reverse migration - set centre to None (but this won't work after making field required)
    """
    pass  # Cannot reverse this as field will be required


class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0035_centre_semester_centre_student_centre_teacher_centre'),
    ]

    operations = [
        migrations.RunPython(assign_default_centre, reverse_assign_default_centre),
    ]
