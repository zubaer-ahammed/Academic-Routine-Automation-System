from django.conf import settings
from django.db import models

DAYS = [
    ("Friday", "Friday"),
    ("Saturday", "Saturday")
]

class Teacher(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    short_name = models.CharField(max_length=50, blank=True, null=True, unique=True)

    def __str__(self):
        return self.name

class Semester(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=10, unique=True)
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

    def __str__(self):
        return self.name

class Course(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, default="", unique=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)

    def __str__(self):
        return self.code

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
