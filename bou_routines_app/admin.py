from django.contrib import admin
from .models import Teacher, Semester, TimeSlot, Course, CurrentRoutine, NewRoutine, SemesterCourse

@admin.register(CurrentRoutine)
class CurrentRoutineAdmin(admin.ModelAdmin):
    list_display = ('id', 'semester', 'course', 'teacher', 'time_slot', 'day')
    list_filter = ('semester', 'day')
    search_fields = ('course__code', 'teacher__name', 'semester__name')
    ordering = ('semester', 'day', 'time_slot')

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'teacher')
    list_filter = ('teacher',)
    search_fields = ('code', 'name', 'teacher__name')
    ordering = ('code',)

@admin.register(SemesterCourse)
class SemesterCourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'semester', 'course', 'teacher')
    list_filter = ('semester', 'teacher')
    search_fields = ('semester__name', 'course__code', 'teacher__name')
    ordering = ('semester', 'course__code')

admin.site.register([Teacher, Semester, TimeSlot, NewRoutine])
