from django.core.management.base import BaseCommand
from bou_routines_app.models import Curriculum, Semester, Course, SemesterCourse, Teacher
import re

class Command(BaseCommand):
    help = 'Setup semesters and assign courses for the new curriculum based on PDF structure'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually create the semesters and assign courses (default is dry run)',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        
        if not apply_changes:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
            self.stdout.write('Use --apply to actually create semesters and assign courses\n')
        
        # Get the new curriculum
        try:
            new_curriculum = Curriculum.objects.get(code='NEW')
            self.stdout.write(f'📚 Working with curriculum: {new_curriculum.name} ({new_curriculum.code})')
        except Curriculum.DoesNotExist:
            self.stdout.write(self.style.ERROR('❌ New Curriculum not found. Please run setup_curricula first.'))
            return

        # Create semesters for new curriculum (4 years, 2 semesters each)
        semester_names = [
            'Y1S1', 'Y1S2', 'Y2S1', 'Y2S2', 
            'Y3S1', 'Y3S2', 'Y4S1', 'Y4S2'
        ]
        
        created_semesters = []
        for semester_name in semester_names:
            semester, created = Semester.objects.get_or_create(
                name=semester_name,
                curriculum=new_curriculum,
                defaults={
                    'semester_full_name': f'{semester_name} - New Curriculum',
                    'term': 'Regular',
                    'session': '2024-25',
                    'contact_person': 'Academic Coordinator',
                    'contact_person_designation': 'Academic Coordinator',
                    'contact_person_phone': '+880-XXX-XXXXXXX',
                    'contact_person_email': 'academic@bousst.edu.bd',
                    'theory_class_duration_minutes': 60,
                    'lab_class_duration_minutes': 90,
                }
            )
            if created:
                created_semesters.append(semester)
                self.stdout.write(f'✅ Created semester: {semester.name}')
            else:
                self.stdout.write(f'ℹ️  Semester already exists: {semester.name}')
        
        if not apply_changes:
            self.stdout.write(f'\n📋 Would create {len(created_semesters)} semesters')
            return

        # Get all courses for the new curriculum
        new_courses = Course.objects.filter(curriculum=new_curriculum).order_by('code')
        self.stdout.write(f'\n📚 Found {new_courses.count()} courses in new curriculum')

        # Course assignment mapping based on typical CSE curriculum structure
        course_assignments = {
            'Y1S1': [
                # Language and General Education
                '0231-101',  # Communicative English
                '0222-101',  # Technology and Society
                # Basic Sciences
                '0533-101',  # Physics I
                '0533-102',  # Physics I Lab
                # Mathematics
                '0541-101',  # Differential and Integral Calculus
                '0541-102',  # Linear Algebra
                # Programming
                '0613-101',  # Structured Programming Language
                '0613-102',  # Structured Programming Language Lab
            ],
            'Y1S2': [
                # Language
                '0232-402',  # Technical Writing and Presentation Lab
                # Social Science
                '0223-201',  # Professional Ethics
                '0311-101',  # Economics
                # Basic Sciences
                '0533-103',  # Physics II
                # Mathematics
                '0541-201',  # Discrete Mathematics
                '0541-202',  # Numerical Analysis Lab
                '0542-201',  # Statistical Methods
                '0542-202',  # Statistical Computing Lab
                # Programming
                '0613-201',  # Object Oriented Programming
                '0613-202',  # Object Oriented Programming Lab
            ],
            'Y2S1': [
                # Other Engineering
                '0713-101',  # Electronic Devices and Circuits
                '0713-102',  # Electronic Devices and Circuits Lab
                '0713-201',  # Digital Logic Design
                '0713-202',  # Digital Logic Design Lab
                # CSE Core
                '0613-301',  # Data Structures and Algorithms I
                '0613-302',  # Data Structures and Algorithms I Lab
                '0613-303',  # Computer Organization and Architecture
                '0613-304',  # Computer Organization and Architecture Lab
                '0613-305',  # Database Management System
                '0613-306',  # Database Management System Lab
            ],
            'Y2S2': [
                # CSE Core
                '0613-401',  # Data Structures and Algorithms II
                '0613-402',  # Data Structures and Algorithms II Lab
                '0613-403',  # Software Engineering
                '0613-404',  # Software Engineering Lab
                '0613-405',  # Computer Networks
                '0613-406',  # Computer Networks Lab
                '0613-407',  # Operating Systems
                '0613-408',  # Operating Systems Lab
            ],
            'Y3S1': [
                # CSE Core
                '0613-501',  # Web Programming
                '0613-502',  # Web Programming Lab
                '0613-503',  # Machine Learning
                '0613-504',  # Machine Learning Lab
                '0613-505',  # Computer Graphics
                '0613-506',  # Computer Graphics Lab
                '0613-507',  # Information Security
                '0613-508',  # Information Security Lab
                # Business
                '0413-201',  # Information System Management
            ],
            'Y3S2': [
                # CSE Core
                '0613-601',  # Artificial Intelligence
                '0613-602',  # Artificial Intelligence Lab
                '0613-603',  # Data Communication
                '0613-604',  # Data Communication Lab
                '0613-605',  # Software Development
                '0613-606',  # Software Development Lab
                '0613-607',  # Pattern Recognition
                '0613-608',  # Pattern Recognition Lab
                # Business
                '0413-401',  # Project Management and Finance
                '0413-402',  # Software Project Management Lab
            ],
            'Y4S1': [
                # CSE Core
                '0613-701',  # Advanced Database Systems
                '0613-702',  # Advanced Database Systems Lab
                '0613-703',  # Computer Vision
                '0613-704',  # Computer Vision Lab
                '0613-705',  # Mobile Application Development
                '0613-706',  # Mobile Application Development Lab
                '0613-707',  # Cloud Computing
                '0613-708',  # Cloud Computing Lab
                # Business
                '0413-403',  # Technopreneurship
            ],
            'Y4S2': [
                # CSE Core
                '0613-801',  # Advanced Algorithms
                '0613-802',  # Advanced Algorithms Lab
                '0613-803',  # Blockchain Technology
                '0613-804',  # Blockchain Technology Lab
                '0613-805',  # Quantum Computing
                '0613-806',  # Quantum Computing Lab
                '0613-807',  # Cybersecurity
                '0613-808',  # Cybersecurity Lab
                # Capstone
                '0688-400',  # Capstone Project Design II
            ]
        }

        # Assign courses to semesters
        total_assignments = 0
        for semester_name, course_codes in course_assignments.items():
            try:
                semester = Semester.objects.get(name=semester_name, curriculum=new_curriculum)
                self.stdout.write(f'\n📅 Assigning courses to {semester.name}:')
                
                for course_code in course_codes:
                    try:
                        course = Course.objects.get(code=course_code, curriculum=new_curriculum)
                        
                        # Create or update SemesterCourse
                        semester_course, created = SemesterCourse.objects.get_or_create(
                            semester=semester,
                            course=course,
                            defaults={'number_of_classes': 1}
                        )
                        
                        if created:
                            self.stdout.write(f'  ✅ {course.code} - {course.name}')
                            total_assignments += 1
                        else:
                            self.stdout.write(f'  ℹ️  {course.code} - {course.name} (already assigned)')
                            
                    except Course.DoesNotExist:
                        self.stdout.write(f'  ❌ Course not found: {course_code}')
                        
            except Semester.DoesNotExist:
                self.stdout.write(f'❌ Semester not found: {semester_name}')

        self.stdout.write(f'\n🎉 Successfully assigned {total_assignments} courses to semesters!')
        self.stdout.write(f'📊 Total semesters: {len(semester_names)}')
        self.stdout.write(f'📚 Total courses in curriculum: {new_courses.count()}')
        
        if not apply_changes:
            self.stdout.write(self.style.WARNING('\n🔍 This was a dry run. Use --apply to make actual changes.'))
