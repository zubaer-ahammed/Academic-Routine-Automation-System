from django.core.management.base import BaseCommand
from bou_routines_app.models import Curriculum, Course, Semester
from datetime import date


class Command(BaseCommand):
    help = 'Set up default curricula and migrate existing data'

    def handle(self, *args, **kwargs):
        # Create default curricula
        current_curriculum, created = Curriculum.objects.get_or_create(
            code='OLD',
            defaults={
                'name': 'Current Curriculum',
                'description': 'The existing curriculum for current batches',
                'is_active': True,
                'effective_from': date(2020, 1, 1)
            }
        )
        
        new_curriculum, created = Curriculum.objects.get_or_create(
            code='NEW2024',
            defaults={
                'name': 'New Curriculum 2024',
                'description': 'The new curriculum for incoming batches',
                'is_active': True,
                'effective_from': date(2024, 1, 1)
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f"✅ Created {current_curriculum.name}"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️  {current_curriculum.name} already exists"))
            
        if created:
            self.stdout.write(self.style.SUCCESS(f"✅ Created {new_curriculum.name}"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️  {new_curriculum.name} already exists"))
        
        # Migrate existing courses to current curriculum
        existing_courses = Course.objects.filter(curriculum__isnull=True)
        updated_count = 0
        
        for course in existing_courses:
            course.curriculum = current_curriculum
            course.save()
            updated_count += 1
        
        if updated_count > 0:
            self.stdout.write(self.style.SUCCESS(f"✅ Migrated {updated_count} existing courses to Current Curriculum"))
        
        # Migrate existing semesters to current curriculum
        existing_semesters = Semester.objects.filter(curriculum__isnull=True)
        semester_updated_count = 0
        
        for semester in existing_semesters:
            semester.curriculum = current_curriculum
            semester.save()
            semester_updated_count += 1
        
        if semester_updated_count > 0:
            self.stdout.write(self.style.SUCCESS(f"✅ Migrated {semester_updated_count} existing semesters to Current Curriculum"))
        
        self.stdout.write(self.style.SUCCESS("🎉 Curriculum setup completed successfully!"))
