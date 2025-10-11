from django.conf import settings
from django.db import models

DAYS = [
    ("Friday", "Friday"),
    ("Saturday", "Saturday")
]

class Curriculum(models.Model):
    """
    Represents different curriculum versions (Current, New, etc.)
    """
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, help_text="Curriculum name (e.g., 'Current Curriculum', 'New Curriculum 2024')")
    code = models.CharField(max_length=20, unique=True, help_text="Short code for curriculum (e.g., 'OLD', 'NEW2024')")
    description = models.TextField(blank=True, null=True, help_text="Description of the curriculum")
    is_active = models.BooleanField(default=True, help_text="Whether this curriculum is currently active")
    effective_from = models.DateField(null=True, blank=True, help_text="Date from which this curriculum is effective")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_active', 'name']
        verbose_name = "Curriculum"
        verbose_name_plural = "Curricula"
    
    def __str__(self):
        return f"{self.name} ({self.code})"

class Teacher(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100, unique=True)
    short_name = models.CharField(max_length=50, blank=True, null=True, unique=True)
    address = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    join_date = models.DateField(null=True, blank=True)
    
    class Meta:
        permissions = [
            ("can_mark_attendance", "Can mark class attendance"),
            ("can_manage_ca", "Can manage continuous assessment"),
            ("can_manage_final_marks", "Can manage semester final marks"),
        ]

    def __str__(self):
        return self.name
    
    @property
    def email(self):
        return self.user.email if self.user else ""
    
    @property
    def username(self):
        return self.user.username if self.user else ""

class Semester(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=10)
    order = models.IntegerField(default=0, help_text="Display order for semester dropdown")
    semester_full_name = models.CharField(max_length=100, blank=True, null=True)
    term = models.CharField(max_length=50, blank=True, null=True)
    session = models.CharField(max_length=50, blank=True, null=True)
    study_center = models.CharField(max_length=100, blank=True, null=True)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    contact_person_designation = models.CharField(max_length=100, blank=True, null=True)
    contact_person_phone = models.CharField(max_length=30, blank=True, null=True)
    contact_person_email = models.EmailField(blank=True, null=True)
    lunch_break_start = models.TimeField(null=True, blank=True)
    lunch_break_end = models.TimeField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    holidays = models.TextField(null=True, blank=True, help_text="Comma-separated list of holiday dates (YYYY-MM-DD)")
    makeup_dates = models.TextField(null=True, blank=True, help_text="Comma-separated list of makeup/extra class dates (YYYY-MM-DD)")
    theory_class_duration_minutes = models.PositiveIntegerField(default=60, help_text="Duration of theory classes in minutes (default: 60)")
    lab_class_duration_minutes = models.PositiveIntegerField(default=90, help_text="Duration of lab classes in minutes (default: 90)")
    teacher_short_name_newline = models.BooleanField(default=True, help_text="Show teacher's short name on a new line in PDF routine table (otherwise, show on same line as course code)")
    
    # Curriculum association
    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE, null=True, blank=True, help_text="Curriculum this semester follows")

    class Meta:
        ordering = ['curriculum', 'order', 'name']
        unique_together = [['name', 'curriculum']]  # Same semester name can exist in different curricula
    
    def __str__(self):
        curriculum_suffix = f" ({self.curriculum.code})" if self.curriculum else ""
        return f"{self.name}{curriculum_suffix}"

class Course(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, default="")
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE, null=True, blank=True, help_text="Curriculum this course belongs to")
    
    # Curriculum-specific fields
    credits = models.PositiveIntegerField(default=3, help_text="Number of credits for this course")
    is_theory = models.BooleanField(default=True, help_text="Whether this is a theory course")
    is_lab = models.BooleanField(default=False, help_text="Whether this is a lab course")
    
    # CA (Continuous Assessment) mark distribution
    ca_attendance_weight = models.PositiveIntegerField(default=10, help_text="CA weight for attendance (%)")
    ca_assignment_weight = models.PositiveIntegerField(default=20, help_text="CA weight for assignments (%)")
    ca_quiz_weight = models.PositiveIntegerField(default=20, help_text="CA weight for quizzes (%)")
    ca_midterm_weight = models.PositiveIntegerField(default=50, help_text="CA weight for midterm (%)")
    
    # Lab-specific CA distribution (if applicable)
    lab_ca_attendance_weight = models.PositiveIntegerField(default=10, help_text="Lab CA weight for attendance (%)")
    lab_ca_assignment_weight = models.PositiveIntegerField(default=30, help_text="Lab CA weight for assignments (%)")
    lab_ca_practical_weight = models.PositiveIntegerField(default=60, help_text="Lab CA weight for practical exams (%)")
    
    # Additional curriculum information
    prerequisite_courses = models.ManyToManyField('self', blank=True, symmetrical=False, help_text="Prerequisite courses")
    course_type = models.CharField(max_length=20, choices=[
        ('CORE', 'Core'),
        ('ELECTIVE', 'Elective'),
        ('GENERAL', 'General'),
        ('PROJECT', 'Project'),
    ], default='CORE', help_text="Type of course")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['curriculum', 'code']
        unique_together = [['code', 'curriculum'], ['name', 'curriculum']]  # Same course code and name can exist in different curricula
    
    def __str__(self):
        curriculum_suffix = f" ({self.curriculum.code})" if self.curriculum else ""
        return f"{self.code}{curriculum_suffix}"
    
    def get_ca_distribution(self):
        """Get CA distribution based on course type"""
        if self.is_lab:
            return {
                'attendance': self.lab_ca_attendance_weight,
                'assignment': self.lab_ca_assignment_weight,
                'practical': self.lab_ca_practical_weight,
            }
        else:
            return {
                'attendance': self.ca_attendance_weight,
                'assignment': self.ca_assignment_weight,
                'quiz': self.ca_quiz_weight,
                'midterm': self.ca_midterm_weight,
            }

class SemesterCourse(models.Model):
    id = models.AutoField(primary_key=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    number_of_classes = models.PositiveIntegerField(default=1)  # Default to 1 class
    # Removed teacher field as it's already in the Course model

    class Meta:
        unique_together = ('semester', 'course')

    def __str__(self):
        return f"{self.semester.name} - {self.course.code}"

class CurrentRoutine(models.Model):
    id = models.AutoField(primary_key=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    # Removed teacher field as it's already accessible through course.teacher
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    day = models.CharField(max_length=10, choices=DAYS)
    
    def __str__(self):
        return f"{self.course.code} {self.day} {self.start_time}-{self.end_time}"
    
    @property
    def teacher(self):
        """
        Get the teacher from the associated course
        This maintains backward compatibility with existing code
        """
        return self.course.teacher

class NewRoutine(models.Model):
    id = models.AutoField(primary_key=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    # Removed teacher field as it's already accessible through course.teacher
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    day = models.CharField(max_length=10, choices=DAYS)
    class_date = models.DateField()
    
    def __str__(self):
        return f"{self.course.code} {self.day} {self.class_date.strftime('%Y-%m-%d')} {self.start_time}-{self.end_time}"
    
    @property
    def teacher(self):
        """
        Get the teacher from the associated course
        This maintains backward compatibility with existing code
        """
        return self.course.teacher
    
    class Meta:
        ordering = ['class_date', 'start_time']

class LoginLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    login_time = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-login_time']

class Student(models.Model):
    id = models.CharField(max_length=20, primary_key=True, help_text="Student ID")
    name = models.CharField(max_length=100)
    semesters = models.ManyToManyField(Semester, help_text="Semesters this student is enrolled in")
    session = models.CharField(max_length=20, help_text="Academic session (e.g., 2020-21)")
    roll_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    
    def __str__(self):
        return f"{self.id} - {self.name}"
    
    class Meta:
        ordering = ['id']


class Attendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    attendance_date = models.DateField()
    is_present = models.BooleanField(default=False)
    marked_by = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    marked_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = ('student', 'course', 'semester', 'attendance_date')
        ordering = ['attendance_date', 'student__id']
    
    def __str__(self):
        status = "Present" if self.is_present else "Absent"
        return f"{self.student.id} - {self.course.code} - {self.attendance_date} - {status}"


class CAMark(models.Model):
    """
    Continuous Assessment marks for students
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    
    # Theory course CA components
    attendance_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Attendance mark (auto-calculated)")
    
    # Assignment/Presentation fields (3 assignments + average)
    first_assignment_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="First Assignment/Presentation mark")
    second_assignment_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Second Assignment/Presentation mark")
    third_assignment_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Third Assignment/Presentation mark")
    assignment_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Average Assignment mark (auto-calculated)")
    
    quiz_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Quiz mark")
    midterm_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Midterm mark")
    
    # Lab course CA components
    lab_assignment_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Lab assignment mark")
    lab_practical_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Lab practical mark")
    
    # Total CA mark (calculated)
    total_ca_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Total CA mark")
    
    # Metadata
    marked_by = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    marked_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = ('student', 'course', 'semester')
        ordering = ['student__id']
    
    def __str__(self):
        return f"{self.student.id} - {self.course.code} - CA: {self.total_ca_mark}"
    
    def calculate_attendance_mark(self):
        """Calculate attendance mark based on BOU official attendance rules with duration-based class counting"""
        # Get total classes from SemesterCourse relationship
        try:
            semester_course = SemesterCourse.objects.get(
                semester=self.semester,
                course=self.course
            )
            total_classes = semester_course.number_of_classes
        except SemesterCourse.DoesNotExist:
            total_classes = 1  # Default to 1 if no SemesterCourse found
        
        # Get standard class duration from semester settings
        if self.course.is_lab:
            standard_duration_minutes = self.semester.lab_class_duration_minutes
        else:
            standard_duration_minutes = self.semester.theory_class_duration_minutes
        
        # Calculate attended classes with duration consideration
        attended_classes_fractional = 0.0
        
        # Get all attendance records for this student, course, and semester
        # Only count records that have corresponding routine entries
        attendance_records = Attendance.objects.filter(
            student=self.student,
            course=self.course,
            semester=self.semester,
            is_present=True
        )
        
        # Filter to only include attendance records that have corresponding routines
        valid_attendance_records = []
        for attendance_record in attendance_records:
            try:
                NewRoutine.objects.get(
                    semester=self.semester,
                    course=self.course,
                    class_date=attendance_record.attendance_date
                )
                valid_attendance_records.append(attendance_record)
            except NewRoutine.DoesNotExist:
                # Skip attendance records that don't have corresponding routines
                continue
        
        for attendance_record in valid_attendance_records:
            # Find the routine for this specific date and course
            try:
                routine = NewRoutine.objects.get(
                    semester=self.semester,
                    course=self.course,
                    class_date=attendance_record.attendance_date
                )
                
                # Calculate actual class duration in minutes
                if routine.start_time and routine.end_time:
                    start_time = routine.start_time
                    end_time = routine.end_time
                    
                    # Convert time to minutes for calculation
                    start_minutes = start_time.hour * 60 + start_time.minute
                    end_minutes = end_time.hour * 60 + end_time.minute
                    actual_duration_minutes = end_minutes - start_minutes
                    
                    # Calculate fractional class count
                    if standard_duration_minutes > 0:
                        fractional_classes = actual_duration_minutes / standard_duration_minutes
                        attended_classes_fractional += fractional_classes
                    else:
                        # Fallback to 1 class if standard duration is 0
                        attended_classes_fractional += 1.0
                else:
                    # Fallback to 1 class if no time information
                    attended_classes_fractional += 1.0
                    
            except NewRoutine.DoesNotExist:
                # If no routine found for this date, count as 1 class (fallback)
                attended_classes_fractional += 1.0
        
        if total_classes > 0:
            attendance_percentage = (attended_classes_fractional / total_classes) * 100
            
            # Apply BOU official attendance mark distribution
            if attendance_percentage >= 90:
                mark_percentage = 100
            elif attendance_percentage >= 85:
                mark_percentage = 90
            elif attendance_percentage >= 80:
                mark_percentage = 80
            elif attendance_percentage >= 75:
                mark_percentage = 70
            elif attendance_percentage >= 70:
                mark_percentage = 60
            elif attendance_percentage >= 65:
                mark_percentage = 50
            elif attendance_percentage >= 60:
                mark_percentage = 40
            else:
                mark_percentage = 0
            
            # Convert to actual mark out of the attendance weight
            attendance_weight = self.course.ca_attendance_weight if not self.course.is_lab else self.course.lab_ca_attendance_weight
            return (mark_percentage / 100) * attendance_weight
        return 0
    
    def calculate_assignment_mark(self):
        """Calculate average assignment mark from the three assignments"""
        total = self.first_assignment_mark + self.second_assignment_mark + self.third_assignment_mark
        if total > 0:
            return round(total / 3, 2)
        return 0
    
    def calculate_total_ca_mark(self):
        """Calculate total CA mark based on course type"""
        if self.course.is_lab:
            # Lab course: attendance + lab assignment + lab practical
            return (
                self.attendance_mark +
                self.lab_assignment_mark +
                self.lab_practical_mark
            )
        else:
            # Theory course: attendance + assignment + quiz + midterm
            return (
                self.attendance_mark +
                self.assignment_mark +
                self.quiz_mark +
                self.midterm_mark
            )
    
    def save(self, *args, **kwargs):
        # Auto-calculate attendance mark
        self.attendance_mark = self.calculate_attendance_mark()
        
        # Auto-calculate assignment mark (average of three assignments)
        self.assignment_mark = self.calculate_assignment_mark()
        
        # Calculate total CA mark
        self.total_ca_mark = self.calculate_total_ca_mark()
        
        super().save(*args, **kwargs)
