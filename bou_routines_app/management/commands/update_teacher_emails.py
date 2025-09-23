from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from bou_routines_app.models import Teacher

class Command(BaseCommand):
    help = 'Update all teacher email domains from @bou.edu.bd to @bousst.edu.bd'

    def handle(self, *args, **options):
        # Get all users who have teacher profiles
        teachers = Teacher.objects.filter(user__isnull=False).select_related('user')
        
        if not teachers.exists():
            self.stdout.write(
                self.style.WARNING('No teachers with user accounts found.')
            )
            return
        
        updated_count = 0
        
        for teacher in teachers:
            user = teacher.user
            old_email = user.email
            
            # Check if email has the old domain
            if old_email and old_email.endswith('@bou.edu.bd'):
                new_email = old_email.replace('@bou.edu.bd', '@bousst.edu.bd')
                user.email = new_email
                user.save()
                updated_count += 1
                
                self.stdout.write(
                    f'Updated {teacher.name}: {old_email} -> {new_email}'
                )
            else:
                self.stdout.write(
                    f'Skipped {teacher.name}: {old_email} (does not have @bou.edu.bd domain)'
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully updated {updated_count} teacher email addresses.'
            )
        )
        
        if updated_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    '\nIMPORTANT: Teachers should be notified about their updated email addresses!'
                )
            )
