from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Teacher, Semester, Course, CurrentRoutine, NewRoutine, SemesterCourse, LoginLog, Student, Attendance, Curriculum, CAMark

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

class TeacherInline(admin.StackedInline):
    model = Teacher
    can_delete = False
    verbose_name_plural = 'Teacher Profile'
    fields = ('name', 'short_name', 'address', 'phone', 'designation', 'department', 'join_date')

class TeacherUserAdmin(UserAdmin):
    inlines = (TeacherInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_teacher_name')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    
    def get_teacher_name(self, obj):
        try:
            return obj.teacher.name
        except Teacher.DoesNotExist:
            return "No Teacher Profile"
    get_teacher_name.short_description = 'Teacher Name'
    
    def get_inline_instances(self, request, obj=None):
        if not obj:
            return list()
        return super(TeacherUserAdmin, self).get_inline_instances(request, obj)

# Unregister the default User admin and register our custom one
admin.site.unregister(User)
admin.site.register(User, TeacherUserAdmin)

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('name', 'username', 'email', 'short_name', 'designation', 'department', 'phone')
    search_fields = ('name', 'short_name', 'user__username', 'user__email', 'designation')
    list_filter = ('department', 'designation')
    ordering = ('name',)
    
    fields = ('user', 'name', 'short_name', 'address', 'phone', 'designation', 'department', 'join_date')
    readonly_fields = ('user',)
    
    def username(self, obj):
        return obj.user.username if obj.user else ""
    username.short_description = 'Username'
    
    def email(self, obj):
        return obj.user.email if obj.user else ""
    email.short_description = 'Email'

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

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'get_semesters', 'session', 'roll_number', 'email')
    list_filter = ('semesters', 'session')
    search_fields = ('id', 'name', 'roll_number', 'email')
    ordering = ('id',)
    filter_horizontal = ('semesters',)
    
    def get_semesters(self, obj):
        return ", ".join([semester.name for semester in obj.semesters.all()])
    get_semesters.short_description = 'Semesters'


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'semester', 'attendance_date', 'is_present', 'marked_by', 'marked_at')
    list_filter = ('semester', 'course', 'attendance_date', 'is_present', 'marked_by')
    search_fields = ('student__id', 'student__name', 'course__code', 'course__name')
    ordering = ('-attendance_date', 'student__id')
    date_hierarchy = 'attendance_date'
    
    readonly_fields = ('marked_at',)
    
    fieldsets = (
        ('Attendance Information', {
            'fields': ('student', 'course', 'semester', 'attendance_date', 'is_present')
        }),
        ('Record Details', {
            'fields': ('marked_by', 'marked_at', 'notes'),
            'classes': ('collapse',)
        }),
    )

@admin.register(CAMark)
class CAMarkAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'semester', 'total_ca_mark', 'marked_by', 'updated_at')
    list_filter = ('semester', 'course', 'marked_by', 'updated_at')
    search_fields = ('student__id', 'student__name', 'course__code', 'course__name')
    ordering = ('semester', 'course', 'student__id')
    readonly_fields = ('attendance_mark', 'total_ca_mark', 'marked_at', 'updated_at')
    
    fieldsets = (
        ('Student & Course', {
            'fields': ('student', 'course', 'semester')
        }),
        ('Theory Course Marks', {
            'fields': ('attendance_mark', 'assignment_mark', 'quiz_mark', 'midterm_mark'),
            'description': 'Marks for theory courses'
        }),
        ('Lab Course Marks', {
            'fields': ('lab_assignment_mark', 'lab_practical_mark'),
            'description': 'Marks for lab courses'
        }),
        ('Total', {
            'fields': ('total_ca_mark',)
        }),
        ('Record Details', {
            'fields': ('marked_by', 'marked_at', 'updated_at', 'notes'),
            'classes': ('collapse',)
        }),
    )
