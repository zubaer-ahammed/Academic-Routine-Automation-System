from django.core.management.base import BaseCommand
from bou_routines_app.models import Course, Semester, Centre, Teacher, SemesterCourse, Curriculum


class Command(BaseCommand):
    help = 'Copy all courses from DRC SemesterCourse records to DUET SemesterCourse records with TBD Teacher (DUET)'

    def handle(self, *args, **options):
        # Get centres
        try:
            drc_centre = Centre.objects.get(code='DRC')
            duet_centre = Centre.objects.get(code='DUET')
        except Centre.DoesNotExist:
            self.stdout.write(self.style.ERROR('DRC or DUET Centre not found. Please run setup_centres command first.'))
            return
        
        # Get or create TBD Teacher for DUET
        tbd_teacher = Teacher.objects.filter(
            name__icontains='TBD Teacher (DUET)',
            centre=duet_centre
        ).first()
        
        if not tbd_teacher:
            # Try alternative names
            tbd_teacher = Teacher.objects.filter(
                name__icontains='TBD',
                centre=duet_centre
            ).first()
        
        if not tbd_teacher:
            # Create TBD Teacher for DUET
            # Find a unique short_name
            base_short = 'TBD'
            short_name = base_short
            counter = 1
            while Teacher.objects.filter(short_name=short_name).exists():
                short_name = f'{base_short}{counter}'
                counter += 1
            
            tbd_teacher = Teacher.objects.create(
                name='TBD Teacher (DUET)',
                short_name=short_name,
                centre=duet_centre,
                designation='To Be Determined',
                department='TBD'
            )
            self.stdout.write(self.style.SUCCESS(f'✅ Created TBD Teacher (DUET)'))
        else:
            self.stdout.write(self.style.SUCCESS(f'ℹ️  Using existing TBD Teacher: {tbd_teacher.name}'))
        
        # Get all SemesterCourse records for DRC centre
        # Note: Semesters are now shared across centres, so we filter by centre in SemesterCourse
        drc_semester_courses = SemesterCourse.objects.filter(
            centre=drc_centre
        ).select_related('semester', 'course', 'course__curriculum', 'teacher')
        
        self.stdout.write(self.style.SUCCESS(f'\n📚 Found {drc_semester_courses.count()} SemesterCourse records for DRC Centre\n'))
        
        courses_created = 0
        courses_skipped = 0
        courses_updated = 0
        
        # Group by semester for better output
        semesters_processed = {}
        
        for drc_sc in drc_semester_courses:
            semester = drc_sc.semester
            course = drc_sc.course
            
            # Track by semester
            if semester.name not in semesters_processed:
                semesters_processed[semester.name] = {
                    'curriculum': semester.curriculum.code if semester.curriculum else 'No Curriculum',
                    'count': 0
                }
            
            # Check if SemesterCourse already exists for DUET
            duet_sc, created = SemesterCourse.objects.get_or_create(
                semester=semester,
                course=course,
                centre=duet_centre,
                defaults={
                    'teacher': tbd_teacher,
                    'number_of_classes': drc_sc.number_of_classes
                }
            )
            
            if created:
                courses_created += 1
                semesters_processed[semester.name]['count'] += 1
                self.stdout.write(f'✅ Created: {semester.name} - {course.code} ({course.name}) - {drc_sc.number_of_classes} classes')
            else:
                # Update if teacher is not set or is from DRC
                if not duet_sc.teacher or (duet_sc.teacher and duet_sc.teacher.centre == drc_centre):
                    duet_sc.teacher = tbd_teacher
                    duet_sc.number_of_classes = drc_sc.number_of_classes
                    duet_sc.save()
                    courses_updated += 1
                    self.stdout.write(f'🔄 Updated: {semester.name} - {course.code} ({course.name}) - assigned TBD Teacher (DUET)')
                else:
                    courses_skipped += 1
                    self.stdout.write(f'ℹ️  Skipped: {semester.name} - {course.code} (already has DUET teacher: {duet_sc.teacher.name})')
        
        # Summary by semester
        self.stdout.write(self.style.SUCCESS(f'\n📊 Summary by Semester:'))
        for sem_name, info in sorted(semesters_processed.items()):
            self.stdout.write(f'   {sem_name} ({info["curriculum"]}): {info["count"]} courses')
        
        # Overall summary
        total_duet_semester_courses = SemesterCourse.objects.filter(centre=duet_centre).count()
        
        self.stdout.write(self.style.SUCCESS(f'\n🎉 Overall Summary:'))
        self.stdout.write(self.style.SUCCESS(f'   Created: {courses_created} SemesterCourse records'))
        self.stdout.write(self.style.SUCCESS(f'   Updated: {courses_updated} SemesterCourse records'))
        self.stdout.write(self.style.SUCCESS(f'   Skipped: {courses_skipped} SemesterCourse records'))
        self.stdout.write(self.style.SUCCESS(f'   Total DUET SemesterCourse records: {total_duet_semester_courses}'))
