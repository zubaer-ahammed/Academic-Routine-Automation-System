from django.core.management.base import BaseCommand
from bou_routines_app.models import Teacher, Centre


class Command(BaseCommand):
    help = 'Add teachers from DUET Centre to the database'

    def handle(self, *args, **options):
        # Get DUET Centre
        try:
            duet_centre = Centre.objects.get(code='DUET')
        except Centre.DoesNotExist:
            self.stdout.write(self.style.ERROR('DUET Centre not found. Please run setup_centres command first.'))
            return
        
        # List of teachers from the screenshot
        teachers_data = [
            {'name': 'Prof. Dr. Md. Nasim Akhtar', 'short_name': 'DMNA', 'department': 'CSE', 'designation': 'Professor'},
            {'name': 'Prof. Dr. Md. Azmal Hossain', 'short_name': 'DMAH', 'department': 'Math', 'designation': 'Professor'},
            {'name': 'Dr. Fatema Sultana', 'short_name': 'DFS', 'department': 'HSS', 'designation': 'Assistant Professor'},
            {'name': 'Afruza Haque', 'short_name': 'AH', 'department': 'HSS', 'designation': 'Assistant Professor'},
            {'name': 'Prof. Dr. Md. Sharafat Hossain', 'short_name': 'DMSH', 'department': 'EEE', 'designation': 'Professor'},
            {'name': 'Prof. Dr. Md. Atiqur Rahman', 'short_name': 'MARD', 'department': 'EEE', 'designation': 'Professor'},
            {'name': 'Prof. Dr. Md. Sahab Uddin', 'short_name': 'DMSU', 'department': 'Phy', 'designation': 'Professor'},
            {'name': 'Prof. Dr. Md. Abdur Rouf', 'short_name': 'DMAR', 'department': 'CSE', 'designation': 'Professor'},
            {'name': 'Prof. Dr. Md. Obaidur Rahman', 'short_name': 'DMOR', 'department': 'CSE', 'designation': 'Professor'},
            {'name': 'Prof. Dr. Rafiqul Islam', 'short_name': 'DRI', 'department': 'CSE', 'designation': 'Professor'},
            {'name': 'Prof. Dr. Momataz Begum', 'short_name': 'DMB', 'department': 'CSE', 'designation': 'Professor'},
            {'name': 'Prof. Dr. Md. Shafiqul Islam', 'short_name': 'DMSI', 'department': 'CSE', 'designation': 'Professor'},
            {'name': 'Prof. Dr. Amran Hossain', 'short_name': 'DAH', 'department': 'CSE', 'designation': 'Professor'},
            {'name': 'Dr. Md. Jakirul Islam', 'short_name': 'DMJI', 'department': 'CSE', 'designation': 'Associate Professor'},
            {'name': 'Ms. Sumaya Kazary', 'short_name': 'SK', 'department': 'CSE', 'designation': 'Assistant Professor'},
            {'name': 'Mr. Khwaza Imran Masud', 'short_name': 'KIM', 'department': 'CSE', 'designation': 'Assistant Professor'},
            {'name': 'Dr. Umme Fawzia Rahim', 'short_name': 'DUFR', 'department': 'CSE', 'designation': 'Assistant Professor'},
            {'name': 'Mst. Sumaya Khatun', 'short_name': 'MSK', 'department': 'CSE', 'designation': 'Lecturer'},
            {'name': 'Mr. Litan Islam', 'short_name': 'LI', 'department': 'CSE', 'designation': 'Lecturer'},
            {'name': 'Mr. Md. Rajibul Islam', 'short_name': 'MRI', 'department': 'CSE', 'designation': 'Lecturer'},
            {'name': 'Mr. Md. Mohedul Hasan', 'short_name': 'MMH', 'department': 'Math', 'designation': 'Assistant Professor'},
            {'name': 'Prof. Dr. Main Uddin Ahmed', 'short_name': 'DMUA', 'department': 'Math', 'designation': 'Professor'},
        ]
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        self.stdout.write(self.style.SUCCESS(f'\n📚 Adding teachers to DUET Centre ({duet_centre.name})...\n'))
        
        for teacher_data in teachers_data:
            # Check if teacher already exists by name or short_name
            existing_by_name = Teacher.objects.filter(name=teacher_data['name']).first()
            existing_by_short = Teacher.objects.filter(short_name=teacher_data['short_name']).first()
            
            if existing_by_name:
                # Update existing teacher to DUET centre if not already set
                if existing_by_name.centre != duet_centre:
                    existing_by_name.centre = duet_centre
                    existing_by_name.department = teacher_data.get('department', existing_by_name.department)
                    existing_by_name.designation = teacher_data.get('designation', existing_by_name.designation)
                    existing_by_name.save()
                    updated_count += 1
                    self.stdout.write(f'✅ Updated: {teacher_data["name"]} - assigned to DUET')
                else:
                    skipped_count += 1
                    self.stdout.write(f'ℹ️  Already exists: {teacher_data["name"]}')
            elif existing_by_short:
                # Update existing teacher by short name
                if existing_by_short.centre != duet_centre:
                    existing_by_short.centre = duet_centre
                    existing_by_short.department = teacher_data.get('department', existing_by_short.department)
                    existing_by_short.designation = teacher_data.get('designation', existing_by_short.designation)
                    existing_by_short.save()
                    updated_count += 1
                    self.stdout.write(f'✅ Updated: {existing_by_short.name} (by short name {teacher_data["short_name"]}) - assigned to DUET')
                else:
                    skipped_count += 1
                    self.stdout.write(f'ℹ️  Already exists: {existing_by_short.name} (by short name {teacher_data["short_name"]})')
            else:
                # Create new teacher
                teacher = Teacher.objects.create(
                    name=teacher_data['name'],
                    short_name=teacher_data['short_name'],
                    department=teacher_data.get('department', ''),
                    designation=teacher_data.get('designation', ''),
                    centre=duet_centre
                )
                created_count += 1
                self.stdout.write(f'✅ Created: {teacher_data["name"]} ({teacher_data["short_name"]})')
        
        # Summary
        total_duet_teachers = Teacher.objects.filter(centre=duet_centre).count()
        self.stdout.write(self.style.SUCCESS(f'\n🎉 Summary:'))
        self.stdout.write(self.style.SUCCESS(f'   Created: {created_count} teachers'))
        self.stdout.write(self.style.SUCCESS(f'   Updated: {updated_count} teachers'))
        self.stdout.write(self.style.SUCCESS(f'   Skipped: {skipped_count} teachers'))
        self.stdout.write(self.style.SUCCESS(f'   Total DUET teachers: {total_duet_teachers}'))

