from django.core.management.base import BaseCommand
from bou_routines_app.models import Course, Semester, Curriculum, SemesterCourse
import re

class Command(BaseCommand):
    help = 'Assign New Curriculum courses to their respective semesters based on PDF structure'

    def handle(self, *args, **options):
        # Get New Curriculum
        try:
            new_curriculum = Curriculum.objects.get(code='NEW')
        except Curriculum.DoesNotExist:
            self.stdout.write(self.style.ERROR('New Curriculum not found'))
            return

        # Course to semester mapping based on official curriculum screenshots
        # This mapping follows the exact course distribution from the PDF
        course_semester_mapping = {
            # First Year First Semester (Y1S1) - Foundation courses (7 courses, 17 credits)
            'Y1S1': [
                '0222-101',  # Technology and Society
                '0231-101',  # Communicative English
                '0533-101',  # Physics I
                '0533-102',  # Physics I Lab
                '0541-101',  # Differential and Integral Calculus and Vector Analysis
                '0613-101',  # Structured Programming Language
                '0613-102',  # Structured Programming Language Lab
            ],
            
            # First Year Second Semester (Y1S2) - Basic programming and math (7 courses, 17 credits)
            'Y1S2': [
                '0311-101',  # Economics
                '0533-103',  # Physics II
                '0541-102',  # Linear Algebra and Complex Variables
                '0613-103',  # Data Structures and Algorithms I
                '0613-104',  # Data Structures and Algorithms I Lab
                '0713-101',  # Electronic Devices and Circuits
                '0713-102',  # Electronic Devices and Circuits Lab
            ],
            
            # Second Year First Semester (Y2S1) - Object-oriented programming and ethics (8 courses, 18 credits)
            'Y2S1': [
                '0223-201',  # Professional Ethics and Environmental Protection
                '0541-201',  # Discrete Mathematics
                '0542-201',  # Statistical Methods and Probability
                '0542-202',  # Statistical Computing Lab
                '0613-201',  # Object Oriented Programming
                '0613-202',  # Object Oriented Programming Lab
                '0713-201',  # Digital Logic Design
                '0713-202',  # Digital Logic Design Lab
            ],
            
            # Second Year Second Semester (Y2S2) - Database and data structures (8 courses, 16 credits)
            'Y2S2': [
                '0413-201',  # Information System Management
                '0541-202',  # Numerical Analysis Lab
                '0612-201',  # Database Management System
                '0612-202',  # Database Management System Lab
                '0612-203',  # Data Communication
                '0612-204',  # Data Communication Lab
                '0613-203',  # Data Structures and Algorithms II
                '0613-204',  # Data Structures and Algorithms II Lab
            ],
            
            # Third Year First Semester (Y3S1) - Web programming and networking (8 courses, 16 credits)
            'Y3S1': [
                '0612-301',  # Computer Networking
                '0612-302',  # Computer Networking Lab
                '0613-301',  # Web Programming
                '0613-302',  # Web Programming Lab
                '0613-303',  # Software Engineering
                '0613-304',  # Software Development with .Net Framework
                '0613-305',  # Computer Organization and Architecture
                '0613-306',  # Software Testing and Quality Assurance Lab
            ],
            
            # Third Year Second Semester (Y3S2) - Advanced programming and AI (8 courses, 16 credits)
            'Y3S2': [
                '0613-307',  # Microprocessor, Microcontroller and Assembly Language
                '0613-308',  # Microprocessor, Microcontroller and Assembly Language Lab
                '0613-309',  # Theory of Computation
                '0613-310',  # Mobile Application Development Lab
                '0613-311',  # Operating System
                '0613-312',  # Operating System Lab
                '0613-313',  # Artificial Intelligence
                '0613-314',  # Artificial Intelligence Lab
            ],
            
            # Fourth Year First Semester (Y4S1) - Project management and electives (9 courses, 20 credits)
            'Y4S1': [
                '0232-402',  # Technical Writing and Presentation Lab
                '0413-401',  # Project Management and Finance
                '0413-402',  # Software Project Management Lab
                '0613-401',  # Machine Learning
                '0613-402',  # Machine Learning Lab
                '0688-400',  # Capstone Project Design I
                # Note: Elective courses (3 courses) are represented by generic codes in the screenshot
                # These would be selected from available elective courses
            ],
            
            # Fourth Year Second Semester (Y4S2) - Final semester with capstone (7 courses, 20 credits)
            'Y4S2': [
                '0413-403',  # Technopreneurship
                '0612-401',  # Information Security Fundamentals
                '0612-402',  # Information Security Fundamentals Lab
                '0688-400',  # Capstone Project Design II
                # Note: Elective courses (3 courses) are represented by generic codes in the screenshot
                # These would be selected from available elective courses
            ]
        }

        # Get all New Curriculum semesters
        semesters = Semester.objects.filter(curriculum=new_curriculum).order_by('order')
        
        # Clear existing course assignments for New Curriculum
        SemesterCourse.objects.filter(semester__curriculum=new_curriculum).delete()
        self.stdout.write('Cleared existing course assignments for New Curriculum')

        total_assigned = 0
        
        # Assign courses to semesters
        for semester in semesters:
            semester_code = semester.name
            if semester_code in course_semester_mapping:
                course_codes = course_semester_mapping[semester_code]
                assigned_count = 0
                
                for course_code in course_codes:
                    try:
                        course = Course.objects.get(code=course_code, curriculum=new_curriculum)
                        SemesterCourse.objects.create(
                            semester=semester,
                            course=course
                        )
                        assigned_count += 1
                        total_assigned += 1
                    except Course.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'Course {course_code} not found for {semester_code}')
                        )
                
                self.stdout.write(
                    self.style.SUCCESS(f'Assigned {assigned_count} courses to {semester_code}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'No course mapping found for {semester_code}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully assigned {total_assigned} courses to New Curriculum semesters')
        )
