from django.core.management.base import BaseCommand
from bou_routines_app.models import SemesterCourse, Centre, Teacher

class Command(BaseCommand):
    help = 'Fix SemesterCourse records for DRC centre that have DUET teachers assigned'

    def handle(self, *args, **options):
        # Get centres
        try:
            drc_centre = Centre.objects.get(code='DRC')
            duet_centre = Centre.objects.get(code='DUET')
        except Centre.DoesNotExist:
            self.stdout.write(self.style.ERROR('DRC or DUET Centre not found.'))
            return
        
        # Get TBD Teacher for DRC
        tbd_drc_teacher = Teacher.objects.filter(
            name__icontains='TBD',
            centre=drc_centre
        ).exclude(name__icontains='DUET').first()
        
        if not tbd_drc_teacher:
            # Create TBD Teacher for DRC if it doesn't exist
            tbd_drc_teacher = Teacher.objects.create(
                name='TBD Teacher',
                short_name='TBD',
                centre=drc_centre,
                designation='To Be Determined',
                department='TBD'
            )
            self.stdout.write(self.style.SUCCESS('✅ Created TBD Teacher for DRC Centre'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✅ Using existing TBD Teacher for DRC: {tbd_drc_teacher.name}'))
        
        # Find all SemesterCourse records for DRC centre that have DUET teachers
        problematic_scs = SemesterCourse.objects.filter(
            centre=drc_centre,
            teacher__centre=duet_centre
        ).select_related('teacher', 'teacher__centre')
        
        count = problematic_scs.count()
        self.stdout.write(self.style.WARNING(f'\n⚠️  Found {count} SemesterCourse records for DRC centre with DUET teachers\n'))
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('✅ No issues found. All records are correct.'))
            return
        
        # Fix them by setting teacher to DRC TBD Teacher or None
        fixed_count = 0
        for sc in problematic_scs:
            old_teacher = sc.teacher.name if sc.teacher else 'None'
            sc.teacher = tbd_drc_teacher
            sc.save()
            fixed_count += 1
            self.stdout.write(f'✅ Fixed: {sc.semester.name} - {sc.course.code} (was: {old_teacher}, now: {tbd_drc_teacher.name})')
        
        self.stdout.write(self.style.SUCCESS(f'\n📊 Summary:'))
        self.stdout.write(f'   Fixed: {fixed_count} records')
        self.stdout.write(f'   All DRC SemesterCourse records now have DRC teachers or TBD Teacher (DRC)')

