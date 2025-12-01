from django.core.management.base import BaseCommand
from bou_routines_app.models import Centre, Teacher, Student, Semester


class Command(BaseCommand):
    help = 'Assign all teachers, students, and semesters to DRC Centre'

    def handle(self, *args, **kwargs):
        try:
            drc_centre = Centre.objects.get(code='DRC')
        except Centre.DoesNotExist:
            self.stdout.write(self.style.ERROR('DRC Centre not found. Please run setup_centres command first.'))
            return
        
        # Count records before update
        teachers_before = Teacher.objects.filter(centre__isnull=True).count()
        students_before = Student.objects.filter(centre__isnull=True).count()
        semesters_before = Semester.objects.filter(centre__isnull=True).count()
        
        # Update teachers
        teachers_updated = Teacher.objects.filter(centre__isnull=True).update(centre=drc_centre)
        
        # Update students
        students_updated = Student.objects.filter(centre__isnull=True).update(centre=drc_centre)
        
        # Update semesters
        semesters_updated = Semester.objects.filter(centre__isnull=True).update(centre=drc_centre)
        
        # Verification
        total_teachers = Teacher.objects.count()
        total_students = Student.objects.count()
        total_semesters = Semester.objects.count()
        
        teachers_with_drc = Teacher.objects.filter(centre=drc_centre).count()
        students_with_drc = Student.objects.filter(centre=drc_centre).count()
        semesters_with_drc = Semester.objects.filter(centre=drc_centre).count()
        
        self.stdout.write(self.style.SUCCESS(f'\n=== Assignment Summary ==='))
        self.stdout.write(self.style.SUCCESS(f'Teachers: Updated {teachers_updated} (Total: {total_teachers}, With DRC: {teachers_with_drc})'))
        self.stdout.write(self.style.SUCCESS(f'Students: Updated {students_updated} (Total: {total_students}, With DRC: {students_with_drc})'))
        self.stdout.write(self.style.SUCCESS(f'Semesters: Updated {semesters_updated} (Total: {total_semesters}, With DRC: {semesters_with_drc})'))
        
        if teachers_with_drc == total_teachers and students_with_drc == total_students and semesters_with_drc == total_semesters:
            self.stdout.write(self.style.SUCCESS('\n✅ All records are now assigned to DRC Centre!'))
        else:
            self.stdout.write(self.style.WARNING('\n⚠️  Some records may still need assignment.'))

