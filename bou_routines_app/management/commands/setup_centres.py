from django.core.management.base import BaseCommand
from bou_routines_app.models import Centre


class Command(BaseCommand):
    help = 'Set up default centres (Dhaka Regional Center and DUET Study Center)'

    def handle(self, *args, **kwargs):
        # Create or update DRC Centre
        drc_centre, created = Centre.objects.get_or_create(
            code='DRC',
            defaults={
                'name': 'Dhaka Regional Center',
                'description': 'Dhaka Regional Center',
                'is_active': True
            }
        )
        
        # Update name if it already exists with old name
        if not created and drc_centre.name != 'Dhaka Regional Center':
            drc_centre.name = 'Dhaka Regional Center'
            drc_centre.description = 'Dhaka Regional Center'
            drc_centre.save()
            self.stdout.write(self.style.SUCCESS(f"✅ Updated {drc_centre.name}"))
        elif created:
            self.stdout.write(self.style.SUCCESS(f"✅ Created {drc_centre.name}"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️  {drc_centre.name} already exists"))
        
        # Create or update DUET Centre
        duet_centre, created = Centre.objects.get_or_create(
            code='DUET',
            defaults={
                'name': 'DUET Study Center',
                'description': 'DUET Study Center',
                'is_active': True
            }
        )
        
        # Update name if it already exists with old name
        if not created and duet_centre.name != 'DUET Study Center':
            duet_centre.name = 'DUET Study Center'
            duet_centre.description = 'DUET Study Center'
            duet_centre.save()
            self.stdout.write(self.style.SUCCESS(f"✅ Updated {duet_centre.name}"))
        elif created:
            self.stdout.write(self.style.SUCCESS(f"✅ Created {duet_centre.name}"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️  {duet_centre.name} already exists"))
        
        self.stdout.write(self.style.SUCCESS("🎉 Centre setup completed successfully!"))

