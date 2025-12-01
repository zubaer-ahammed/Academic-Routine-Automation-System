from django.core.management.base import BaseCommand
from bou_routines_app.models import Centre, Semester, Curriculum


class Command(BaseCommand):
    help = 'Create all 8 semesters for DUET Centre (for both OLD and NEW curricula)'

    def handle(self, *args, **options):
        # Get DUET centre
        try:
            duet_centre = Centre.objects.get(code='DUET')
        except Centre.DoesNotExist:
            self.stdout.write(self.style.ERROR('DUET Centre not found. Please run setup_centres command first.'))
            return
        
        # Get curricula
        try:
            old_curriculum = Curriculum.objects.get(code='OLD')
            new_curriculum = Curriculum.objects.get(code='NEW2024')
        except Curriculum.DoesNotExist:
            # Try alternative code
            try:
                new_curriculum = Curriculum.objects.get(code='NEW')
            except Curriculum.DoesNotExist:
                self.stdout.write(self.style.ERROR('Curricula not found. Please run setup_curricula command first.'))
                return
        
        # Semester names for 4 years, 2 semesters each
        semester_names = [
            'Y1S1', 'Y1S2', 'Y2S1', 'Y2S2', 
            'Y3S1', 'Y3S2', 'Y4S1', 'Y4S2'
        ]
        
        # Semester full names mapping
        semester_full_names = {
            'Y1S1': 'First Year First Semester',
            'Y1S2': 'First Year Second Semester',
            'Y2S1': 'Second Year First Semester',
            'Y2S2': 'Second Year Second Semester',
            'Y3S1': 'Third Year First Semester',
            'Y3S2': 'Third Year Second Semester',
            'Y4S1': 'Fourth Year First Semester',
            'Y4S2': 'Fourth Year Second Semester',
        }
        
        created_count = 0
        updated_count = 0
        
        # Create semesters for NEW curriculum
        self.stdout.write(self.style.SUCCESS(f'\n📚 Creating semesters for NEW curriculum ({new_curriculum.name})...'))
        for i, semester_name in enumerate(semester_names):
            semester, created = Semester.objects.get_or_create(
                name=semester_name,
                curriculum=new_curriculum,
                centre=duet_centre,
                defaults={
                    'semester_full_name': semester_full_names[semester_name],
                    'order': 0,
                    'term': 'Regular',
                    'session': '2024-25',
                    'contact_person': 'Academic Coordinator',
                    'contact_person_designation': 'Academic Coordinator',
                    'contact_person_phone': '+880-XXX-XXXXXXX',
                    'contact_person_email': 'academic@bousst.edu.bd',
                    'theory_class_duration_minutes': 60,
                    'lab_class_duration_minutes': 90,
                }
            )
            
            # Update centre if it was created without one
            if not created and semester.centre != duet_centre:
                semester.centre = duet_centre
                semester.save()
                updated_count += 1
                self.stdout.write(f'✅ Updated semester: {semester.name} (NEW) - assigned to DUET')
            elif created:
                created_count += 1
                self.stdout.write(f'✅ Created semester: {semester.name} (NEW)')
            else:
                self.stdout.write(f'ℹ️  Semester already exists: {semester.name} (NEW)')
        
        # Create semesters for OLD curriculum
        self.stdout.write(self.style.SUCCESS(f'\n📚 Creating semesters for OLD curriculum ({old_curriculum.name})...'))
        for i, semester_name in enumerate(semester_names):
            semester, created = Semester.objects.get_or_create(
                name=semester_name,
                curriculum=old_curriculum,
                centre=duet_centre,
                defaults={
                    'semester_full_name': semester_full_names[semester_name],
                    'order': i + 1,
                    'term': 'Regular',
                    'session': '2024-25',
                    'contact_person': 'Academic Coordinator',
                    'contact_person_designation': 'Academic Coordinator',
                    'contact_person_phone': '+880-XXX-XXXXXXX',
                    'contact_person_email': 'academic@bousst.edu.bd',
                    'theory_class_duration_minutes': 60,
                    'lab_class_duration_minutes': 90,
                }
            )
            
            # Update centre if it was created without one
            if not created and semester.centre != duet_centre:
                semester.centre = duet_centre
                semester.save()
                updated_count += 1
                self.stdout.write(f'✅ Updated semester: {semester.name} (OLD) - assigned to DUET')
            elif created:
                created_count += 1
                self.stdout.write(f'✅ Created semester: {semester.name} (OLD)')
            else:
                self.stdout.write(f'ℹ️  Semester already exists: {semester.name} (OLD)')
        
        # Summary
        total_duet_semesters = Semester.objects.filter(centre=duet_centre).count()
        self.stdout.write(self.style.SUCCESS(f'\n🎉 Summary:'))
        self.stdout.write(self.style.SUCCESS(f'   Created: {created_count} semesters'))
        self.stdout.write(self.style.SUCCESS(f'   Updated: {updated_count} semesters'))
        self.stdout.write(self.style.SUCCESS(f'   Total DUET semesters: {total_duet_semesters}'))

