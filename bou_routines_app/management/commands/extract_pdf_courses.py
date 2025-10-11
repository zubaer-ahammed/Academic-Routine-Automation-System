from django.core.management.base import BaseCommand
from bou_routines_app.models import Curriculum, Course, Teacher
import PyPDF2
import re
from datetime import date


class Command(BaseCommand):
    help = 'Extract course data from New-Curriculum-BSc-in CSE-Courses.pdf and populate the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--pdf-path',
            type=str,
            default='new_curriculum/New-Curriculum-BSc-in CSE-Courses.pdf',
            help='Path to the PDF file'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating courses'
        )

    def handle(self, *args, **options):
        pdf_path = options['pdf_path']
        dry_run = options['dry_run']
        
        try:
            # Get the New Curriculum
            new_curriculum = Curriculum.objects.get(code='NEW')
            self.stdout.write(f"📚 Working with curriculum: {new_curriculum.name} ({new_curriculum.code})")
        except Curriculum.DoesNotExist:
            self.stdout.write(self.style.ERROR("New Curriculum not found. Please run setup_curricula first."))
            return

        # Get or create a default teacher
        default_teacher, created = Teacher.objects.get_or_create(
            name="TBD Teacher",
            defaults={'short_name': 'TBD'}
        )

        try:
            # Extract text from PDF
            self.stdout.write(f"📄 Extracting text from: {pdf_path}")
            
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
            
            self.stdout.write("✅ PDF text extracted successfully")
            
            # Look for course patterns in the entire PDF
            # The PDF seems to have courses listed with course codes and titles
            # Let's extract all course information from the text
            section_content = text
            
            self.stdout.write("📋 Section content found:")
            self.stdout.write(section_content[:2000] + "..." if len(section_content) > 2000 else section_content)
            
            # Parse courses from the section
            courses_data = self.parse_courses_from_section(section_content)
            
            if not courses_data:
                self.stdout.write(self.style.WARNING("⚠️  No courses found in the section"))
                return
            
            self.stdout.write(f"📚 Found {len(courses_data)} courses to process")
            
            if dry_run:
                self.stdout.write("🔍 DRY RUN - No courses will be created")
                for course_data in courses_data:
                    self.stdout.write(f"  Would create: {course_data['code']} - {course_data['name']} ({course_data['credits']} credits)")
                return
            
            # Clear existing sample courses for New Curriculum
            existing_courses = Course.objects.filter(curriculum=new_curriculum)
            if existing_courses.exists():
                self.stdout.write(f"🗑️  Removing {existing_courses.count()} existing sample courses...")
                existing_courses.delete()
            
            # Create courses
            created_count = 0
            for course_data in courses_data:
                try:
                    course = Course.objects.create(
                        code=course_data['code'],
                        name=course_data['name'],
                        curriculum=new_curriculum,
                        teacher=default_teacher,
                        credits=course_data['credits'],
                        is_theory=course_data.get('is_theory', True),
                        is_lab=course_data.get('is_lab', False),
                        course_type=course_data.get('course_type', 'CORE'),
                        # Set CA distribution based on course type
                        ca_attendance_weight=10,
                        ca_assignment_weight=20,
                        ca_quiz_weight=20,
                        ca_midterm_weight=50,
                        lab_ca_attendance_weight=10,
                        lab_ca_assignment_weight=30,
                        lab_ca_practical_weight=60,
                    )
                    created_count += 1
                    self.stdout.write(f"✅ Created: {course.code} - {course.name} ({course.credits} credits)")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"❌ Error creating {course_data['code']}: {str(e)}"))
            
            self.stdout.write(self.style.SUCCESS(f"🎉 Successfully created {created_count} courses from PDF"))
            
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"❌ PDF file not found: {pdf_path}"))
            self.stdout.write("Please ensure the PDF file exists in the new_curriculum folder")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error processing PDF: {str(e)}"))

    def parse_courses_from_section(self, section_content):
        """Parse course information from the section content"""
        courses_data = []
        
        # Look for course patterns in the PDF format
        lines = section_content.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Debug: print lines that might contain courses
            if re.search(r'\d{4}\s*-\d{3}', line):
                print(f"DEBUG: Found potential course line: {line}")
            
            # Look for course code patterns (4 digits - 3 digits)
            course_code_match = re.search(r'(\d{4}\s*-\d{3})', line)
            if course_code_match:
                print(f"DEBUG: Processing line: {line}")
                
                # Extract course code, title, and credits using regex
                # Pattern: "0231 -101 Communicative English 3.0"
                course_pattern = r'(\d{4}\s*-\d{3})\s+(.+?)\s+(\d+\.?\d*)\s*$'
                match = re.search(course_pattern, line)
                
                if match:
                    code = match.group(1).replace(' ', '')
                    name = match.group(2).strip()
                    credits = float(match.group(3))
                    
                    print(f"DEBUG: Extracted - Code: {code}, Name: {name}, Credits: {credits}")
                    
                    # Determine if it's a lab course
                    is_lab = 'Lab' in name or 'lab' in name
                    is_theory = not is_lab
                    
                    # Determine course type based on code prefix
                    if code.startswith('0231') or code.startswith('0232'):  # English courses
                        course_type = 'GENERAL'
                    elif code.startswith('0222') or code.startswith('0223'):  # Arts/Humanities
                        course_type = 'GENERAL'
                    elif code.startswith('0311'):  # Economics
                        course_type = 'GENERAL'
                    elif code.startswith('0413'):  # Business/Management
                        course_type = 'CORE'
                    elif code.startswith('0533'):  # Physics
                        course_type = 'CORE'
                    elif code.startswith('0633'):  # Mathematics
                        course_type = 'CORE'
                    elif code.startswith('0733'):  # CSE courses
                        course_type = 'CORE'
                    else:
                        course_type = 'CORE'
                    
                    courses_data.append({
                        'code': code,
                        'name': name,
                        'credits': int(credits),
                        'is_theory': is_theory,
                        'is_lab': is_lab,
                        'course_type': course_type
                    })
        
        print(f"DEBUG: Found {len(courses_data)} courses")
        return courses_data
