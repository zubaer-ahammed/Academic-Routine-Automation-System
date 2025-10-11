from django.core.management.base import BaseCommand
from bou_routines_app.models import Semester, Curriculum
from datetime import datetime, timedelta

class Command(BaseCommand):
    help = 'Update New Curriculum semester dates to current/future dates'

    def handle(self, *args, **options):
        try:
            new_curriculum = Curriculum.objects.get(code='NEW')
        except Curriculum.DoesNotExist:
            self.stdout.write(self.style.ERROR('New Curriculum not found'))
            return

        # Get all New Curriculum semesters
        semesters = Semester.objects.filter(curriculum=new_curriculum).order_by('order')
        
        if not semesters.exists():
            self.stdout.write(self.style.WARNING('No semesters found for New Curriculum'))
            return

        # Set start date to next Monday
        today = datetime.now().date()
        days_ahead = 7 - today.weekday()  # Monday is 0
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        next_monday = today + timedelta(days=days_ahead)

        self.stdout.write(f'Setting New Curriculum semester dates starting from {next_monday}')
        
        # Update each semester with proper dates
        for i, semester in enumerate(semesters):
            # Calculate start and end dates for each semester
            semester_start = next_monday + timedelta(weeks=i*16)  # 16 weeks per semester
            semester_end = semester_start + timedelta(weeks=16) - timedelta(days=1)  # 16 weeks duration
            
            old_start = semester.start_date
            old_end = semester.end_date
            
            semester.start_date = semester_start
            semester.end_date = semester_end
            semester.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'{semester.name}: {old_start} to {old_end} → {semester_start} to {semester_end}'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated {semesters.count()} New Curriculum semesters')
        )
