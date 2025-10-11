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
    code = models.CharField(max_length=20, unique=True, help_text="Short code for curriculum (e.g., 'CURR', 'NEW2024')")
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
    name = models.CharField(max_length=100, unique=True)
    short_name = models.CharField(max_length=50, blank=True, null=True, unique=True)

    def __str__(self):
        return self.name

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
