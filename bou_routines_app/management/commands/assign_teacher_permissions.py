from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission
from bou_routines_app.models import Teacher


class Command(BaseCommand):
    help = 'Assign all teacher permissions (can_mark_attendance, can_manage_ca, can_manage_final_marks) to all teachers'

    def handle(self, *args, **options):
        # Get the three permissions
        try:
            attendance_perm = Permission.objects.get(
                codename='can_mark_attendance',
                content_type__app_label='bou_routines_app'
            )
            ca_perm = Permission.objects.get(
                codename='can_manage_ca',
                content_type__app_label='bou_routines_app'
            )
            final_marks_perm = Permission.objects.get(
                codename='can_manage_final_marks',
                content_type__app_label='bou_routines_app'
            )
        except Permission.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f'Permission not found: {e}'))
            self.stdout.write(self.style.WARNING('Make sure migrations have been run to create these permissions.'))
            return

        # Get all teachers
        teachers = Teacher.objects.all()
        total_teachers = teachers.count()
        
        if total_teachers == 0:
            self.stdout.write(self.style.WARNING('No teachers found in the database.'))
            return

        assigned_count = 0
        skipped_count = 0

        for teacher in teachers:
            if not teacher.user:
                self.stdout.write(self.style.WARNING(f'Teacher "{teacher.name}" has no associated user account. Skipping.'))
                skipped_count += 1
                continue

            user = teacher.user
            permissions_added = []

            # Assign attendance permission
            if not user.has_perm('bou_routines_app.can_mark_attendance'):
                user.user_permissions.add(attendance_perm)
                permissions_added.append('can_mark_attendance')

            # Assign CA permission
            if not user.has_perm('bou_routines_app.can_manage_ca'):
                user.user_permissions.add(ca_perm)
                permissions_added.append('can_manage_ca')

            # Assign final marks permission
            if not user.has_perm('bou_routines_app.can_manage_final_marks'):
                user.user_permissions.add(final_marks_perm)
                permissions_added.append('can_manage_final_marks')

            if permissions_added:
                assigned_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Assigned permissions to {teacher.name} ({user.username}): {", ".join(permissions_added)}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'Teacher {teacher.name} ({user.username}) already has all permissions.'
                    )
                )

        self.stdout.write(self.style.SUCCESS(
            f'\nCompleted! Assigned permissions to {assigned_count} out of {total_teachers} teachers.'
        ))
        if skipped_count > 0:
            self.stdout.write(self.style.WARNING(
                f'Skipped {skipped_count} teachers without user accounts.'
            ))

