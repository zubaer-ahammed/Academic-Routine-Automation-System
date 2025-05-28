from django.db import models

DAYS = [
    ("Friday", "Friday"),
    ("Saturday", "Saturday")
]

class Teacher(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Semester(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=10)
    lunch_break_start = models.TimeField(null=True, blank=True)
    lunch_break_end = models.TimeField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    holidays = models.TextField(null=True, blank=True, help_text="Comma-separated list of holiday dates (YYYY-MM-DD)")

    def __str__(self):
        return self.name

class Course(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100, default="")
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)

    def __str__(self):
        return self.code

class SemesterCourse(models.Model):
    id = models.AutoField(primary_key=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
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

