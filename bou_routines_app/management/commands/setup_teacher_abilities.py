from django.core.management.base import BaseCommand
from bou_routines_app.models import Teacher, TeacherAbility

class Command(BaseCommand):
    help = 'Setup default teacher abilities - all teachers get attendance ability by default'

    def handle(self, *args, **options):
        teachers = Teacher.objects.all()
        
        if not teachers.exists():
            self.stdout.write(
                self.style.WARNING('No teachers found. Please add teachers first.')
            )
            return
        
        attendance_abilities_created = 0
        
        for teacher in teachers:
            # Create attendance ability for all teachers (default)
            attendance_ability, created = TeacherAbility.objects.get_or_create(
                teacher=teacher,
                ability='attendance',
                defaults={'is_enabled': True}
            )
            
            if created:
                attendance_abilities_created += 1
                self.stdout.write(
                    f'Created attendance ability for teacher: {teacher.name}'
                )
            else:
                self.stdout.write(
                    f'Attendance ability already exists for teacher: {teacher.name}'
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully processed {teachers.count()} teachers. '
                f'Created {attendance_abilities_created} new attendance abilities.'
            )
        )
        
        # Show current abilities
        self.stdout.write('\nCurrent teacher abilities:')
        for ability in TeacherAbility.objects.select_related('teacher').order_by('teacher__name', 'ability'):
            status = 'Enabled' if ability.is_enabled else 'Disabled'
            self.stdout.write(
                f'  {ability.teacher.name}: {ability.get_ability_display()} - {status}'
            )
