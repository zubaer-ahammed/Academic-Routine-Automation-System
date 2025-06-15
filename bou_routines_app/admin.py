from django.contrib import admin
from .models import Teacher, Semester, Course, CurrentRoutine, NewRoutine, SemesterCourse

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
    list_display = ('id', 'name')
    search_fields = ('name',)
    ordering = ('id',)

@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'semester_full_name', 'lunch_break_start', 'lunch_break_end', 'start_date')
    search_fields = ('name',)
    ordering = ('id',)

admin.site.register([NewRoutine])
