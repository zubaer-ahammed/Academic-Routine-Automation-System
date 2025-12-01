from django.core.management.base import BaseCommand
from bou_routines_app.models import Semester, Course, Teacher, Centre, SemesterCourse, Curriculum

class Command(BaseCommand):
    help = 'Update SemesterCourse table with teacher assignments for DRC Centre semesters'

    def handle(self, *args, **options):
        # Get DRC Centre
        try:
            drc_centre = Centre.objects.get(code='DRC')
        except Centre.DoesNotExist:
            self.stdout.write(self.style.ERROR('DRC Centre not found. Please run setup_centres command first.'))
            return
        
        # Get NEW curriculum (assuming these are for NEW curriculum)
        try:
            new_curriculum = Curriculum.objects.get(code='NEW')
        except Curriculum.DoesNotExist:
            try:
                new_curriculum = Curriculum.objects.get(code='NEW2024')
            except Curriculum.DoesNotExist:
                self.stdout.write(self.style.ERROR('NEW Curriculum not found.'))
                return
        
        # Course and teacher data from images
        # Format: (semester_name, course_code, number_of_classes, teacher_short_name)
        course_data = [
            # Y1S2 (First Year Second Semester)
            ('Y1S2', 'MAT1231', 24, 'EA'),
            ('Y1S2', 'HUM1222', 16, 'ZR'),
            ('Y1S2', 'EEE1233', 24, 'AK'),
            ('Y1S2', 'EEE12P4', 18, 'KMRR'),
            ('Y1S2', 'CSE1235', 24, 'MNU'),
            ('Y1S2', 'CSE12P6', 18, 'MH'),
            ('Y1S2', 'CSE1237', 24, 'MMR'),
            ('Y1S2', 'CSE12P8', 18, 'MMR'),
            
            # Y2S2 (Second Year Second Semester)
            ('Y2S2', 'ECO2221', 16, 'DMMR'),
            ('Y2S2', 'CSE2232', 24, 'HR'),
            ('Y2S2', 'CSE22P3', 10, 'HR'),
            ('Y2S2', 'CSE2234', 24, 'PAA'),
            ('Y2S2', 'CSE22P5', 10, 'PAA'),
            ('Y2S2', 'CSE2236', 24, 'ZM'),
            ('Y2S2', 'CSE22P7', 18, 'ZM'),
            ('Y2S2', 'CSE2238', 24, 'MI'),
            ('Y2S2', 'CSE22P9', 18, 'MI'),
            
            # Y3S2 (Third Year Second Semester)
            ('Y3S2', 'CSE3221', 16, 'MMR'),
            ('Y3S2', 'CSE3233', 24, 'MHT'),
            ('Y3S2', 'CSE32P4', 18, 'MHT'),
            ('Y3S2', 'CSE3235', 24, 'RH'),
            ('Y3S2', 'CSE32P6', 10, 'RH'),
            ('Y3S2', 'CSE3232', 24, 'RM'),
            ('Y3S2', 'CSE3237', 24, 'MR'),
            ('Y3S2', 'CSE32P8', 18, 'MR'),
            ('Y3S2', 'CSE32P9', 18, 'KMRR'),
            
            # Y4S2 (Fourth Year Second Semester)
            ('Y4S2', 'CSE4231', 24, 'MH'),
            ('Y4S2', 'CSE4232', 24, 'STS'),
            ('Y4S2', 'CSE42P3', 10, 'STS'),
            ('Y4S2', 'CSE4234', 24, 'RH'),
            ('Y4S2', 'CSE42P5', 18, 'RH'),
            ('Y4S2', 'CSE4246', 0, None),  # Project/Thesis - no teacher
            ('Y4S2', 'CSE4227', 0, None),  # Comprehensive Viva Voce - no teacher
        ]
        
        updated_count = 0
        created_count = 0
        not_found_count = 0
        
        self.stdout.write(self.style.SUCCESS(f'\n📚 Updating SemesterCourse teacher assignments for DRC Centre...\n'))
        
        for semester_name, course_code, num_classes, teacher_short_name in course_data:
            try:
                # Get semester
                semester = Semester.objects.get(name=semester_name, curriculum=new_curriculum)
                
                # Get course
                course = Course.objects.get(code=course_code)
                
                # Get teacher if provided
                teacher = None
                if teacher_short_name:
                    teacher = Teacher.objects.filter(short_name=teacher_short_name, centre=drc_centre).first()
                    if not teacher:
                        # Try case-insensitive search
                        teacher = Teacher.objects.filter(short_name__iexact=teacher_short_name, centre=drc_centre).first()
                
                # Get or create SemesterCourse
                semester_course, created = SemesterCourse.objects.get_or_create(
                    semester=semester,
                    course=course,
                    centre=drc_centre,
                    defaults={
                        'number_of_classes': num_classes,
                        'teacher': teacher
                    }
                )
                
                if not created:
                    # Update existing
                    semester_course.number_of_classes = num_classes
                    semester_course.teacher = teacher
                    semester_course.save()
                    updated_count += 1
                    status = '✅ Updated'
                else:
                    created_count += 1
                    status = '✅ Created'
                
                teacher_name = teacher.name if teacher else 'No teacher'
                self.stdout.write(f'{status}: {semester_name} - {course_code} ({num_classes} classes) - {teacher_name}')
                
            except Semester.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'⚠️  Semester not found: {semester_name} ({new_curriculum.code})'))
                not_found_count += 1
            except Course.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'⚠️  Course not found: {course_code}'))
                not_found_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Error processing {semester_name} - {course_code}: {str(e)}'))
                not_found_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'\n📊 Summary:'))
        self.stdout.write(f'   Created: {created_count}')
        self.stdout.write(f'   Updated: {updated_count}')
        self.stdout.write(f'   Not found/Errors: {not_found_count}')
        self.stdout.write(f'   Total processed: {len(course_data)}')

