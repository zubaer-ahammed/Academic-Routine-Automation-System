from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Permission
from bou_routines_app.models import Teacher
import uuid

class Command(BaseCommand):
    help = 'Create user accounts for existing teachers and assign permissions'

    def handle(self, *args, **options):
        teachers = Teacher.objects.filter(user__isnull=True)
        
        if not teachers.exists():
            self.stdout.write(
                self.style.WARNING('No teachers without user accounts found.')
            )
            return
        
        # Get the attendance permission
        attendance_permission = Permission.objects.get(
            codename='can_mark_attendance',
            content_type__app_label='bou_routines_app'
        )
        
        users_created = 0
        permissions_assigned = 0
        
        for teacher in teachers:
            # Generate username from teacher name
            username = teacher.name.lower().replace(' ', '_').replace('.', '').replace(',', '')
            # Ensure username is unique
            original_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{original_username}_{counter}"
                counter += 1
            
            # Generate email if not provided
            email = f"{username}@bousst.edu.bd"
            
            # Generate a temporary password
            temp_password = str(uuid.uuid4())[:8]
            
            # Create user account
            user = User.objects.create_user(
                username=username,
                email=email,
                password=temp_password,
                first_name=teacher.name.split()[0] if teacher.name.split() else '',
                last_name=' '.join(teacher.name.split()[1:]) if len(teacher.name.split()) > 1 else '',
                is_staff=True,  # Allow access to admin
                is_active=True
            )
            
            # Link teacher to user
            teacher.user = user
            teacher.save()
            
            # Assign attendance permission (default for all teachers)
            user.user_permissions.add(attendance_permission)
            
            users_created += 1
            permissions_assigned += 1
            
            self.stdout.write(
                f'Created user account for {teacher.name}:'
            )
            self.stdout.write(f'  Username: {username}')
            self.stdout.write(f'  Email: {email}')
            self.stdout.write(f'  Temporary Password: {temp_password}')
            self.stdout.write(f'  Permission: can_mark_attendance')
            self.stdout.write('')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully processed {users_created} teachers. '
                f'Created {users_created} user accounts and assigned {permissions_assigned} permissions.'
            )
        )
        
        self.stdout.write(
            self.style.WARNING(
                '\nIMPORTANT: Teachers should change their temporary passwords after first login!'
            )
        )
