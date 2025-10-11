from django.contrib import admin
from .models import Teacher, Semester, Course, CurrentRoutine, NewRoutine, SemesterCourse, LoginLog, Curriculum

@admin.register(CurrentRoutine)
class CurrentRoutineAdmin(admin.ModelAdmin):
    list_display = ('id', 'semester', 'course', 'get_teacher', 'start_time', 'end_time', 'day')
    list_filter = ('semester', 'day', 'course__teacher')
    search_fields = ('course__code', 'course__teacher__name', 'semester__name')
    ordering = ('semester', 'day', 'start_time')
    
    def get_teacher(self, obj):
        return obj.teacher.name
    get_teacher.short_description = 'Teacher'
    get_teacher.admin_order_field = 'course__teacher'

@admin.register(Curriculum)
class CurriculumAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code', 'is_active', 'effective_from', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'code', 'description')
    ordering = ('-is_active', 'name')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'description', 'is_active')
        }),
        ('Timeline', {
            'fields': ('effective_from',)
        }),
    )

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'teacher', 'curriculum', 'credits', 'course_type', 'is_theory', 'is_lab')
    list_filter = ('teacher', 'curriculum', 'course_type', 'is_theory', 'is_lab')
    search_fields = ('code', 'name', 'teacher__name', 'curriculum__name')
    ordering = ('curriculum', 'code',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'teacher', 'curriculum', 'course_type')
        }),
        ('Course Details', {
            'fields': ('credits', 'is_theory', 'is_lab', 'prerequisite_courses')
        }),
        ('Theory CA Distribution', {
            'fields': ('ca_attendance_weight', 'ca_assignment_weight', 'ca_quiz_weight', 'ca_midterm_weight'),
            'classes': ('collapse',)
        }),
        ('Lab CA Distribution', {
            'fields': ('lab_ca_attendance_weight', 'lab_ca_assignment_weight', 'lab_ca_practical_weight'),
            'classes': ('collapse',)
        }),
    )

@admin.register(SemesterCourse)
class SemesterCourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'semester', 'course', 'number_of_classes')
    list_filter = ('semester',)
    search_fields = ('semester__name', 'course__code')
    ordering = ('semester', 'course__code')

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'short_name')
    search_fields = ('name', 'short_name')
    ordering = ('name',)

@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'semester_full_name', 'curriculum', 'theory_class_duration_minutes', 'lab_class_duration_minutes', 'lunch_break_start', 'lunch_break_end', 'start_date')
    list_filter = ('curriculum',)
    search_fields = ('name', 'curriculum__name')
    ordering = ('name',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'order', 'semester_full_name', 'term', 'session', 'study_center', 'curriculum')
        }),
        ('Contact Information', {
            'fields': ('contact_person', 'contact_person_designation', 'contact_person_phone', 'contact_person_email')
        }),
        ('Class Durations', {
            'fields': ('theory_class_duration_minutes', 'lab_class_duration_minutes'),
            'description': 'Duration in minutes for theory and lab classes. Used for calculating class counts during routine generation.'
        }),
        ('Schedule Settings', {
            'fields': ('lunch_break_start', 'lunch_break_end', 'start_date', 'end_date')
        }),
        ('Dates', {
            'fields': ('holidays', 'makeup_dates'),
            'description': 'Comma-separated dates in YYYY-MM-DD format'
        }),
    )

@admin.register(NewRoutine)
class NewRoutineAdmin(admin.ModelAdmin):
    list_display = ('id', 'semester', 'course', 'class_date', 'day', 'start_time', 'end_time', 'get_teacher')
    list_filter = ('semester', 'day', 'course__teacher', 'class_date')
    search_fields = ('course__code', 'course__name', 'course__teacher__name', 'semester__name', 'day', 'class_date')
    ordering = ('semester', 'class_date', 'start_time')
    date_hierarchy = 'class_date'
    
    def get_teacher(self, obj):
        return obj.teacher.name
    get_teacher.short_description = 'Teacher'
    get_teacher.admin_order_field = 'course__teacher'

@admin.register(LoginLog)
class LoginLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'login_time', 'ip_address', 'user_agent')
    search_fields = ('user__username', 'ip_address', 'user_agent')
    list_filter = ('user',)
