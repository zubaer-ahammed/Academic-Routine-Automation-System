from django.contrib import admin
from .models import Teacher, Semester, Course, CurrentRoutine, NewRoutine, SemesterCourse, LoginLog

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

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'teacher')
    list_filter = ('teacher',)
    search_fields = ('code', 'name', 'teacher__name')
    ordering = ('code',)

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
    list_display = ('id', 'name', 'semester_full_name', 'theory_class_duration_minutes', 'lab_class_duration_minutes', 'lunch_break_start', 'lunch_break_end', 'start_date')
    search_fields = ('name',)
    ordering = ('name',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'order', 'semester_full_name', 'term', 'session', 'study_center')
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
