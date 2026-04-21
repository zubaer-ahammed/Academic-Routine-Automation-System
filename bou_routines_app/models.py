from django.conf import settings
from django.db import models

DAYS = [
    ("Friday", "Friday"),
    ("Saturday", "Saturday")
]

class Centre(models.Model):
    """
    Represents study centres (DRC Centre, DUET Centre, etc.)
    """
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, help_text="Centre name (e.g., 'DRC Centre', 'DUET Centre')")
    code = models.CharField(max_length=20, unique=True, help_text="Short code for centre (e.g., 'DRC', 'DUET')")
    description = models.TextField(blank=True, null=True, help_text="Description of the centre")
    is_active = models.BooleanField(default=True, help_text="Whether this centre is currently active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = "Centre"
        verbose_name_plural = "Centres"
    
    def __str__(self):
        return f"{self.name} ({self.code})"

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
    
    # Theory Course CA Distribution (default values for old curriculum)
    theory_ca_attendance_weight = models.PositiveIntegerField(default=5, help_text="Theory CA weight for attendance (%)")
    theory_ca_assignment_weight = models.PositiveIntegerField(default=10, help_text="Theory CA weight for assignments (%)")
    theory_ca_quiz_weight = models.PositiveIntegerField(default=15, help_text="Theory CA weight for quizzes (%)")
    theory_ca_midterm_weight = models.PositiveIntegerField(default=0, help_text="Theory CA weight for midterm (%)")
    
    # Lab Course CA Distribution (default values for old curriculum)
    lab_ca_attendance_weight = models.PositiveIntegerField(default=10, help_text="Lab CA weight for attendance (%)")
    lab_ca_assignment_weight = models.PositiveIntegerField(default=10, help_text="Lab CA weight for assignments (%)")
    lab_ca_practical_weight = models.PositiveIntegerField(default=10, help_text="Lab CA weight for practical exams (%)")
    lab_ca_quiz_weight = models.PositiveIntegerField(default=10, help_text="Lab CA weight for quizzes (%)")
    
    # Project Work Distribution
    project_supervisor_weight = models.PositiveIntegerField(default=30, help_text="Project supervisor weight (%)")
    project_evaluation_weight = models.PositiveIntegerField(default=40, help_text="Project evaluation weight (%)")
    project_presentation_weight = models.PositiveIntegerField(default=30, help_text="Project presentation weight (%)")
    
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
    centre = models.ForeignKey('Centre', on_delete=models.PROTECT, help_text="Centre this teacher belongs to (required - a teacher can teach at one centre only)")
    
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


class ProgramCoordinator(models.Model):
    """
    Program Coordinator information - links a teacher with their coordinator details
    """
    id = models.AutoField(primary_key=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, help_text="Teacher who is the program coordinator")
    designation = models.CharField(max_length=100, blank=True, null=True, help_text="Primary designation (e.g., 'Professor and Program Coordinator')")
    secondary_designation = models.CharField(max_length=100, blank=True, null=True, help_text="Secondary designation (e.g., 'School of Science and Technology')")
    phone = models.CharField(max_length=30, blank=True, null=True, help_text="Contact phone number")
    email = models.EmailField(blank=True, null=True, help_text="Contact email address")
    centre = models.ForeignKey('Centre', on_delete=models.PROTECT, help_text="Centre this coordinator belongs to (required)")
    is_active = models.BooleanField(default=True, help_text="Whether this coordinator is currently active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['centre', 'teacher__name']
        verbose_name = "Program Coordinator"
        verbose_name_plural = "Program Coordinators"
    
    def __str__(self):
        return f"{self.teacher.name} - {self.centre.name}"
    
    @property
    def name(self):
        """Return the teacher's name for convenience"""
        return self.teacher.name if self.teacher else ""

class Semester(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=10)
    order = models.IntegerField(default=0, help_text="Display order for semester dropdown")
    semester_full_name = models.CharField(max_length=100, blank=True, null=True)
    term = models.CharField(max_length=50, blank=True, null=True)
    session = models.CharField(max_length=50, blank=True, null=True)
    program_coordinator = models.ForeignKey('ProgramCoordinator', on_delete=models.SET_NULL, null=True, blank=True, help_text="Program Coordinator for this semester")
    lunch_break_start = models.TimeField(null=True, blank=True)
    lunch_break_end = models.TimeField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    holidays = models.TextField(null=True, blank=True, help_text="Comma-separated list of holiday dates (YYYY-MM-DD)")
    makeup_dates = models.TextField(null=True, blank=True, help_text="Comma-separated list of makeup/extra class dates (YYYY-MM-DD)")
    mid_term_exam_dates = models.TextField(null=True, blank=True, help_text="Comma-separated list of mid-term exam dates (YYYY-MM-DD). Only used for new curriculum.")
    theory_class_duration_minutes = models.PositiveIntegerField(default=60, help_text="Duration of theory classes in minutes (default: 60)")
    lab_class_duration_minutes = models.PositiveIntegerField(default=90, help_text="Duration of lab classes in minutes (default: 90)")
    teacher_short_name_newline = models.BooleanField(default=True, help_text="Show teacher's short name on a new line in PDF routine table (otherwise, show on same line as course code)")
    hide_teacher_name_in_pdf = models.BooleanField(default=False, help_text="Hide teacher's name in PDF routine")
    
    # Curriculum association
    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE, null=True, blank=True, help_text="Curriculum this semester follows")

    class Meta:
        ordering = ['curriculum', 'order', 'name']
        unique_together = [['name', 'curriculum']]  # Same semester name can exist in different curricula and centres
    
    def __str__(self):
        curriculum_suffix = f" ({self.curriculum.code})" if self.curriculum else ""
        return f"{self.name}{curriculum_suffix}"

class Course(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, default="")
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
    
    @property
    def effective_ca_attendance_weight(self):
        """Get theory CA attendance weight from curriculum or course"""
        if self.curriculum:
            return self.curriculum.theory_ca_attendance_weight
        return self.ca_attendance_weight
    
    @property
    def effective_ca_assignment_weight(self):
        """Get theory CA assignment weight from curriculum or course"""
        if self.curriculum:
            return self.curriculum.theory_ca_assignment_weight
        return self.ca_assignment_weight
    
    @property
    def effective_ca_quiz_weight(self):
        """Get theory CA quiz weight from curriculum or course"""
        if self.curriculum:
            return self.curriculum.theory_ca_quiz_weight
        return self.ca_quiz_weight
    
    @property
    def effective_ca_midterm_weight(self):
        """Get theory CA midterm weight from curriculum or course"""
        if self.curriculum:
            return self.curriculum.theory_ca_midterm_weight
        return self.ca_midterm_weight
    
    @property
    def effective_lab_ca_attendance_weight(self):
        """Get lab CA attendance weight from curriculum or course"""
        if self.curriculum:
            return self.curriculum.lab_ca_attendance_weight
        return self.lab_ca_attendance_weight
    
    @property
    def effective_lab_ca_assignment_weight(self):
        """Get lab CA assignment weight from curriculum or course"""
        if self.curriculum:
            return self.curriculum.lab_ca_assignment_weight
        return self.lab_ca_assignment_weight
    
    @property
    def effective_lab_ca_practical_weight(self):
        """Get lab CA practical weight from curriculum or course"""
        if self.curriculum:
            return self.curriculum.lab_ca_practical_weight
        return self.lab_ca_practical_weight
    
    @property
    def effective_lab_ca_quiz_weight(self):
        """Get lab CA quiz weight from curriculum"""
        if self.curriculum:
            return self.curriculum.lab_ca_quiz_weight
        return 0  # Course model doesn't have this field
    
    @property
    def effective_project_supervisor_weight(self):
        """Get project supervisor weight from curriculum"""
        if self.curriculum:
            return self.curriculum.project_supervisor_weight
        return 0
    
    @property
    def effective_project_evaluation_weight(self):
        """Get project evaluation weight from curriculum"""
        if self.curriculum:
            return self.curriculum.project_evaluation_weight
        return 0
    
    @property
    def effective_project_presentation_weight(self):
        """Get project presentation weight from curriculum"""
        if self.curriculum:
            return self.curriculum.project_presentation_weight
        return 0
    
    def clean(self):
        """Validate that a course cannot be both lab and theory, and handle project work"""
        from django.core.exceptions import ValidationError
        
        # Project work courses don't need is_lab or is_theory set
        if self.course_type == 'PROJECT':
            # Project work courses can have both False
            return
        
        if self.is_lab and self.is_theory:
            raise ValidationError({
                'is_lab': 'A course cannot be both a lab course and a theory course. Please select only one.',
                'is_theory': 'A course cannot be both a lab course and a theory course. Please select only one.',
            })
        
        if not self.is_lab and not self.is_theory:
            raise ValidationError({
                'is_lab': 'A course must be either a lab course, theory course, or project work. Please select one.',
                'is_theory': 'A course must be either a lab course, theory course, or project work. Please select one.',
            })
    
    def save(self, *args, **kwargs):
        """Override save to call clean()"""
        self.full_clean()
        super().save(*args, **kwargs)
    
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

class SemesterCentreCoordinator(models.Model):
    """
    Links a Program Coordinator to a specific Semester and Centre.
    This allows different coordinators for different study centres within the same semester.
    """
    id = models.AutoField(primary_key=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, help_text="Semester this coordinator is assigned to")
    centre = models.ForeignKey('Centre', on_delete=models.PROTECT, help_text="Study Centre this coordinator is assigned to")
    program_coordinator = models.ForeignKey('ProgramCoordinator', on_delete=models.CASCADE, help_text="Program Coordinator for this semester/centre")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('semester', 'centre')
        ordering = ['semester', 'centre']
        verbose_name = "Semester Centre Coordinator"
        verbose_name_plural = "Semester Centre Coordinators"
    
    def __str__(self):
        return f"{self.semester.name} - {self.centre.name} - {self.program_coordinator.teacher.name}"

class SemesterCourse(models.Model):
    id = models.AutoField(primary_key=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    centre = models.ForeignKey('Centre', on_delete=models.PROTECT, help_text="Study Centre this course is offered in for this semester (required)")
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, 
                                help_text="Teacher for this course in this specific semester/centre.")
    # Final exam: three evaluators for this semester/course/centre offering (canonical source)
    final_exam_evaluator1 = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='semester_courses_as_final_exam_evaluator1',
        help_text="First examiner (e.g. DRC) for final exam marking",
    )
    final_exam_evaluator2 = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='semester_courses_as_final_exam_evaluator2',
        help_text="Second examiner (e.g. DUET) for final exam marking",
    )
    final_exam_evaluator3 = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='semester_courses_as_final_exam_evaluator3',
        help_text="Third examiner if required (large T1/T2 discrepancy)",
    )
    # Attendance-only schedule override (does NOT affect routine/calendar generation)
    attendance_midterm_override_dates = models.TextField(
        blank=True,
        null=True,
        help_text="Attendance-only mid-term exam dates override (comma-separated YYYY-MM-DD). Used only to adjust Attendance table date columns.",
    )
    number_of_classes = models.PositiveIntegerField(default=1)  # Default to 1 class

    class Meta:
        unique_together = ('semester', 'course', 'centre')

    def __str__(self):
        return f"{self.semester.name} - {self.course.code} ({self.centre.code})"
    
    @property
    def effective_teacher(self):
        """Returns the teacher assigned to this semester course"""
        return self.teacher

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
        Get the teacher from the SemesterCourse for this semester and course
        Note: There may be multiple SemesterCourse objects for different centres,
        so we use filter().first() to get the first one
        """
        try:
            semester_course = SemesterCourse.objects.filter(
                semester=self.semester, 
                course=self.course
            ).first()
            return semester_course.teacher if semester_course else None
        except Exception:
            return None

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
        Get the teacher from the SemesterCourse for this semester and course
        Note: There may be multiple SemesterCourse objects for different centres,
        so we use filter().first() to get the first one
        """
        try:
            semester_course = SemesterCourse.objects.filter(
                semester=self.semester, 
                course=self.course
            ).first()
            return semester_course.teacher if semester_course else None
        except Exception:
            return None
    
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
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]
    
    id = models.CharField(max_length=20, primary_key=True, help_text="Student ID")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    semesters = models.ManyToManyField(Semester, help_text="Semesters this student is enrolled in")
    session = models.CharField(max_length=20, help_text="Academic session (e.g., 2020-21)")
    roll_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    centre = models.ForeignKey('Centre', on_delete=models.SET_NULL, null=True, blank=True, help_text="Centre this student belongs to")
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True, help_text="Student's gender")
    date_of_birth = models.DateField(blank=True, null=True, help_text="Date of birth (format: d-m-y)")
    father_name = models.CharField(max_length=100, blank=True, null=True, help_text="Father's name")
    mother_name = models.CharField(max_length=100, blank=True, null=True, help_text="Mother's name")
    
    def __str__(self):
        return f"{self.id} - {self.name}"
    
    @property
    def username(self):
        return self.user.username if self.user else ""
    
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
    
    # Class Test fields (for old curriculum - best of two is counted)
    first_class_test_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="First Class Test mark (for old curriculum)")
    second_class_test_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Second Class Test mark (for old curriculum)")
    class_test_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Best Class Test mark (auto-calculated, best of first and second)")
    midterm_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Midterm mark (for new curriculum)")
    
    # Lab course CA components
    # Lab Assignment/Presentation fields (3 assignments + average)
    first_lab_assignment_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="First Lab Assignment/Report mark")
    second_lab_assignment_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Second Lab Assignment/Report mark")
    third_lab_assignment_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Third Lab Assignment/Report mark")
    lab_assignment_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Average Lab Assignment mark (auto-calculated)")
    lab_practical_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Lab practical mark")
    
    # Project Work CA components
    project_supervisor_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Project supervisor mark")
    project_evaluation_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Project evaluation mark")
    project_presentation_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Project presentation mark")
    
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
        """Calculate attendance mark based on simple percentage calculation"""
        # Get total classes from SemesterCourse (same as attendance table)
        # Use filter().first() instead of get() since there may be multiple SemesterCourse
        # objects for the same semester/course but different centres
        try:
            semester_course = SemesterCourse.objects.filter(
                semester=self.semester,
                course=self.course
            ).first()
            if semester_course:
                total_classes = semester_course.number_of_classes
            else:
                total_classes = 1  # Default to 1 if no SemesterCourse found
        except Exception:
            total_classes = 1  # Default to 1 if error occurs
        
        # Get simple count of attended days (without filtering by NewRoutine)
        attended_days = Attendance.objects.filter(
            student=self.student,
            course=self.course,
            semester=self.semester,
            is_present=True
        ).count()
        
        if total_classes > 0:
            # Simple percentage calculation: attendance_weight * (attended_days / total_classes)
            attendance_weight = self.course.effective_ca_attendance_weight if not self.course.is_lab else self.course.effective_lab_ca_attendance_weight
            return (attended_days / total_classes) * attendance_weight
        return 0
    
    def calculate_assignment_mark(self):
        """Calculate average assignment mark from the three assignments"""
        total = self.first_assignment_mark + self.second_assignment_mark + self.third_assignment_mark
        if total > 0:
            return round(total / 3, 2)
        return 0
    
    def calculate_lab_assignment_mark(self):
        """Calculate average lab assignment mark from the three lab assignments"""
        total = self.first_lab_assignment_mark + self.second_lab_assignment_mark + self.third_lab_assignment_mark
        if total > 0:
            return round(total / 3, 2)
        return 0
    
    def calculate_class_test_mark(self):
        """Calculate best class test mark (best of first and second)"""
        first = float(self.first_class_test_mark or 0)
        second = float(self.second_class_test_mark or 0)
        return max(first, second)
    
    def calculate_total_ca_mark(self):
        """Calculate total CA mark based on course type"""
        if self.course.course_type == 'PROJECT':
            # Project Work: supervisor + evaluation + presentation
            return (
                self.project_supervisor_mark +
                self.project_evaluation_mark +
                self.project_presentation_mark
            )
        elif self.course.is_lab:
            # Lab course: attendance + lab assignment + lab practical
            return (
                self.attendance_mark +
                self.lab_assignment_mark +
                self.lab_practical_mark
            )
        else:
            # Theory course: attendance + assignment + (class_test for old curriculum OR midterm for new curriculum)
            # Determine which to use based on semester's curriculum
            exam_mark = 0
            if self.semester and self.semester.curriculum:
                # Check if it's old curriculum (code='OLD')
                if self.semester.curriculum.code == 'OLD':
                    # Use class test mark (best of first and second)
                    exam_mark = float(self.class_test_mark or 0)
                else:
                    # Use midterm mark for new curriculum
                    exam_mark = float(self.midterm_mark or 0)
            else:
                # Default to midterm if curriculum is not set
                exam_mark = float(self.midterm_mark or 0)
            
            # Convert to float for calculation, then return as float
            # The save() method will convert to Decimal
            attendance = float(self.attendance_mark or 0)
            assignment = float(self.assignment_mark or 0)
            exam = float(exam_mark or 0)
            return attendance + assignment + exam
    
    def save(self, *args, **kwargs):
        from decimal import Decimal

        def _to_decimal(val):
            if val is None:
                return Decimal('0')
            if isinstance(val, Decimal):
                return val
            # Handles float/int/str safely
            return Decimal(str(val))

        # Normalize numeric fields (POST assigns floats; calculations expect Decimals)
        self.first_assignment_mark = _to_decimal(self.first_assignment_mark)
        self.second_assignment_mark = _to_decimal(self.second_assignment_mark)
        self.third_assignment_mark = _to_decimal(self.third_assignment_mark)
        self.midterm_mark = _to_decimal(self.midterm_mark)
        self.first_class_test_mark = _to_decimal(self.first_class_test_mark)
        self.second_class_test_mark = _to_decimal(self.second_class_test_mark)

        self.first_lab_assignment_mark = _to_decimal(self.first_lab_assignment_mark)
        self.second_lab_assignment_mark = _to_decimal(self.second_lab_assignment_mark)
        self.third_lab_assignment_mark = _to_decimal(self.third_lab_assignment_mark)
        self.lab_practical_mark = _to_decimal(self.lab_practical_mark)

        self.project_supervisor_mark = _to_decimal(self.project_supervisor_mark)
        self.project_evaluation_mark = _to_decimal(self.project_evaluation_mark)
        self.project_presentation_mark = _to_decimal(self.project_presentation_mark)
        
        # Auto-calculate attendance mark
        attendance_mark_float = self.calculate_attendance_mark()
        self.attendance_mark = Decimal(str(attendance_mark_float))
        
        # Auto-calculate assignment mark (average of three assignments)
        assignment_mark_float = self.calculate_assignment_mark()
        self.assignment_mark = Decimal(str(assignment_mark_float))
        
        # Auto-calculate lab assignment mark (average of three lab assignments)
        lab_assignment_mark_float = self.calculate_lab_assignment_mark()
        self.lab_assignment_mark = Decimal(str(lab_assignment_mark_float))
        
        # Auto-calculate class test mark (best of first and second)
        class_test_mark_float = self.calculate_class_test_mark()
        self.class_test_mark = Decimal(str(class_test_mark_float))
        
        # Set midterm to 0 for old curriculum, class tests to 0 for new curriculum
        if self.semester and self.semester.curriculum:
            if self.semester.curriculum.code == 'OLD':
                # Old curriculum: set midterm to 0 (use class tests)
                self.midterm_mark = Decimal('0')
            else:
                # New curriculum: set class tests to 0 (use midterm)
                self.first_class_test_mark = Decimal('0')
                self.second_class_test_mark = Decimal('0')
                self.class_test_mark = Decimal('0')
        
        # Calculate total CA mark
        total_ca_mark_float = self.calculate_total_ca_mark()
        self.total_ca_mark = Decimal(str(total_ca_mark_float))
        
        super().save(*args, **kwargs)


class FinalExamMark(models.Model):
    """
    Semester Final Examination marks for students
    Theory course: 70 marks (7 question sets, max 5 can be entered, max 14 per set)
    Lab course: 60 marks (single field)
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    
    # Theory course: 7 question sets (each max 14 marks, total max 70)
    # Teacher 1 evaluation
    teacher1_q1 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 1 - Question Set 1 (max 14)")
    teacher1_q2 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 1 - Question Set 2 (max 14)")
    teacher1_q3 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 1 - Question Set 3 (max 14)")
    teacher1_q4 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 1 - Question Set 4 (max 14)")
    teacher1_q5 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 1 - Question Set 5 (max 14)")
    teacher1_q6 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 1 - Question Set 6 (max 14)")
    teacher1_q7 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 1 - Question Set 7 (max 14)")
    teacher1_total = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Teacher 1 total (auto-calculated, max 70)")
    
    # Teacher 2 evaluation
    teacher2_q1 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 2 - Question Set 1 (max 14)")
    teacher2_q2 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 2 - Question Set 2 (max 14)")
    teacher2_q3 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 2 - Question Set 3 (max 14)")
    teacher2_q4 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 2 - Question Set 4 (max 14)")
    teacher2_q5 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 2 - Question Set 5 (max 14)")
    teacher2_q6 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 2 - Question Set 6 (max 14)")
    teacher2_q7 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 2 - Question Set 7 (max 14)")
    teacher2_total = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Teacher 2 total (auto-calculated, max 70)")
    
    # Teacher 3 evaluation (only if difference > 20% or > 14 marks)
    teacher3_q1 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 3 - Question Set 1 (max 14)")
    teacher3_q2 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 3 - Question Set 2 (max 14)")
    teacher3_q3 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 3 - Question Set 3 (max 14)")
    teacher3_q4 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 3 - Question Set 4 (max 14)")
    teacher3_q5 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 3 - Question Set 5 (max 14)")
    teacher3_q6 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 3 - Question Set 6 (max 14)")
    teacher3_q7 = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Teacher 3 - Question Set 7 (max 14)")
    teacher3_total = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Teacher 3 total (auto-calculated, max 70)")
    
    # Lab course: single field (max 60)
    lab_final_exam_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True, help_text="Lab course final exam mark (max 60)")
    
    # Final total (for theory: average of teachers, for lab: single value)
    final_exam_total = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Final exam total mark")
    
    # Metadata
    teacher1_evaluator = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='final_exam_marks_teacher1', null=True, blank=True)
    teacher2_evaluator = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='final_exam_marks_teacher2', null=True, blank=True)
    teacher3_evaluator = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='final_exam_marks_teacher3', null=True, blank=True)
    marked_by = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='final_exam_marks_marked_by')
    marked_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    
    # Flag to indicate if there's a discrepancy requiring third teacher
    requires_third_teacher = models.BooleanField(default=False, help_text="True if difference between teacher1 and teacher2 > 20% or > 14 marks")

    # Student absent for the final exam — UI shows "AB"; numeric totals are cleared
    exam_absent = models.BooleanField(default=False)

    class Meta:
        unique_together = ('student', 'course', 'semester')
        ordering = ['student__id']
    
    def __str__(self):
        return f"{self.student.id} - {self.course.code} - Final: {self.final_exam_total}"
    
    def clear_numeric_exam_fields(self):
        """Clear all entered marks (used when marking the student absent)."""
        for i in range(1, 8):
            setattr(self, f'teacher1_q{i}', None)
            setattr(self, f'teacher2_q{i}', None)
            setattr(self, f'teacher3_q{i}', None)
        self.lab_final_exam_mark = None

    def calculate_teacher_total(self, teacher_num):
        """Calculate total for a specific teacher (1, 2, or 3)"""
        from decimal import Decimal
        if getattr(self, 'exam_absent', False):
            return Decimal('0')
        total = Decimal('0')
        for i in range(1, 8):
            field_name = f'teacher{teacher_num}_q{i}'
            value = getattr(self, field_name, None)
            if value:
                total += Decimal(str(value))
        return total
    
    def check_discrepancy(self):
        """Check if difference between teacher1 and teacher2 is > 20% or > 14 marks"""
        if getattr(self, 'exam_absent', False):
            return False
        if not self.course.is_lab:
            teacher1_total = float(self.teacher1_total or 0)
            teacher2_total = float(self.teacher2_total or 0)
            
            # Calculate difference
            difference = abs(teacher1_total - teacher2_total)
            
            # Check if difference > 14 marks (20% of 70)
            if difference > 14:
                return True
            
            # Check if difference > 20% of the average
            if teacher1_total > 0 or teacher2_total > 0:
                avg = (teacher1_total + teacher2_total) / 2
                if avg > 0:
                    percentage_diff = (difference / avg) * 100
                    if percentage_diff > 20:
                        return True
        return False
    
    @property
    def discrepancy_reason(self):
        """Get the reason for discrepancy as a formatted string"""
        if getattr(self, 'exam_absent', False):
            return "Absent (AB)"
        if not self.course.is_lab:
            teacher1_total = float(self.teacher1_total or 0)
            teacher2_total = float(self.teacher2_total or 0)
            
            if teacher1_total == 0 and teacher2_total == 0:
                return "No marks entered yet"
            
            difference = abs(teacher1_total - teacher2_total)
            avg = (teacher1_total + teacher2_total) / 2 if (teacher1_total > 0 or teacher2_total > 0) else 0
            
            reasons = []
            if difference > 14:
                reasons.append(f"Difference of {difference:.2f} marks exceeds 14 marks (20% of 70)")
            
            if avg > 0:
                percentage_diff = (difference / avg) * 100
                if percentage_diff > 20:
                    reasons.append(f"Difference of {percentage_diff:.1f}% exceeds 20% threshold")
            
            if reasons:
                return " | ".join(reasons)
            else:
                return "No discrepancy detected"
        
        return "N/A (Lab course)"
    
    def calculate_final_total(self):
        """Calculate final exam total based on course type"""
        from decimal import Decimal

        if getattr(self, 'exam_absent', False):
            return Decimal('0')
        
        if self.course.is_lab:
            # Lab course: use single field
            return Decimal(str(self.lab_final_exam_mark or 0))
        else:
            # Theory course logic:
            # No discrepancy → Total = avg(Teacher 1, Teacher 2)
            # Discrepancy exists + Teacher 3 evaluated → Total = avg(Teacher 1, Teacher 2, Teacher 3)
            # Discrepancy exists + Teacher 3 not evaluated → Total = avg(Teacher 1, Teacher 2)
            
            teacher1_total = float(self.teacher1_total or 0)
            teacher2_total = float(self.teacher2_total or 0)
            teacher3_total = float(self.teacher3_total or 0)
            
            # Collect totals from teachers who have evaluated (total > 0)
            evaluated_totals = []
            if teacher1_total > 0:
                evaluated_totals.append(teacher1_total)
            if teacher2_total > 0:
                evaluated_totals.append(teacher2_total)
            
            # If discrepancy exists and Teacher 3 has evaluated, include Teacher 3 in average
            if self.requires_third_teacher and teacher3_total > 0:
                evaluated_totals.append(teacher3_total)
            
            # Calculate average of all evaluated teachers
            if evaluated_totals:
                average = sum(evaluated_totals) / len(evaluated_totals)
                return Decimal(str(average))
            
            return Decimal('0')
    
    def save(self, *args, **kwargs):
        from decimal import Decimal

        if getattr(self, 'exam_absent', False):
            self.requires_third_teacher = False
        
        if not self.course.is_lab:
            # Theory course: calculate totals for each teacher
            self.teacher1_total = Decimal(str(self.calculate_teacher_total(1)))
            self.teacher2_total = Decimal(str(self.calculate_teacher_total(2)))
            self.teacher3_total = Decimal(str(self.calculate_teacher_total(3)))
            
            # Check for discrepancy
            self.requires_third_teacher = self.check_discrepancy()
        
        # Calculate final total
        self.final_exam_total = self.calculate_final_total()
        
        super().save(*args, **kwargs)
