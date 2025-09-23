from django.core.management.base import BaseCommand
from bou_routines_app.models import Student, Semester

class Command(BaseCommand):
    help = 'Add real students from the provided list'

    def handle(self, *args, **options):
        # Get or create the Y3S1 semester
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
        
        # Real student data from the screenshot
        real_students = [
            {'id': '20-0-52-801-004', 'name': 'Mohammad Ibrahim'},
            {'id': '20-0-52-801-006', 'name': 'Md. Zubaer Ahammed'},
            {'id': '20-0-52-801-009', 'name': 'Md. Al Amin Miah'},
            {'id': '20-0-52-801-014', 'name': 'Omar Faruk'},
            {'id': '20-0-52-801-018', 'name': 'Nafiur Rahman Tanzim'},
            {'id': '20-0-52-801-021', 'name': 'Mojahidul Alam'},
            {'id': '20-0-52-801-024', 'name': 'Ashraful Islam'},
            {'id': '20-0-52-801-026', 'name': 'Sumaiya Islam'},
            {'id': '20-0-52-801-031', 'name': 'Md. Nazmul Huda Alamin'},
            {'id': '20-0-52-801-033', 'name': 'S.M. Mozammal Hossain Imon'},
            {'id': '20-0-52-801-038', 'name': 'Mohammad Abdullah Al Mamun'},
            {'id': '20-0-52-801-042', 'name': 'A. B. M. Anowar Hossain'},
            {'id': '20-0-52-801-045', 'name': 'Farjana Akter Ranu'},
            {'id': '20-0-52-801-046', 'name': 'Fahim-Al-Jubaer'},
            {'id': '20-0-52-801-051', 'name': 'Anika Tabassum'},
            {'id': '20-0-52-801-061', 'name': 'Safkat Jamil'},
            {'id': '15-0-52-801-016', 'name': 'Md. Mehadi Hasan'},
            {'id': '18-0-52-801-028', 'name': 'Abdul Hasnat'},
            {'id': '18-0-52-801-038', 'name': 'Arakto Mobin Chowdhury'},
            {'id': '19-0-52-801-039', 'name': 'Md. Mehedi Hasan'},
        ]
        
        students_created = 0
        students_updated = 0
        
        for student_data in real_students:
            student, created = Student.objects.update_or_create(
                id=student_data['id'],
                defaults={
                    'name': student_data['name'],
                    'semester': semester,
                    'session': '2020-21',  # Based on the ID pattern
                    'roll_number': student_data['id'].split('-')[-1]
                }
            )
            
            if created:
                students_created += 1
                self.stdout.write(f'Created student: {student.name} ({student.id})')
            else:
                students_updated += 1
                self.stdout.write(f'Updated student: {student.name} ({student.id})')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully processed {len(real_students)} students. '
                f'Created {students_created} new students, updated {students_updated} existing students.'
            )
        )
