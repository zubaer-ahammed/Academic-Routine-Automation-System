from django.core.management.base import BaseCommand
from bou_routines_app.models import Student, Semester

class Command(BaseCommand):
    help = 'Add sample students for testing attendance functionality'

    def handle(self, *args, **options):
        # Get the first semester (or create one if none exists)
        semester, created = Semester.objects.get_or_create(
            name='Y3S1',
            defaults={
                'semester_full_name': 'Year 3 Semester 1',
                'session': '2024-25',
                'order': 1
            }
        )
        
        if created:
            self.stdout.write(f'Created semester: {semester.name}')
        
        # Sample student data
        sample_students = [
            {'id': '2020-1-60-001', 'name': 'Ahmad Ali', 'session': '2020-21'},
            {'id': '2020-1-60-002', 'name': 'Fatima Khan', 'session': '2020-21'},
            {'id': '2020-1-60-003', 'name': 'Mohammad Rahman', 'session': '2020-21'},
            {'id': '2020-1-60-004', 'name': 'Sultana Begum', 'session': '2020-21'},
            {'id': '2020-1-60-005', 'name': 'Abdul Karim', 'session': '2020-21'},
            {'id': '2020-1-60-006', 'name': 'Nusrat Jahan', 'session': '2020-21'},
            {'id': '2020-1-60-007', 'name': 'Rashid Ahmed', 'session': '2020-21'},
            {'id': '2020-1-60-008', 'name': 'Sabina Yasmin', 'session': '2020-21'},
            {'id': '2020-1-60-009', 'name': 'Kamal Uddin', 'session': '2020-21'},
            {'id': '2020-1-60-010', 'name': 'Nasima Akter', 'session': '2020-21'},
        ]
        
        students_created = 0
        
        for student_data in sample_students:
            student, created = Student.objects.get_or_create(
                id=student_data['id'],
                defaults={
                    'name': student_data['name'],
                    'semester': semester,
                    'session': student_data['session'],
                    'roll_number': student_data['id'].split('-')[-1]
                }
            )
            
            if created:
                students_created += 1
                self.stdout.write(f'Created student: {student.name} ({student.id})')
            else:
                self.stdout.write(f'Student already exists: {student.name} ({student.id})')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully processed {len(sample_students)} students. '
                f'Created {students_created} new students.'
            )
        )
