from django.shortcuts import render, redirect
from .models import CurrentRoutine, Teacher, TimeSlot, Semester, Course, NewRoutine, SemesterCourse
from .forms import RoutineForm
from datetime import datetime, timedelta
from collections import defaultdict



def routine_entry(request):
    routines = CurrentRoutine.objects.select_related("teacher", "time_slot", "course")
    if request.method == "POST":
        form = RoutineForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('routine-entry')
    else:
        form = RoutineForm()
    return render(request, 'bou_routines_app/routine_entry.html', {
        'form': form,
        'routines': routines
    })

def generate_routine(request):
    semesters = Semester.objects.all()
    courses = Course.objects.all()
    teachers = Teacher.objects.all()

    generated_routines = []

    if request.method == "POST":
        # Fake logic — replace with actual generation logic
        selected_semester_id = request.POST.get("semester")
        date_range = request.POST.get("date_range")
        duration = request.POST.get("duration")

        # You can build real routines here; this is just an example
        generated_routines = CurrentRoutine.objects.filter(semester_id=selected_semester_id)

    return render(request, "bou_routines_app/generate_routine.html", {
        "semesters": semesters,
        "courses": courses,
        "teachers": teachers,
        "generated_routines": generated_routines
    })

def create_semester(request):
    if request.method == "POST":
        semester_name = request.POST.get("semester_name")
        selected_courses = request.POST.getlist("courses")
        selected_teachers = request.POST.getlist("teachers")

        # Create semester
        semester = Semester.objects.create(name=semester_name)

        # Create semester courses
        for course_id, teacher_id in zip(selected_courses, selected_teachers):
            course = Course.objects.get(id=course_id)
            teacher = Teacher.objects.get(id=teacher_id)
            SemesterCourse.objects.create(
                semester=semester,
                course=course,
                teacher=teacher
            )

        return redirect('create_semester')

    semesters = Semester.objects.all()
    courses = Course.objects.all()
    teachers = Teacher.objects.all()
    return render(request, "bou_routines_app/create_semester.html", {
        "semesters": semesters,
        "courses": courses,
        "teachers": teachers
    })
