from django.contrib import admin
from .models import Teacher, Semester, TimeSlot, Course, CurrentRoutine, NewRoutine

admin.site.register([Teacher, Semester, TimeSlot, Course, CurrentRoutine, NewRoutine])
