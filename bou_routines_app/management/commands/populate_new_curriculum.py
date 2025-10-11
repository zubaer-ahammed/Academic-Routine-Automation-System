from django.core.management.base import BaseCommand
from bou_routines_app.models import Curriculum, Course, Teacher
from datetime import date


class Command(BaseCommand):
    help = 'Populate new curriculum with sample courses based on new curriculum structure'

    def handle(self, *args, **kwargs):
        # Get the new curriculum
        try:
            new_curriculum = Curriculum.objects.get(code='NEW2024')
        except Curriculum.DoesNotExist:
            self.stdout.write(self.style.ERROR("New curriculum not found. Please run setup_curricula first."))
            return
        
        # Sample courses for the new curriculum (you can modify these based on the actual PDF content)
        new_courses_data = [
            # Year 1, Semester 1
            {'code': 'CSE1101', 'name': 'Programming Fundamentals', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE1101P', 'name': 'Programming Fundamentals Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            {'code': 'MAT1101', 'name': 'Mathematics I', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'ENG1101', 'name': 'English Language', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'GENERAL'},
            
            # Year 1, Semester 2
            {'code': 'CSE1201', 'name': 'Data Structures', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE1201P', 'name': 'Data Structures Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            {'code': 'MAT1201', 'name': 'Mathematics II', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'PHY1201', 'name': 'Physics', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'GENERAL'},
            
            # Year 2, Semester 1
            {'code': 'CSE2101', 'name': 'Object-Oriented Programming', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE2101P', 'name': 'Object-Oriented Programming Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            {'code': 'CSE2102', 'name': 'Database Systems', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE2102P', 'name': 'Database Systems Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            {'code': 'MAT2101', 'name': 'Discrete Mathematics', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            
            # Year 2, Semester 2
            {'code': 'CSE2201', 'name': 'Computer Networks', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE2201P', 'name': 'Computer Networks Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            {'code': 'CSE2202', 'name': 'Software Engineering', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE2202P', 'name': 'Software Engineering Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            {'code': 'MAT2201', 'name': 'Statistics', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            
            # Year 3, Semester 1
            {'code': 'CSE3101', 'name': 'Algorithm Design', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE3101P', 'name': 'Algorithm Design Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            {'code': 'CSE3102', 'name': 'Machine Learning', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE3102P', 'name': 'Machine Learning Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            {'code': 'CSE3103', 'name': 'Web Development', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE3103P', 'name': 'Web Development Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            
            # Year 3, Semester 2
            {'code': 'CSE3201', 'name': 'Artificial Intelligence', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE3201P', 'name': 'Artificial Intelligence Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            {'code': 'CSE3202', 'name': 'Cybersecurity', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE3202P', 'name': 'Cybersecurity Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            {'code': 'CSE3203', 'name': 'Mobile App Development', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE3203P', 'name': 'Mobile App Development Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            
            # Year 4, Semester 1
            {'code': 'CSE4101', 'name': 'Final Year Project I', 'credits': 3, 'is_theory': False, 'is_lab': False, 'course_type': 'PROJECT'},
            {'code': 'CSE4102', 'name': 'Cloud Computing', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE4102P', 'name': 'Cloud Computing Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            {'code': 'CSE4103', 'name': 'Data Science', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'CORE'},
            {'code': 'CSE4103P', 'name': 'Data Science Lab', 'credits': 1, 'is_theory': False, 'is_lab': True, 'course_type': 'CORE'},
            
            # Year 4, Semester 2
            {'code': 'CSE4201', 'name': 'Final Year Project II', 'credits': 3, 'is_theory': False, 'is_lab': False, 'course_type': 'PROJECT'},
            {'code': 'CSE4202', 'name': 'Blockchain Technology', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'ELECTIVE'},
            {'code': 'CSE4203', 'name': 'IoT Development', 'credits': 3, 'is_theory': True, 'is_lab': False, 'course_type': 'ELECTIVE'},
        ]
        
        # Get or create a default teacher for new courses
        default_teacher, created = Teacher.objects.get_or_create(
            name="TBD Teacher",
            defaults={'short_name': 'TBD'}
        )
        
        created_count = 0
        updated_count = 0
        
        for course_data in new_courses_data:
            # Make course name unique by adding curriculum suffix
            unique_name = f"{course_data['name']} ({new_curriculum.code})"
            
            course, created = Course.objects.get_or_create(
                code=course_data['code'],
                curriculum=new_curriculum,
                defaults={
                    'name': unique_name,
                    'teacher': default_teacher,
                    'credits': course_data['credits'],
                    'is_theory': course_data['is_theory'],
                    'is_lab': course_data['is_lab'],
                    'course_type': course_data['course_type'],
                    # Set CA distribution based on course type
                    'ca_attendance_weight': 10,
                    'ca_assignment_weight': 20,
                    'ca_quiz_weight': 20,
                    'ca_midterm_weight': 50,
                    'lab_ca_attendance_weight': 10,
                    'lab_ca_assignment_weight': 30,
                    'lab_ca_practical_weight': 60,
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"✅ Created course: {course.code} - {course.name}"))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"⚠️  Course already exists: {course.code} - {course.name}"))
        
        self.stdout.write(self.style.SUCCESS(f"🎉 New curriculum population completed!"))
        self.stdout.write(self.style.SUCCESS(f"✅ Created {created_count} new courses"))
        self.stdout.write(self.style.SUCCESS(f"⚠️  {updated_count} courses already existed"))
        self.stdout.write(self.style.SUCCESS(f"📚 Total courses in new curriculum: {Course.objects.filter(curriculum=new_curriculum).count()}"))
