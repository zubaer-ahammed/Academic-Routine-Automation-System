from django.core.management.base import BaseCommand
from bou_routines_app.models import Course

class Command(BaseCommand):
    help = 'Update CA mark distribution for all courses according to new specifications'

    def handle(self, *args, **options):
        self.stdout.write('Updating CA mark distribution...')
        
        # Update Theory courses
        theory_courses = Course.objects.filter(is_theory=True, is_lab=False)
        theory_updated = 0
        
        for course in theory_courses:
            course.ca_attendance_weight = 5  # Attendance (5)
            course.ca_assignment_weight = 5  # Assignment/Presentation (5)
            course.ca_quiz_weight = 0  # Remove quiz weight
            course.ca_midterm_weight = 20  # Mid-Term Exam (20)
            course.save()
            theory_updated += 1
        
        # Update Lab courses
        lab_courses = Course.objects.filter(is_lab=True)
        lab_updated = 0
        
        for course in lab_courses:
            course.lab_ca_attendance_weight = 10  # Attendance (10)
            course.lab_ca_assignment_weight = 10  # Assignment/Lab Report (10)
            course.lab_ca_practical_weight = 30  # Experiment/Lab Based Project Works (30)
            course.save()
            lab_updated += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully updated CA distribution:\n'
                f'- Theory courses: {theory_updated}\n'
                f'- Lab courses: {lab_updated}\n\n'
                f'New CA Distribution:\n'
                f'Theory: Attendance (5), Assignment/Presentation (5), Mid-Term Exam (20)\n'
                f'Lab: Attendance (10), Assignment/Lab Report (10), Experiment/Lab Project (30)'
            )
        )
