# Generated migration to migrate centre data and remove DUET semesters

from django.db import migrations, models
from collections import defaultdict
import django.db.models.deletion

def migrate_centre_data_and_remove_duet_semesters(apps, schema_editor):
    """Migrate centre from Semester to SemesterCourse and remove DUET semesters"""
    SemesterCourse = apps.get_model('bou_routines_app', 'SemesterCourse')
    Semester = apps.get_model('bou_routines_app', 'Semester')
    Centre = apps.get_model('bou_routines_app', 'Centre')
    Teacher = apps.get_model('bou_routines_app', 'Teacher')
    
    # Get centres
    try:
        drc_centre = Centre.objects.get(code='DRC')
    except Centre.DoesNotExist:
        drc_centre = Centre.objects.filter(is_active=True).first()
        if not drc_centre:
            return  # No centres available
    
    try:
        duet_centre = Centre.objects.get(code='DUET')
    except Centre.DoesNotExist:
        duet_centre = None
    
    # Step 1: Set default centre (DRC) for all existing SemesterCourse records
    SemesterCourse.objects.filter(centre__isnull=True).update(centre=drc_centre)
    
    # Step 2: Find duplicate semesters (same name and curriculum) - these are DUET semesters
    # Group semesters by name and curriculum
    semester_groups = defaultdict(list)
    for semester in Semester.objects.all().order_by('id'):
        key = (semester.name, semester.curriculum_id if semester.curriculum else None)
        semester_groups[key].append(semester)
    
    # Step 3: For each group with duplicates, keep the first (lowest ID) and delete the rest
    deleted_count = 0
    moved_count = 0
    
    for key, semesters in semester_groups.items():
        if len(semesters) > 1:
            # Sort by ID to ensure we keep the original (lowest ID)
            semesters.sort(key=lambda s: s.id)
            first_semester = semesters[0]  # Keep this one (original DRC semester)
            
            # Process duplicates (DUET semesters)
            for duplicate_semester in semesters[1:]:
                # Get all SemesterCourse records for this duplicate semester
                duplicate_scs = SemesterCourse.objects.filter(semester=duplicate_semester)
                
                for sc in duplicate_scs:
                    # Determine centre based on teacher's centre, or default to DRC
                    centre_to_use = drc_centre
                    if sc.teacher and duet_centre and sc.teacher.centre_id == duet_centre.id:
                        centre_to_use = duet_centre
                    
                    # Check if a SemesterCourse already exists for first_semester + course + centre
                    existing_sc = SemesterCourse.objects.filter(
                        semester=first_semester,
                        course=sc.course,
                        centre=centre_to_use
                    ).first()
                    
                    if existing_sc:
                        # Update existing one with teacher if duplicate has one
                        if sc.teacher and not existing_sc.teacher:
                            existing_sc.teacher = sc.teacher
                            existing_sc.save()
                        # Delete the duplicate
                        sc.delete()
                    else:
                        # Move to first semester with appropriate centre
                        sc.semester = first_semester
                        sc.centre = centre_to_use
                        sc.save()
                        moved_count += 1
                
                # Delete the duplicate semester
                duplicate_semester.delete()
                deleted_count += 1
    
    print(f"Migration complete: Deleted {deleted_count} duplicate (DUET) semesters, moved {moved_count} SemesterCourse records")

def reverse_migrate_centre_data(apps, schema_editor):
    """Reverse migration - not fully reversible"""
    # This is not fully reversible as we're deleting data
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('bou_routines_app', '0046_add_centre_to_semestercourse_remove_from_semester'),
    ]

    operations = [
        migrations.RunPython(migrate_centre_data_and_remove_duet_semesters, reverse_migrate_centre_data),
        # Make centre non-nullable after data migration
        migrations.AlterField(
            model_name='semestercourse',
            name='centre',
            field=models.ForeignKey(help_text='Study Centre this course is offered in for this semester (required)', on_delete=django.db.models.deletion.PROTECT, to='bou_routines_app.centre'),
        ),
    ]

