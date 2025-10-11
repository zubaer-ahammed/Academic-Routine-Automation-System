from django.shortcuts import render, redirect
from .models import CurrentRoutine, Teacher, Semester, Course, NewRoutine, SemesterCourse, Student, Attendance, Curriculum, CAMark
from .forms import RoutineForm, TeacherRegistrationForm
from datetime import datetime, timedelta, date
from collections import defaultdict
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, FileResponse
import io
import calendar
import xlsxwriter
import re
import math
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from django.urls import reverse
from django.utils.http import urlencode
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.utils import timezone


@login_required
def routine_entry(request):
    # Updated select_related to include course__teacher since teacher is now accessed through course
    routines = CurrentRoutine.objects.select_related("course", "course__teacher", "semester")
    if request.method == "POST":
        form = RoutineForm(request.POST)
        if form.is_valid():
            # Get the cleaned data from the form
            cleaned_data = form.cleaned_data
            course = cleaned_data.get('course')
            semester = cleaned_data.get('semester')
            
            # Check if a routine with the same course already exists
            existing_routine = CurrentRoutine.objects.filter(course=course, semester=semester).first()
            
            if existing_routine:
                # Update the existing routine with the new data
                # No need to set teacher as it comes from the course
                existing_routine.start_time = cleaned_data.get('start_time')
                existing_routine.end_time = cleaned_data.get('end_time')
                existing_routine.day = cleaned_data.get('day')
                existing_routine.save()
                messages.success(request, f'Updated routine for {course.code}')
            else:
                # Create a new routine but set the teacher from the course
                routine = form.save(commit=False)
                # No need to set teacher as it comes from the course
                routine.save()
                messages.success(request, f'Created new routine for {course.code}')
            
            return redirect('generate-routine')
    else:
        form = RoutineForm()
    return render(request, 'bou_routines_app/routine_entry.html', {
        'form': form,
        'routines': routines
    })

def time_overlap(start1, end1, start2, end2):
    # Two time ranges overlap if:
    # 1. The start time of one range is less than the end time of the other range
    # 2. AND the start time of the other range is less than the end time of the first range
    # This correctly handles cases where ranges share exactly the same start or end time
    return start1 < end2 and start2 < end1

@login_required
def generate_routine(request):
    # Get all curricula
    curricula = Curriculum.objects.filter(is_active=True).order_by('name')
    
    # Get selected curriculum from request
    selected_curriculum_id = request.GET.get('curriculum') or request.POST.get('curriculum')
    selected_curriculum = None
    
    if selected_curriculum_id:
        try:
            # Convert to integer to ensure type consistency
            selected_curriculum_id = int(selected_curriculum_id)
            selected_curriculum = Curriculum.objects.get(id=selected_curriculum_id)
        except (Curriculum.DoesNotExist, ValueError):
            selected_curriculum = None
            selected_curriculum_id = None
    
    # If no curriculum selected, use the Old Curriculum by default
    if not selected_curriculum and curricula.exists():
        try:
            selected_curriculum = Curriculum.objects.get(code='OLD')
            selected_curriculum_id = selected_curriculum.id
        except Curriculum.DoesNotExist:
            selected_curriculum = curricula.first()
            selected_curriculum_id = selected_curriculum.id if selected_curriculum else None
    
    # Filter semesters and courses by selected curriculum
    if selected_curriculum:
        semesters = Semester.objects.filter(curriculum=selected_curriculum).order_by('name')
        courses = Course.objects.select_related('teacher').filter(curriculum=selected_curriculum).order_by('code')
    else:
        semesters = Semester.objects.all().order_by('name')
        courses = Course.objects.select_related('teacher').all().order_by('code')
    
    teachers = Teacher.objects.all()

    # Pre-select semester if provided in query params (GET)
    selected_semester_id = request.GET.get('semester') or request.POST.get('semester')
    if selected_semester_id:
        try:
            selected_semester_id = int(selected_semester_id)
        except (ValueError, TypeError):
            selected_semester_id = None
    selected_semester = None
    teacher_short_name_newline = True  # Default
    
    # If semester is provided but no curriculum, determine curriculum from semester
    if selected_semester_id and not selected_curriculum:
        try:
            selected_semester = Semester.objects.get(id=selected_semester_id)
            if selected_semester.curriculum:
                selected_curriculum = selected_semester.curriculum
                selected_curriculum_id = selected_curriculum.id
                # Re-filter semesters and courses by the determined curriculum
                semesters = Semester.objects.filter(curriculum=selected_curriculum).order_by('name')
                courses = Course.objects.select_related('teacher').filter(curriculum=selected_curriculum).order_by('code')
        except Semester.DoesNotExist:
            selected_semester = None

    # Check if we have any semester courses at all
    if not SemesterCourse.objects.exists():
        messages.warning(request, "No courses have been assigned to any semester yet. Please add courses to a semester first via the 'Semester Courses' menu.")

    generated_routines = []
    overlap_conflicts = []
    form_rows = []

    # On POST, save the teacher_short_name_newline value to the Semester
    if request.method == "POST" and request.POST.get("semester"):
        try:
            selected_semester = Semester.objects.get(id=request.POST.get("semester"))
            # Save the checkbox value to the Semester
            tsn_newline = request.POST.get("teacher_short_name_newline") == "1"
            selected_semester.teacher_short_name_newline = tsn_newline
            selected_semester.save()
            teacher_short_name_newline = tsn_newline
        except Semester.DoesNotExist:
            selected_semester = None
    elif selected_semester_id:
        try:
            selected_semester = Semester.objects.get(id=selected_semester_id)
            teacher_short_name_newline = selected_semester.teacher_short_name_newline
        except Semester.DoesNotExist:
            selected_semester = None

    # Load existing generated routines if semester is selected via GET
    if selected_semester_id and request.method == "GET":
        try:
            selected_semester = Semester.objects.get(id=selected_semester_id)
            existing_routines = NewRoutine.objects.filter(semester=selected_semester).select_related('course', 'course__teacher').order_by('class_date', 'start_time')
            
            if existing_routines.exists():
                for routine in existing_routines:
                    generated_routines.append({
                        'id': routine.id,
                        'course_id': routine.course.id,
                        'date': routine.class_date,
                        'day': routine.day,
                        'course_code': routine.course.code,
                        'course_name': routine.course.name,
                        'teacher': routine.course.teacher.name,
                        'start_time': routine.start_time.strftime('%H:%M'),
                        'end_time': routine.end_time.strftime('%H:%M')
                    })
                
                # Sort generated routines by date and time for display
                generated_routines.sort(key=lambda x: (x['date'], x['start_time']))

                # Build the routine table structure for existing routines
                if generated_routines:
                    unique_dates = []
                    seen_dates = set()
                    for routine in generated_routines:
                        date_str = routine['date'].strftime('%Y-%m-%d')
                        if date_str not in seen_dates:
                            seen_dates.add(date_str)
                            unique_dates.append((routine['date'], routine['day']))

                    # Add makeup dates to unique_dates for existing routines display
                    if selected_semester.makeup_dates:
                        makeup_dates = [
                            datetime.strptime(date.strip(), "%Y-%m-%d").date()
                            for date in selected_semester.makeup_dates.split(',')
                            if date.strip()
                        ]
                        for makeup_date in makeup_dates:
                            day_name = makeup_date.strftime('%A')
                            # Only add Friday and Saturday makeup dates
                            if day_name in ['Friday', 'Saturday']:
                                date_str = makeup_date.strftime('%Y-%m-%d')
                                # Check if this date is not already in unique_dates
                                date_already_exists = any(date[0].strftime('%Y-%m-%d') == date_str for date in unique_dates)
                                if not date_already_exists:
                                    unique_dates.append((makeup_date, day_name))

                    unique_dates.sort(key=lambda x: x[0])

                    # Build merged time slot structure
                    time_boundaries = set()
                    for routine in generated_routines:
                        time_boundaries.add(routine['start_time'])
                        time_boundaries.add(routine['end_time'])
                    if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
                        time_boundaries.add(selected_semester.lunch_break_start.strftime('%H:%M'))
                        time_boundaries.add(selected_semester.lunch_break_end.strftime('%H:%M'))
                    time_boundaries = sorted(time_boundaries)

                    # Build contiguous time slots
                    all_time_slot_labels = []
                    for i in range(len(time_boundaries)-1):
                        all_time_slot_labels.append(f"{time_boundaries[i]} - {time_boundaries[i+1]}")

                    # Filter only slots that are actually used
                    used_slots = set()
                    for routine in generated_routines:
                        r_start = routine['start_time']
                        r_end = routine['end_time']
                        for i in range(len(time_boundaries)-1):
                            slot_start = time_boundaries[i]
                            slot_end = time_boundaries[i+1]
                            if (slot_start >= r_start and slot_end <= r_end):
                                used_slots.add((slot_start, slot_end))
                    
                    # Add lunch break as used slot if present
                    if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
                        lb_start = selected_semester.lunch_break_start.strftime('%H:%M')
                        lb_end = selected_semester.lunch_break_end.strftime('%H:%M')
                        for i in range(len(time_boundaries)-1):
                            slot_start = time_boundaries[i]
                            slot_end = time_boundaries[i+1]
                            if (slot_start >= lb_start and slot_end <= lb_end):
                                used_slots.add((slot_start, slot_end))
                    
                    # Filter time slot labels
                    time_slot_labels = []
                    slot_ranges = []
                    for i in range(len(time_boundaries)-1):
                        slot_start = time_boundaries[i]
                        slot_end = time_boundaries[i+1]
                        if (slot_start, slot_end) in used_slots:
                            label = f"{slot_start} - {slot_end}"
                            time_slot_labels.append(label)
                            slot_ranges.append((slot_start, slot_end, label))

                    # Build routine table rows
                    from collections import defaultdict
                    routines_by_date = defaultdict(list)
                    for routine in generated_routines:
                        routines_by_date[(routine['date'], routine['day'])].append(routine)

                    # Add lunch break as a pseudo-routine if present
                    lunch_break = None
                    if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
                        lunch_break = {
                            'start_time': selected_semester.lunch_break_start.strftime('%H:%M'),
                            'end_time': selected_semester.lunch_break_end.strftime('%H:%M'),
                            'is_lunch_break': True
                        }

                    routine_table_rows = []
                    for date, day in unique_dates:
                        row_cells = []
                        slot_idx = 0
                        routines = routines_by_date.get((date, day), [])
                        routines_for_row = routines.copy()
                        if lunch_break:
                            routines_for_row.append({
                                'start_time': lunch_break['start_time'],
                                'end_time': lunch_break['end_time'],
                                'is_lunch_break': True
                            })
                        routines_for_row.sort(key=lambda r: r['start_time'])
                        
                        while slot_idx < len(slot_ranges):
                            slot_start, slot_end, slot_label = slot_ranges[slot_idx]
                            found = False
                            for r in routines_for_row:
                                r_start = r['start_time']
                                r_end = r['end_time']
                                if r_start == slot_start:
                                    colspan = 0
                                    for j in range(slot_idx, len(slot_ranges)):
                                        s2, e2, _ = slot_ranges[j]
                                        if e2 <= r_end:
                                            colspan += 1
                                        else:
                                            break
                                    if r.get('is_lunch_break'):
                                        content = 'BREAK'
                                        cell = {'content': content, 'colspan': colspan, 'is_lunch_break': True}
                                    else:
                                        content = {
                                            'course_code': r['course_code'],
                                            'teacher': 'Supervisor' if r['course_code'] == 'CSE4246' else r['teacher'],
                                        }
                                        if 'id' in r and 'course_id' in r:
                                            content['routine_id'] = r['id']
                                            content['course_id'] = r['course_id']
                                        cell = {'content': content, 'colspan': colspan, 'is_lunch_break': False}
                                    row_cells.append(cell)
                                    slot_idx += colspan
                                    found = True
                                    break
                            if not found:
                                row_cells.append({'content': '', 'colspan': 1, 'is_lunch_break': False})
                                slot_idx += 1
                        routine_table_rows.append({'date': date, 'day': day, 'cells': row_cells})

                    # Prepare data for the calendar view
                    time_slots = []
                    time_slot_set = set()
                    for routine in generated_routines:
                        time_slot = f"{routine['start_time']} - {routine['end_time']}"
                        if time_slot not in time_slot_set:
                            time_slot_set.add(time_slot)
                            time_slots.append(time_slot)

                    # Sort time slots chronologically
                    time_slots.sort(key=lambda x: x.split(' - ')[0])

                    # Add lunch break if configured
                    if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
                        lunch_break_slot = f"{selected_semester.lunch_break_start.strftime('%H:%M')} - {selected_semester.lunch_break_end.strftime('%H:%M')}"
                        if lunch_break_slot not in time_slot_set:
                            time_slots.append(lunch_break_slot)
                            time_slots.sort(key=lambda x: x.split(' - ')[0])

                    # Format routines for the calendar view with time slot info
                    calendar_routines = []
                    for routine in generated_routines:
                        time_slot = f"{routine['start_time']} - {routine['end_time']}"

                        calendar_routines.append({
                            'date': routine['date'],
                            'day': routine['day'],
                            'course_code': routine['course_code'],
                            'course_name': routine['course_name'],
                            'teacher': routine['teacher'],
                            'start_time': routine['start_time'],
                            'end_time': routine['end_time'],
                            'time_slot': time_slot,
                            'is_lunch_break': False
                        })

        except Semester.DoesNotExist:
            pass
    
    # Initialize variables for when no routines are found
    if not generated_routines:
        unique_dates = []
        time_slots = []
        calendar_routines = []
        lunch_break = None
        routine_table_rows = []
        time_slot_labels = []

    if request.method == "POST":
        save_only = request.POST.get("save_only") == "1"
        print("DEBUG save_only value:", request.POST.get("save_only"))
        selected_semester_id = request.POST.get("semester")
        date_range = request.POST.get("date_range")
        days = request.POST.getlist("day[]")
        start_times = request.POST.getlist("start_time[]")
        end_times = request.POST.getlist("end_time[]")
        course_codes = request.POST.getlist('course_code[]')
        lunch_break_start = request.POST.get('lunch_break_start')
        lunch_break_end = request.POST.get('lunch_break_end')
        form_rows = list(zip(course_codes, days, start_times, end_times))
        
        # Create a set to track unique conflicts
        unique_conflicts = set()
        
        # Always update the semester's lunch break if times are provided
        if selected_semester_id and lunch_break_start and lunch_break_end:
            try:
                selected_semester = Semester.objects.get(id=selected_semester_id)
                selected_semester.lunch_break_start = datetime.strptime(lunch_break_start, "%H:%M").time()
                selected_semester.lunch_break_end = datetime.strptime(lunch_break_end, "%H:%M").time()
                # Check if date_range is provided, parse and save to semester
                if date_range:
                    try:
                        start_date_str, end_date_str = date_range.split(' - ')
                        selected_semester.start_date = datetime.strptime(start_date_str, "%m/%d/%Y").date()
                        selected_semester.end_date = datetime.strptime(end_date_str, "%m/%d/%Y").date()
                    except Exception as e:
                        messages.error(request, f"Error parsing date range: {str(e)}")
                # Process and save government holidays
                govt_holidays = request.POST.get('govt_holiday_dates')
                if govt_holidays:
                    # Save comma-separated list of holiday dates directly
                    selected_semester.holidays = govt_holidays
                # Process and save makeup/extra class dates
                makeup_dates = request.POST.get('makeup_date_list')
                if makeup_dates:
                    # Save comma-separated list of makeup dates directly
                    selected_semester.makeup_dates = makeup_dates
                selected_semester.save()
                #messages.success(request, f"Updated lunch break for {selected_semester.name} to {lunch_break_start} - {lunch_break_end}")
            except Exception as e:
                messages.error(request, f"Error updating semester settings: {str(e)}")
        
        # Save class schedule rows (CurrentRoutine) for Save Changes as well
        for i in range(len(days)):
            day = days[i]
            start_time_str = start_times[i]
            end_time_str = end_times[i]
            course_id = course_codes[i]
            # Skip if any field is empty
            if not (course_id and day and start_time_str and end_time_str):
                continue
            try:
                course = Course.objects.get(id=course_id)
                start = datetime.strptime(start_time_str, "%H:%M").time()
                end = datetime.strptime(end_time_str, "%H:%M").time()
                # Update or create CurrentRoutine for this course/day/semester
                CurrentRoutine.objects.update_or_create(
                    semester=selected_semester,
                    course=course,
                    day=day,
                    defaults={
                        'start_time': start,
                        'end_time': end
                    }
                )
            except (Course.DoesNotExist, ValueError):
                continue
        
        # Delete CurrentRoutine entries for this semester that are not in the submitted form
        from django.db.models import Q
        submitted_pairs = set(
            (int(course_codes[i]), days[i])
            for i in range(len(days))
            if course_codes[i] and days[i] and start_times[i] and end_times[i]
        )
        q = Q()
        for course_id, day in submitted_pairs:
            q |= Q(course_id=course_id, day=day)
        if submitted_pairs:
            CurrentRoutine.objects.filter(semester=selected_semester).exclude(q).delete()
        else:
            # If no rows submitted, delete all for this semester
            CurrentRoutine.objects.filter(semester=selected_semester).delete()
        
        # EARLY RETURN IF SAVE ONLY
        if save_only:
            messages.success(request, "Semester info and class schedule saved successfully.")
            # Preserve both curriculum and semester parameters
            curriculum_param = f"&curriculum={selected_curriculum_id}" if selected_curriculum_id else ""
            return redirect(f"{reverse('generate-routine')}?semester={selected_semester_id}{curriculum_param}")
        
        # Check for lunch break overlaps (always enforced)
        try:
            selected_semester = Semester.objects.get(id=selected_semester_id)
            # Use the form-provided lunch break times if available, otherwise fall back to semester's lunch break
            if lunch_break_start and lunch_break_end:
                lunch_start = datetime.strptime(lunch_break_start, "%H:%M").time()
                lunch_end = datetime.strptime(lunch_break_end, "%H:%M").time()
            elif selected_semester.lunch_break_start and selected_semester.lunch_break_end:
                lunch_start = selected_semester.lunch_break_start
                lunch_end = selected_semester.lunch_break_end
            else:
                # No lunch break defined
                lunch_start = None
                lunch_end = None
            
            if lunch_start and lunch_end:
                for i in range(len(days)):
                    day = days[i]
                    start = datetime.strptime(start_times[i], "%H:%M").time()
                    end = datetime.strptime(end_times[i], "%H:%M").time()
                    
                    # Check if time slot overlaps with lunch break
                    if time_overlap(start, end, lunch_start, lunch_end):
                        conflict_key = f"lunch_break_{day}_{lunch_start}_{lunch_end}"
                        
                        if conflict_key not in unique_conflicts:
                            unique_conflicts.add(conflict_key)
                            overlap_conflicts.append({
                                "course": "Lunch Break",
                                "teacher": "All",
                                "day": day,
                                "start": lunch_start.strftime("%H:%M"),
                                "end": lunch_end.strftime("%H:%M"),
                            })
        except Semester.DoesNotExist:
            # Handle case when semester doesn't exist
            pass
            
        # Check for time slot overlaps between classes
        for i in range(len(days)):
            day = days[i]
            start = datetime.strptime(start_times[i], "%H:%M").time()
            end = datetime.strptime(end_times[i], "%H:%M").time()
            course_id = course_codes[i]
            
            # Get the teacher ID for this course
            try:
                course = Course.objects.get(id=course_id)
                teacher_id = course.teacher.id
                
                # Only check for routines with the same teacher, same day, and overlapping time
                # But exclude the course we're currently checking
                for routine in CurrentRoutine.objects.filter(day=day, course__teacher_id=teacher_id).exclude(course_id=course_id):
                    if time_overlap(start, end, routine.start_time, routine.end_time):
                        # Create a unique key for this conflict to avoid duplicates
                        conflict_key = f"{routine.course.code}_{routine.day}_{routine.start_time}_{routine.end_time}"
                        
                        if conflict_key not in unique_conflicts:
                            unique_conflicts.add(conflict_key)
                            overlap_conflicts.append({
                                "course": routine.course.code,
                                "teacher": routine.course.teacher.name,
                                "day": routine.day,
                                "start": routine.start_time.strftime("%H:%M"),
                                "end": routine.end_time.strftime("%H:%M"),
                            })
            except Course.DoesNotExist:
                # Skip if course doesn't exist
                continue
                
        if overlap_conflicts:
            messages.error(request, "Time conflicts detected. Please resolve all overlaps before generating a routine.")
            return render(request, "bou_routines_app/generate_routine.html", {
                "semesters": semesters,
                "courses": courses,
                "teachers": teachers,
                "generated_routines": generated_routines,
                "overlap_conflicts": overlap_conflicts,
                "form_rows": form_rows,
            })
        
        # No overlaps, continue with routine generation
        try:
            selected_semester = Semester.objects.get(id=selected_semester_id)
            
            # Parse date range
            if not date_range:
                return render(request, "bou_routines_app/generate_routine.html", {
                    "semesters": semesters,
                    "courses": courses,
                    "teachers": teachers,
                    "error": "Please provide a date range",
                })
            
            # Check if there are courses for this semester
            semester_courses = SemesterCourse.objects.filter(semester=selected_semester)
            if not semester_courses.exists():
                messages.warning(request, f"No courses found for semester {selected_semester.name}. Please add courses to this semester first.")
                return render(request, "bou_routines_app/generate_routine.html", {
                    "semesters": semesters,
                    "courses": courses,
                    "teachers": teachers,
                })
                
            start_date_str, end_date_str = date_range.split(' - ')
            start_date = datetime.strptime(start_date_str, "%m/%d/%Y").date()
            end_date = datetime.strptime(end_date_str, "%m/%d/%Y").date()
            
            # Update semester with the date range if it has changed
            if selected_semester.start_date != start_date or selected_semester.end_date != end_date:
                selected_semester.start_date = start_date
                selected_semester.end_date = end_date
                selected_semester.save()
            
            # Check if the date range includes at least one Friday or Saturday
            current_check = start_date
            has_target_day = False
            while current_check <= end_date:
                if current_check.strftime('%A') in ['Friday', 'Saturday']:
                    has_target_day = True
                    break
                current_check += timedelta(days=1)
                
            if not has_target_day:
                messages.warning(request, "The selected date range does not include any Friday or Saturday. Please select a date range that includes at least one Friday or Saturday.")
                return render(request, "bou_routines_app/generate_routine.html", {
                    "semesters": semesters,
                    "courses": courses,
                    "teachers": teachers,
                })
            
            # Clear any existing generated routines for this semester
            NewRoutine.objects.filter(semester=selected_semester).delete()
            # Also clear existing CurrentRoutine entries for this semester
            CurrentRoutine.objects.filter(semester=selected_semester).delete()
            
            # Generate day-by-day routines
            current_date = start_date
            
            # Add debugging logs to identify potential issues
            processed_days = []
            matched_days = []
            skipped_holidays = []

            # Check if we have at least one Friday and one Saturday in the form data
            has_friday = 'Friday' in days
            has_saturday = 'Saturday' in days
            
            if not (has_friday or has_saturday):
                messages.warning(request, "You must schedule at least one course for Friday or Saturday.")
                return render(request, "bou_routines_app/generate_routine.html", {
                    "semesters": semesters,
                    "courses": courses,
                    "teachers": teachers,
                })
            
            # Get holiday dates from the semester model
            holiday_dates = []
            if selected_semester.holidays:
                holiday_dates = [
                    datetime.strptime(date.strip(), "%Y-%m-%d").date()
                    for date in selected_semester.holidays.split(',')
                    if date.strip()
                ]

            # Get makeup dates from the semester model
            makeup_dates = []
            if selected_semester.makeup_dates:
                makeup_dates = [
                    datetime.strptime(date.strip(), "%Y-%m-%d").date()
                    for date in selected_semester.makeup_dates.split(',')
                    if date.strip()
                ]

            # --- CLASS COUNT LIMIT LOGIC ---
            # Build a map: course_id -> (allowed_classes, is_lab, slot_minutes)
            course_limits = {}
            for sc in semester_courses:
                is_lab = 'P' in sc.course.code
                slot_minutes = None
                for i in range(len(days)):
                    if str(course_codes[i]) == str(sc.course.id):
                        start_time_str = start_times[i]
                        end_time_str = end_times[i]
                        if start_time_str and end_time_str:
                            start = datetime.strptime(start_time_str, "%H:%M").time()
                            end = datetime.strptime(end_time_str, "%H:%M").time()
                            slot_minutes = (datetime.combine(datetime.min, end) - datetime.combine(datetime.min, start)).total_seconds() / 60
                            break
                course_limits[str(sc.course.id)] = {
                    'allowed': sc.number_of_classes,
                    'is_lab': is_lab,
                    'slot_minutes': slot_minutes,
                    'start_time': start_time_str if slot_minutes else None,
                    'end_time': end_time_str if slot_minutes else None,
                    'day': days[i] if slot_minutes else None,
                    'course': sc.course,
                }

            # Build a set of makeup/reserve dates
            makeup_dates_set = set(makeup_dates)
            # Build a set of holiday dates
            holiday_dates_set = set(holiday_dates)

            # For each course, build a list of all valid dates (Fridays/Saturdays, not in makeup_dates, not in holidays, not after end_date)
            for course_id, limit in course_limits.items():
                if not limit['slot_minutes']:
                    continue  # skip if no slot info
                # Determine class duration
                if limit['is_lab']:
                    class_duration = selected_semester.lab_class_duration_minutes
                else:
                    class_duration = selected_semester.theory_class_duration_minutes
                # Calculate how many sessions are needed (round up)
                sessions_needed = math.ceil(limit['allowed'] * class_duration / limit['slot_minutes'])
                # Build all valid dates for this course
                valid_dates = []
                current_date = start_date
                while current_date <= end_date:
                    if current_date in makeup_dates_set or current_date in holiday_dates_set:
                        current_date += timedelta(days=1)
                        continue
                    if current_date.strftime('%A') == limit['day']:
                        valid_dates.append(current_date)
                    current_date += timedelta(days=1)
                # Schedule up to sessions_needed or as many as possible
                sessions_scheduled = 0
                for d in valid_dates:
                    if sessions_scheduled >= sessions_needed:
                        break
                    NewRoutine.objects.create(
                        semester=selected_semester,
                        course=limit['course'],
                        start_time=datetime.strptime(limit['start_time'], "%H:%M").time(),
                        end_time=datetime.strptime(limit['end_time'], "%H:%M").time(),
                        day=limit['day'],
                        class_date=d
                    )
                    CurrentRoutine.objects.update_or_create(
                        semester=selected_semester,
                        course=limit['course'],
                        day=limit['day'],
                        defaults={
                            'start_time': datetime.strptime(limit['start_time'], "%H:%M").time(),
                            'end_time': datetime.strptime(limit['end_time'], "%H:%M").time()
                        }
                    )
                    generated_routines.append({
                        'id': None,
                        'course_id': limit['course'].id,
                        'date': d,
                        'day': limit['day'],
                        'course_code': limit['course'].code,
                        'course_name': limit['course'].name,
                        'teacher': limit['course'].teacher.name,
                        'start_time': limit['start_time'],
                        'end_time': limit['end_time']
                    })
                    sessions_scheduled += 1
                # If not enough valid dates, warn the user
                if sessions_scheduled < sessions_needed:
                    messages.warning(request, f"Only {sessions_scheduled} out of {sessions_needed} classes could be scheduled for {limit['course'].code} due to semester date constraints. Please add the remaining classes manually.")

            # Sort generated routines by date and time for display
            generated_routines.sort(key=lambda x: (x['date'], x['start_time']))

            # Ensure unique_dates is always defined
            if generated_routines:
                unique_dates = []
                seen_dates = set()
                for routine in generated_routines:
                    date_str = routine['date'].strftime('%Y-%m-%d')
                    if date_str not in seen_dates:
                        seen_dates.add(date_str)
                        unique_dates.append((routine['date'], routine['day']))
                unique_dates.sort(key=lambda x: x[0])
            else:
                unique_dates = []

            # Add makeup dates to unique_dates as blank rows (only date and day, no classes)
            if makeup_dates:
                for makeup_date in makeup_dates:
                    # Only add if the makeup date is within the date range
                    if start_date <= makeup_date <= end_date:
                        day_name = makeup_date.strftime('%A')
                        # Only add Friday and Saturday makeup dates
                        if day_name in ['Friday', 'Saturday']:
                            date_str = makeup_date.strftime('%Y-%m-%d')
                            # Check if this date is not already in unique_dates
                            date_already_exists = any(date[0].strftime('%Y-%m-%d') == date_str for date in unique_dates)
                            if not date_already_exists:
                                unique_dates.append((makeup_date, day_name))

                # Sort again after adding makeup dates
                unique_dates.sort(key=lambda x: x[0])

            # --- NEW: Build merged time slot structure ---
            # 1. Collect all unique time boundaries (start and end times)
            time_boundaries = set()
            for routine in generated_routines:
                time_boundaries.add(routine['start_time'])
                time_boundaries.add(routine['end_time'])
            if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
                time_boundaries.add(selected_semester.lunch_break_start.strftime('%H:%M'))
                time_boundaries.add(selected_semester.lunch_break_end.strftime('%H:%M'))
            # Convert to sorted list
            time_boundaries = sorted(time_boundaries)

            # 2. Build contiguous time slots (pairs of adjacent boundaries)
            all_time_slot_labels = []  # e.g., ['08:45 - 09:45', ...]
            for i in range(len(time_boundaries)-1):
                all_time_slot_labels.append(f"{time_boundaries[i]} - {time_boundaries[i+1]}")

            # 2.5. Filter only slots that are actually used by a class or lunch break
            # Build a set of (start, end) for all routines and lunch break
            used_slots = set()
            for routine in generated_routines:
                r_start = routine['start_time']
                r_end = routine['end_time']
                for i in range(len(time_boundaries)-1):
                    slot_start = time_boundaries[i]
                    slot_end = time_boundaries[i+1]
                    # If the slot is fully within the routine
                    if (slot_start >= r_start and slot_end <= r_end):
                        used_slots.add((slot_start, slot_end))
            # Add lunch break as used slot if present
            if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
                lb_start = selected_semester.lunch_break_start.strftime('%H:%M')
                lb_end = selected_semester.lunch_break_end.strftime('%H:%M')
                for i in range(len(time_boundaries)-1):
                    slot_start = time_boundaries[i]
                    slot_end = time_boundaries[i+1]
                    if (slot_start >= lb_start and slot_end <= lb_end):
                        used_slots.add((slot_start, slot_end))
            # Now, filter all_time_slot_labels to only those in used_slots
            time_slot_labels = []
            slot_ranges = []
            for i in range(len(time_boundaries)-1):
                slot_start = time_boundaries[i]
                slot_end = time_boundaries[i+1]
                if (slot_start, slot_end) in used_slots:
                    label = f"{slot_start} - {slot_end}"
                    time_slot_labels.append(label)
                    slot_ranges.append((slot_start, slot_end, label))

            # 3. For each date/day, build a row of cells (with content and colspan)
            from collections import defaultdict
            routines_by_date = defaultdict(list)
            for routine in generated_routines:
                routines_by_date[(routine['date'], routine['day'])].append(routine)

            # Add lunch break as a pseudo-routine if present
            lunch_break = None
            if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
                lunch_break = {
                    'start_time': selected_semester.lunch_break_start.strftime('%H:%M'),
                    'end_time': selected_semester.lunch_break_end.strftime('%H:%M'),
                    'is_lunch_break': True
                }

            routine_table_rows = []  # Each row: {'date':..., 'day':..., 'cells': [ {content, colspan, is_lunch_break}, ... ]}
            for date, day in unique_dates:
                row_cells = []
                slot_idx = 0
                # Use filtered slot_ranges
                # For this date, get all routines (by start/end)
                routines = routines_by_date.get((date, day), [])
                # Add lunch break as a pseudo-routine
                routines_for_row = routines.copy()
                if lunch_break:
                    routines_for_row.append({
                        'start_time': lunch_break['start_time'],
                        'end_time': lunch_break['end_time'],
                        'is_lunch_break': True
                    })
                # Sort by start_time
                routines_for_row.sort(key=lambda r: r['start_time'])
                # For each slot, check if a routine (or lunch) starts at this slot
                while slot_idx < len(slot_ranges):
                    slot_start, slot_end, slot_label = slot_ranges[slot_idx]
                    found = False
                    for r in routines_for_row:
                        r_start = r['start_time']
                        r_end = r['end_time']
                        if r_start == slot_start:
                            # Determine how many slots this routine spans
                            colspan = 0
                            for j in range(slot_idx, len(slot_ranges)):
                                s2, e2, _ = slot_ranges[j]
                                if e2 <= r_end:
                                    colspan += 1
                                else:
                                    break
                            if r.get('is_lunch_break'):
                                content = 'BREAK'
                                cell = {'content': content, 'colspan': colspan, 'is_lunch_break': True}
                            else:
                                content = {
                                    'course_code': r['course_code'],
                                    'teacher': 'Supervisor' if r['course_code'] == 'CSE4246' else r['teacher'],
                                }
                                if 'id' in r and 'course_id' in r:
                                    content['routine_id'] = r['id']
                                    content['course_id'] = r['course_id']
                                cell = {'content': content, 'colspan': colspan, 'is_lunch_break': False}
                            row_cells.append(cell)
                            slot_idx += colspan
                            found = True
                            break
                    if not found:
                        # If this is a makeup/reserved date, show 'Reserved Class'
                        if date in makeup_dates:
                            row_cells.append({'content': 'Makeup Class', 'colspan': 1, 'is_makeup_class': True})
                        else:
                            row_cells.append({'content': '', 'colspan': 1, 'is_lunch_break': False})
                        slot_idx += 1
                routine_table_rows.append({'date': date, 'day': day, 'cells': row_cells})

            # Prepare data for the calendar view
            if generated_routines:
                # Get unique dates and days for column headers
                unique_dates = []
                seen_dates = set()
                for routine in generated_routines:
                    date_str = routine['date'].strftime('%Y-%m-%d')
                    if date_str not in seen_dates:
                        seen_dates.add(date_str)
                        unique_dates.append((routine['date'], routine['day']))

                # Sort dates chronologically
                unique_dates.sort(key=lambda x: x[0])

                # Dynamically generate time slots from the actual start and end times
                # of scheduled courses
                time_slots = []
                time_slot_set = set()
                for routine in generated_routines:
                    time_slot = f"{routine['start_time']} - {routine['end_time']}"
                    if time_slot not in time_slot_set:
                        time_slot_set.add(time_slot)
                        time_slots.append(time_slot)

                # Sort time slots chronologically
                time_slots.sort(key=lambda x: x.split(' - ')[0])

                # Add lunch break if configured
                lunch_break = None
                if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
                    lunch_break = f"{selected_semester.lunch_break_start.strftime('%H:%M')} - {selected_semester.lunch_break_end.strftime('%H:%M')}"
                    if lunch_break not in time_slot_set:
                        time_slots.append(lunch_break)
                        time_slots.sort(key=lambda x: x.split(' - ')[0])

                # Format routines for the calendar view with time slot info
                calendar_routines = []
                for routine in generated_routines:
                    time_slot = f"{routine['start_time']} - {routine['end_time']}"

                    calendar_routines.append({
                        'date': routine['date'],
                        'day': routine['day'],
                        'course_code': routine['course_code'],
                        'course_name': routine['course_name'],
                        'teacher': routine['teacher'],
                        'start_time': routine['start_time'],
                        'end_time': routine['end_time'],
                        'time_slot': time_slot,
                        'is_lunch_break': False
                    })

                # Add lunch break info to calendar routines context
                if lunch_break:
                    context_lunch_break = {
                        'is_lunch_break': True,
                        'time_slot': lunch_break
                    }
                else:
                    context_lunch_break = None
            else:
                unique_dates = []
                time_slots = []
                calendar_routines = []
                context_lunch_break = None

            # Add success or warning message based on whether routines were generated
            if generated_routines:
                messages.success(request, f"Successfully generated routine for {selected_semester.name} with {len(generated_routines)} classes")
            else:
                # Create a detailed debug message
                debug_info = {
                    'date_range': f"{start_date} to {end_date}",
                    'processed_days': processed_days,
                    'matched_days': matched_days,
                    'form_days': days,
                    'course_codes_count': len(course_codes),
                    'friday_courses': [course_codes[i] for i in range(len(days)) if days[i] == 'Friday'],
                    'saturday_courses': [course_codes[i] for i in range(len(days)) if days[i] == 'Saturday'],
                }
                
                # Add debug info to the warning message
                messages.warning(request, f"No classes were generated for {selected_semester.name}. Debug info: {debug_info}")
                
        except Exception as e:
            return render(request, "bou_routines_app/generate_routine.html", {
                "semesters": semesters,
                "courses": courses,
                "teachers": teachers,
                "error": f"Error generating routines: {str(e)}",
                "selected_semester_id": selected_semester_id
            })

    # Add selected_semester_id to the context if it was provided in POST
    context = {
        "semesters": semesters,
        "courses": courses,
        "teachers": teachers,
        "generated_routines": generated_routines,
        "selected_semester_id": selected_semester_id,
        "selected_semester": selected_semester,
        "teacher_short_name_newline": teacher_short_name_newline,
        "curricula": curricula,
        "selected_curriculum": selected_curriculum,
        "selected_curriculum_id": selected_curriculum.id if selected_curriculum else None,
    }
    
    
    # Add calendar view data if routines were generated (either from POST or GET)
    if generated_routines:
        context.update({
            "routine_dates": unique_dates,
            "time_slots": time_slots,
            "calendar_routines": calendar_routines,
            "lunch_break": lunch_break,
            # New keys for merged table
            "routine_table_rows": routine_table_rows,
            "time_slot_labels": time_slot_labels,
            "makeup_dates": makeup_dates,  # <-- Add this line
        })

    # Include the selected semester ID if available in POST
    if request.method == "POST" and request.POST.get("semester"):
        try:
            context["selected_semester_id"] = int(request.POST.get("semester"))
        except (ValueError, TypeError):
            context["selected_semester_id"] = None
        
    # After routine_table_rows is built, append selected makeup/extra class dates as empty rows (if not already present)
    if routine_table_rows and time_slot_labels:
        # Get all dates already present in the table
        existing_dates = set(row['date'] for row in routine_table_rows)
        # Get makeup dates from the semester
        makeup_dates = []
        if selected_semester.makeup_dates:
            makeup_dates = [
                datetime.strptime(date.strip(), "%Y-%m-%d").date()
                for date in selected_semester.makeup_dates.split(',')
                if date.strip()
            ]
        # Add makeup dates as empty rows only if not already present
        for makeup_date in makeup_dates:
            if makeup_date not in existing_dates:
                routine_table_rows.append({
                    'date': makeup_date,
                    'day': makeup_date.strftime('%A'),
                    'cells': [
                        {'content': None, 'colspan': 1, 'start_time': slot[0], 'end_time': slot[1]}
                        for slot in slot_ranges
                    ]
                })

    return render(request, "bou_routines_app/generate_routine.html", context)

@login_required
def update_semester_courses(request):
    # Get all curricula
    curricula = Curriculum.objects.filter(is_active=True).order_by('name')
    
    # Get selected curriculum from request
    selected_curriculum_id = request.GET.get('curriculum') or request.POST.get('curriculum')
    selected_curriculum = None
    
    if selected_curriculum_id:
        try:
            # Convert to integer to ensure type consistency
            selected_curriculum_id = int(selected_curriculum_id)
            selected_curriculum = Curriculum.objects.get(id=selected_curriculum_id)
        except (Curriculum.DoesNotExist, ValueError):
            selected_curriculum = None
            selected_curriculum_id = None
    
    # If no curriculum selected, use the Old Curriculum by default
    if not selected_curriculum and curricula.exists():
        try:
            selected_curriculum = Curriculum.objects.get(code='OLD')
            selected_curriculum_id = selected_curriculum.id
        except Curriculum.DoesNotExist:
            selected_curriculum = curricula.first()
            selected_curriculum_id = selected_curriculum.id if selected_curriculum else None
    
    # Filter semesters and courses by selected curriculum
    if selected_curriculum:
        semesters = Semester.objects.filter(curriculum=selected_curriculum).order_by('name')
        # Custom sorting for courses - sort by curriculum, then by code
        courses = Course.objects.filter(curriculum=selected_curriculum).order_by('code')
    else:
        semesters = Semester.objects.all().order_by('name')
        courses = Course.objects.all().order_by('code')
    
    from .models import Teacher
    teachers = Teacher.objects.all().order_by('name')
    context = {
        "semesters": semesters,
        "courses": courses,
        "teachers": teachers,
        "curricula": curricula,
        "selected_curriculum": selected_curriculum,
        "selected_curriculum_id": selected_curriculum.id if selected_curriculum else None,
    }
    
    # Debug output
    print(f"DEBUG: selected_curriculum_id = {selected_curriculum_id}")
    print(f"DEBUG: selected_curriculum = {selected_curriculum}")
    print(f"DEBUG: context selected_curriculum_id = {context['selected_curriculum_id']}")
    print(f"DEBUG: curricula = {[(c.id, c.name) for c in curricula]}")
    
    
    
    if request.method == "POST":
        semester_id = request.POST.get("semester")
        context["selected_semester_id"] = semester_id
        semester = Semester.objects.get(id=semester_id)

        # Update semester info fields from POST
        semester.semester_full_name = request.POST.get("semester_full_name", semester.semester_full_name)
        semester.term = request.POST.get("term", semester.term)
        semester.session = request.POST.get("session", semester.session)
        semester.study_center = request.POST.get("study_center", semester.study_center)
        semester.contact_person = request.POST.get("contact_person", semester.contact_person)
        semester.contact_person_designation = request.POST.get("contact_person_designation", semester.contact_person_designation)
        semester.contact_person_phone = request.POST.get("contact_person_phone", semester.contact_person_phone)
        semester.contact_person_email = request.POST.get("contact_person_email", semester.contact_person_email)
        
        # Update class duration fields
        theory_duration = request.POST.get("theory_class_duration_minutes")
        lab_duration = request.POST.get("lab_class_duration_minutes")
        if theory_duration:
            try:
                semester.theory_class_duration_minutes = int(theory_duration)
            except ValueError:
                pass  # Keep existing value if invalid
        if lab_duration:
            try:
                semester.lab_class_duration_minutes = int(lab_duration)
            except ValueError:
                pass  # Keep existing value if invalid
        
        semester.save()

        SemesterCourse.objects.filter(semester=semester).delete()
        course_ids = request.POST.getlist("courses[]")
        teacher_ids = request.POST.getlist("teachers[]")
        number_of_classes = request.POST.getlist("classes")
        for i, course_id in enumerate(course_ids):
            course = Course.objects.get(id=course_id)
            # Update teacher if changed
            if i < len(teacher_ids):
                teacher_id = teacher_ids[i]
                if teacher_id and str(course.teacher.id) != str(teacher_id):
                    course.teacher = Teacher.objects.get(id=teacher_id)
                    course.save()
            try:
                num_classes = int(number_of_classes[i]) if i < len(number_of_classes) else 1
                if num_classes < 1:
                    num_classes = 0
            except (ValueError, IndexError):
                num_classes = 0
            SemesterCourse.objects.create(
                semester=semester,
                course=course,
                number_of_classes=num_classes
            )
        #messages.success(request, f"Successfully updated courses for {semester.name}")
        # Redirect to the same page with selected semester and success param
        base_url = reverse('update-semester-courses')
        query_string = urlencode({'semester': semester_id, 'success': 1})
        url = f"{base_url}?{query_string}"
        return redirect(url)

    # On GET, pre-select semester if query param is present
    semester_id = request.GET.get("semester")
    if semester_id:
        context["selected_semester_id"] = semester_id
    return render(request, "bou_routines_app/semester_courses.html", context)

@login_required
def get_semester_courses(request):
    """AJAX view to get courses for a specific semester"""
    if request.method == "GET":
        semester_id = request.GET.get("semester_id")
        if semester_id:
            try:
                semester = Semester.objects.get(id=semester_id)
                semester_courses = SemesterCourse.objects.filter(semester_id=semester_id).select_related('course', 'course__teacher')
                courses_data = [{
                    'id': sc.course.id,
                    'code': sc.course.code,
                    'name': sc.course.name,
                    'teacher_name': sc.course.teacher.name,
                    'teacher_id': sc.course.teacher.id,
                    'number_of_classes': sc.number_of_classes
                } for sc in semester_courses]
                lunch_break_info = None
                if semester.lunch_break_start and semester.lunch_break_end:
                    lunch_break_info = {
                        'start': semester.lunch_break_start.strftime('%H:%M'),
                        'end': semester.lunch_break_end.strftime('%H:%M')
                    }
                date_range_info = None
                if semester.start_date and semester.end_date:
                    date_range_info = {
                        'start_date': semester.start_date.strftime('%m/%d/%Y'),
                        'end_date': semester.end_date.strftime('%m/%d/%Y')
                    }
                holidays_info = None
                if semester.holidays:
                    holidays_info = semester.holidays
                
                makeup_dates_info = None
                if semester.makeup_dates:
                    makeup_dates_info = semester.makeup_dates
                
                # Add all semester info fields
                semester_data = {
                    'semester_full_name': semester.semester_full_name,
                    'term': semester.term,
                    'session': semester.session,
                    'study_center': semester.study_center,
                    'contact_person': semester.contact_person,
                    'contact_person_designation': semester.contact_person_designation,
                    'contact_person_phone': semester.contact_person_phone,
                    'contact_person_email': semester.contact_person_email,
                    'theory_class_duration_minutes': semester.theory_class_duration_minutes,
                    'lab_class_duration_minutes': semester.lab_class_duration_minutes,
                }
                return JsonResponse({
                    'courses': courses_data,
                    'lunch_break': lunch_break_info,
                    'date_range': date_range_info,
                    'holidays': holidays_info,
                    'makeup_dates': makeup_dates_info,
                    'semester_data': semester_data
                })
            except Semester.DoesNotExist:
                return JsonResponse({'courses': [], 'lunch_break': None})
    return JsonResponse({'courses': [], 'lunch_break': None})

@login_required
def get_existing_generated_routines(request):
    """AJAX view to get existing generated routines for a specific semester"""
    if request.method == "GET":
        semester_id = request.GET.get("semester_id")
        if semester_id:
            try:
                semester = Semester.objects.get(id=semester_id)
                existing_routines = NewRoutine.objects.filter(semester=semester).select_related('course', 'course__teacher').order_by('class_date', 'start_time')
                
                routines_data = []
                if existing_routines.exists():
                    for routine in existing_routines:
                        routines_data.append({
                            'id': routine.id,
                            'date': routine.class_date.strftime('%Y-%m-%d'),
                            'day': routine.day,
                            'course_code': routine.course.code,
                            'course_name': routine.course.name,
                            'teacher': routine.course.teacher.name,
                            'start_time': routine.start_time.strftime('%H:%M'),
                            'end_time': routine.end_time.strftime('%H:%M')
                        })
                
                return JsonResponse({
                    'routines': routines_data,
                    'has_routines': len(routines_data) > 0
                })
            except Semester.DoesNotExist:
                return JsonResponse({'routines': [], 'has_routines': False})
    return JsonResponse({'routines': [], 'has_routines': False})

@login_required
def check_time_overlap(request):
    """AJAX endpoint to check for time overlaps in real-time"""
    if request.method == "GET":
        # Check if this is a request to get all routines for a semester
        if request.GET.get("get_semester_routines") == "1":
            semester_id = request.GET.get("semester_id")
            if semester_id:
                try:
                    # Get all CurrentRoutine objects for this semester
                    routines = CurrentRoutine.objects.filter(semester_id=semester_id).select_related('course', 'course__teacher')
                    
                    # Format the data for response
                    routines_data = [{
                        'course_id': routine.course.id,
                        'course_code': routine.course.code,
                        'course_name': routine.course.name,
                        'teacher_name': routine.course.teacher.name,
                        'teacher_id': routine.course.teacher.id,
                        'day': routine.day,
                        'start_time': routine.start_time.strftime('%H:%M'),
                        'end_time': routine.end_time.strftime('%H:%M')
                    } for routine in routines]
                    
                    return JsonResponse({
                        'routines': routines_data
                    })
                except Exception as e:
                    return JsonResponse({'error': str(e)}, status=400)

        # Regular time overlap check
        day = request.GET.get("day")
        start_time = request.GET.get("start_time")
        end_time = request.GET.get("end_time")
        teacher_id = request.GET.get("teacher_id")
        course_id = request.GET.get("course_id", None)  # Optional, to exclude current course from check
        semester_id = request.GET.get("semester_id", None)  # Added semester_id to check lunch break
        lunch_break_start = request.GET.get("lunch_break_start", None)
        lunch_break_end = request.GET.get("lunch_break_end", None)
        
        if not all([day, start_time, end_time, teacher_id]):
            return JsonResponse({"overlaps": []})
        
        try:
            start = datetime.strptime(start_time, "%H:%M").time()
            end = datetime.strptime(end_time, "%H:%M").time()
            
            overlaps = []
            
            # Check for lunch break overlap if lunch break times are provided
            if lunch_break_start and lunch_break_end:
                lunch_start = datetime.strptime(lunch_break_start, "%H:%M").time()
                lunch_end = datetime.strptime(lunch_break_end, "%H:%M").time()
                
                # Check if time slot overlaps with lunch break
                if time_overlap(start, end, lunch_start, lunch_end):
                    overlaps.append({
                        "course": "Lunch Break",
                        "course_name": "Lunch Break",
                        "teacher": "All",
                        "day": day,
                        "start": lunch_break_start,
                        "end": lunch_break_end,
                        "is_lunch_break": True
                    })
            # Fall back to semester's lunch break if no custom times provided
            elif semester_id:
                try:
                    semester = Semester.objects.get(id=semester_id)
                    if semester.lunch_break_start and semester.lunch_break_end:
                        lunch_start = semester.lunch_break_start
                        lunch_end = semester.lunch_break_end
                        
                        # Check if time slot overlaps with lunch break
                        if time_overlap(start, end, lunch_start, lunch_end):
                            overlaps.append({
                                "course": "Lunch Break",
                                "course_name": "Lunch Break",
                                "teacher": "All",
                                "day": day,
                                "start": lunch_start.strftime("%H:%M"),
                                "end": lunch_end.strftime("%H:%M"),
                                "is_lunch_break": True
                            })
                except Semester.DoesNotExist:
                    pass
            
            # Find routines with the same day and same teacher
            query = CurrentRoutine.objects.filter(day=day, course__teacher_id=teacher_id)
            
            # Exclude current course if provided (for editing scenarios)
            if course_id:
                query = query.exclude(course_id=course_id)
                
            for routine in query:
                if time_overlap(start, end, routine.start_time, routine.end_time):
                    overlaps.append({
                        "course": routine.course.code,
                        "course_name": routine.course.name,
                        "teacher": routine.course.teacher.name,
                        "day": routine.day,
                        "start": routine.start_time.strftime("%H:%M"),
                        "end": routine.end_time.strftime("%H:%M"),
                        "is_lunch_break": False
                    })
            
            return JsonResponse({
                "overlaps": overlaps,
                "hasOverlaps": len(overlaps) > 0
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    
    return JsonResponse({"overlaps": []})

@login_required
def update_routine_course(request):
    """Update a routine's course or create a new routine entry via AJAX"""
    if request.method == 'POST':
        try:
            routine_id = request.POST.get('routine_id')
            new_course_id = request.POST.get('course_id')
            
            if not new_course_id:
                return JsonResponse({"error": "Missing course_id"}, status=400)
            
            # Get the course
            new_course = Course.objects.get(id=new_course_id)
            
            if routine_id:
                # Updating existing routine
                try:
                    routine = NewRoutine.objects.get(id=routine_id)
                    routine.course = new_course
                    routine.save()
                    
                    # Return updated course information
                    return JsonResponse({
                        "success": True,
                        "course_code": new_course.code,
                        "course_name": new_course.name,
                        "teacher_name": new_course.teacher.name,
                        "teacher_short_name": new_course.teacher.short_name if new_course.teacher.short_name else new_course.teacher.name
                    })
                except NewRoutine.DoesNotExist:
                    return JsonResponse({"error": "Routine not found"}, status=404)
            else:
                # Creating new routine entry
                date_str = request.POST.get('date')
                day = request.POST.get('day')
                time_slot = request.POST.get('time_slot')
                semester_id = request.POST.get('semester_id')
                start_time_str = request.POST.get('start_time')
                end_time_str = request.POST.get('end_time')
                
                if not all([date_str, day, time_slot, semester_id, start_time_str, end_time_str]):
                    return JsonResponse({"error": "Missing required fields for new routine"}, status=400)
                
                try:
                    semester = Semester.objects.get(id=semester_id)
                    class_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    start_time = datetime.strptime(start_time_str, '%H:%M').time()
                    end_time = datetime.strptime(end_time_str, '%H:%M').time()
                    
                    # Create new routine entry
                    new_routine = NewRoutine.objects.create(
                        semester=semester,
                        course=new_course,
                        class_date=class_date,
                        day=day,
                        start_time=start_time,
                        end_time=end_time
                    )
                    
                    # Return new routine information
                    return JsonResponse({
                        "success": True,
                        "routine_id": new_routine.id,
                        "course_code": new_course.code,
                        "course_name": new_course.name,
                        "teacher_name": new_course.teacher.name,
                        "teacher_short_name": new_course.teacher.short_name if new_course.teacher.short_name else new_course.teacher.name
                    })
                    
                except Semester.DoesNotExist:
                    return JsonResponse({"error": "Semester not found"}, status=404)
                except ValueError:
                    return JsonResponse({"error": "Invalid date or time format"}, status=400)
            
        except Course.DoesNotExist:
            return JsonResponse({"error": "Course not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    
    return JsonResponse({"error": "Invalid request method"}, status=405)

@login_required
def remove_routine_course(request):
    """Remove a routine entry via AJAX"""
    if request.method == 'POST':
        try:
            routine_id = request.POST.get('routine_id')
            
            if not routine_id:
                return JsonResponse({"error": "Missing routine_id"}, status=400)
            
            # Get and delete the routine
            try:
                routine = NewRoutine.objects.get(id=routine_id)
                routine.delete()
                
                return JsonResponse({
                    "success": True,
                    "message": "Routine entry removed successfully"
                })
                
            except NewRoutine.DoesNotExist:
                return JsonResponse({"error": "Routine not found"}, status=404)
                
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    
    return JsonResponse({"error": "Invalid request method"}, status=405)

@login_required
def export_to_excel(request, semester_id):
    """Export the routine to Excel file"""
    try:
        selected_semester = Semester.objects.get(id=semester_id)

        # Create a response for Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet("Routine")

        # Add some formatting
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'center',
            'valign': 'vcenter'
        })
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#2c3e50',
            'font_color': 'white',
            'border': 1
        })
        cell_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        date_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bold': True,
            'num_format': 'dd/mm/yyyy'
        })
        lunch_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#fff2cc',
            'bold': True
        })
        course_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#3498db',
            'font_color': 'white',
            'text_wrap': True
        })

        # Add formats for even row background and even row class cell
        even_row_bg_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#e3f0fa',
        })
        even_class_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'bg_color': '#d0e6f7',
            'font_color': 'black',
            'text_wrap': True
        })

        # Get the routines from the database
        routines = NewRoutine.objects.filter(semester=selected_semester).order_by('class_date', 'start_time')

        # Get unique dates and days
        unique_dates_days = []
        seen_dates = set()
        for routine in routines:
            date_str = routine.class_date.strftime('%Y-%m-%d')
            if date_str not in seen_dates:
                seen_dates.add(date_str)
                unique_dates_days.append((routine.class_date, routine.day))

        # Sort dates chronologically
        unique_dates_days.sort(key=lambda x: x[0])

        # --- Build slot_ranges for merging logic ---
        time_boundaries = set()
        for routine in routines:
            time_boundaries.add(routine.start_time.strftime('%H:%M'))
            time_boundaries.add(routine.end_time.strftime('%H:%M'))
        if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
            time_boundaries.add(selected_semester.lunch_break_start.strftime('%H:%M'))
            time_boundaries.add(selected_semester.lunch_break_end.strftime('%H:%M'))
        time_boundaries = sorted(time_boundaries)

        slot_ranges = []
        for i in range(len(time_boundaries)-1):
            slot_start = time_boundaries[i]
            slot_end = time_boundaries[i+1]
            slot_ranges.append((slot_start, slot_end, f"{slot_start} - {slot_end}"))

        used_slots = set()
        for routine in routines:
            r_start = routine.start_time.strftime('%H:%M')
            r_end = routine.end_time.strftime('%H:%M')
            for i in range(len(time_boundaries)-1):
                slot_start = time_boundaries[i]
                slot_end = time_boundaries[i+1]
                if (slot_start >= r_start and slot_end <= r_end):
                    used_slots.add((slot_start, slot_end))
        if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
            lb_start = selected_semester.lunch_break_start.strftime('%H:%M')
            lb_end = selected_semester.lunch_break_end.strftime('%H:%M')
            for i in range(len(time_boundaries)-1):
                slot_start = time_boundaries[i]
                slot_end = time_boundaries[i+1]
                if (slot_start >= lb_start and slot_end <= lb_end):
                    used_slots.add((slot_start, slot_end))

        filtered_slot_ranges = []
        for slot_start, slot_end, label in slot_ranges:
            if (slot_start, slot_end) in used_slots:
                filtered_slot_ranges.append((slot_start, slot_end, label))
        slot_ranges = filtered_slot_ranges

        # Add title
        worksheet.merge_range(0, 0, 0, len(slot_ranges) + 1, f"{selected_semester.name} Routine", title_format)

        # Write headers
        row = 2
        worksheet.write(row, 0, "Date", header_format)
        worksheet.write(row, 1, "Day", header_format)
        for col, (_, _, label) in enumerate(slot_ranges):
            worksheet.write(row, col + 2, label, header_format)

        # Set column widths
        worksheet.set_column(0, 0, 12)  # Date column
        worksheet.set_column(1, 1, 10)  # Day column
        worksheet.set_column(2, len(slot_ranges) + 1, 15)  # Time slot columns

        # Merge unique_dates_days and makeup_dates, sort, and output in order
        makeup_dates = []
        if selected_semester.makeup_dates:
            makeup_dates = [
                datetime.strptime(date.strip(), "%Y-%m-%d").date()
                for date in selected_semester.makeup_dates.split(',')
                if date.strip()
            ]
        # Build a dict for quick lookup of routines by date
        routines_by_date = {date: day for date, day in unique_dates_days}
        all_dates = set(routines_by_date.keys()) | set(makeup_dates)
        sorted_dates = sorted(all_dates)
        # Write data with merging
        row = 3
        for date_idx, date in enumerate(sorted_dates):
            day = routines_by_date.get(date, date.strftime('%A'))
            is_even_row = (date_idx % 2 == 1)
            worksheet.write(row, 0, date, date_format if not is_even_row else even_row_bg_format)
            worksheet.write(row, 1, day, cell_format if not is_even_row else even_row_bg_format)
            # Build routines for this row
            routines_for_row = []
            for r in routines:
                if r.class_date == date and r.day == day:
                    routines_for_row.append({
                        'course_code': r.course.code,
                        'teacher': 'Supervisor' if r.course.code == 'CSE4246' else r.course.teacher.short_name,
                        'start_time': r.start_time.strftime('%H:%M'),
                        'end_time': r.end_time.strftime('%H:%M'),
                        'is_lunch_break': False
                    })
            if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
                routines_for_row.append({
                    'start_time': selected_semester.lunch_break_start.strftime('%H:%M'),
                    'end_time': selected_semester.lunch_break_end.strftime('%H:%M'),
                    'is_lunch_break': True
                })
            routines_for_row.sort(key=lambda r: r['start_time'])
            # Process each slot and handle merging
            slot_idx = 0
            col_idx = 2  # Start after date and day columns
            while slot_idx < len(slot_ranges):
                slot_start, slot_end, slot_label = slot_ranges[slot_idx]
                found = False
                for r in routines_for_row:
                    r_start = r['start_time']
                    r_end = r['end_time']
                    is_lunch = r.get('is_lunch_break', False)
                    if r_start == slot_start:
                        # Determine colspan
                        colspan = 0
                        for j in range(slot_idx, len(slot_ranges)):
                            s2, e2, _ = slot_ranges[j]
                            if e2 <= r_end:
                                colspan += 1
                            else:
                                break
                        # Prepare cell content
                        if is_lunch:
                            cell_content = "BREAK"
                            format_to_use = lunch_format
                        else:
                            cell_content = f"{r['course_code']} ({r['teacher']})"
                            format_to_use = course_format if not is_even_row else even_class_format
                        # Write content and merge if needed
                        if colspan > 1:
                            worksheet.merge_range(row, col_idx, row, col_idx + colspan - 1, cell_content, format_to_use)
                        else:
                            worksheet.write(row, col_idx, cell_content, format_to_use)
                        col_idx += colspan
                        slot_idx += colspan
                        found = True
                        break
                if not found:
                    # If this is a makeup/reserved date, show 'Reserved Class'
                    if date in makeup_dates:
                        worksheet.write(row, col_idx, "Makeup Class", cell_format if not is_even_row else even_row_bg_format)
                    else:
                        worksheet.write(row, col_idx, "", cell_format if not is_even_row else even_row_bg_format)
                    col_idx += 1
                    slot_idx += 1
            row += 1
        # Set row heights
        for i in range(3, row):
            worksheet.set_row(i, 50)

        workbook.close()

        # Prepare the response
        output.seek(0)
        response = HttpResponse(output.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response['Content-Disposition'] = f'attachment; filename="{selected_semester.name}_Routine.xlsx"'
        return response

    except Exception as e:
        return HttpResponse(f"Error generating Excel file: {str(e)}", status=500)

@login_required
def download_routines(request):
    """Display the last generated routines for all semesters"""
    # Get all semesters that have generated routines
    semesters_with_routines = Semester.objects.filter(
        newroutine__isnull=False
    ).distinct().order_by('order', 'name')
    
    # For each semester, get the last generated routine data
    semester_routines = []
    for semester in semesters_with_routines:
        # Get the latest routines for this semester
        latest_routines = NewRoutine.objects.filter(
            semester=semester
        ).order_by('class_date', 'start_time')
        
        if latest_routines.exists():
            # Get unique dates and days
            unique_dates_days = []
            seen_dates = set()
            for routine in latest_routines:
                date_str = routine.class_date.strftime('%Y-%m-%d')
                if date_str not in seen_dates:
                    seen_dates.add(date_str)
                    unique_dates_days.append((routine.class_date, routine.day))
            
            # Sort dates chronologically
            unique_dates_days.sort(key=lambda x: x[0])
            
            # Build time slot structure for merged view
            time_boundaries = set()
            for routine in latest_routines:
                time_boundaries.add(routine.start_time.strftime('%H:%M'))
                time_boundaries.add(routine.end_time.strftime('%H:%M'))
            if semester.lunch_break_start and semester.lunch_break_end:
                time_boundaries.add(semester.lunch_break_start.strftime('%H:%M'))
                time_boundaries.add(semester.lunch_break_end.strftime('%H:%M'))
            time_boundaries = sorted(time_boundaries)
            
            slot_ranges = []
            for i in range(len(time_boundaries)-1):
                slot_start = time_boundaries[i]
                slot_end = time_boundaries[i+1]
                slot_ranges.append((slot_start, slot_end, f"{slot_start} - {slot_end}"))
            
            used_slots = set()
            for routine in latest_routines:
                r_start = routine.start_time.strftime('%H:%M')
                r_end = routine.end_time.strftime('%H:%M')
                for i in range(len(time_boundaries)-1):
                    slot_start = time_boundaries[i]
                    slot_end = time_boundaries[i+1]
                    if (slot_start >= r_start and slot_end <= r_end):
                        used_slots.add((slot_start, slot_end))
            if semester.lunch_break_start and semester.lunch_break_end:
                lb_start = semester.lunch_break_start.strftime('%H:%M')
                lb_end = semester.lunch_break_end.strftime('%H:%M')
                for i in range(len(time_boundaries)-1):
                    slot_start = time_boundaries[i]
                    slot_end = time_boundaries[i+1]
                    if (slot_start >= lb_start and slot_end <= lb_end):
                        used_slots.add((slot_start, slot_end))
            
            filtered_slot_ranges = []
            for slot_start, slot_end, label in slot_ranges:
                if (slot_start, slot_end) in used_slots:
                    filtered_slot_ranges.append((slot_start, slot_end, label))
            slot_ranges = filtered_slot_ranges
            
            # Build routine table rows
            routine_table_rows = []
            for date, day in unique_dates_days:
                row_cells = []
                slot_idx = 0
                routines_for_row = []
                for r in latest_routines:
                    if r.class_date == date and r.day == day:
                        routines_for_row.append({
                            'course_code': r.course.code,
                            'teacher': 'Supervisor' if r.course.code == 'CSE4246' else r.course.teacher.short_name,
                            'start_time': r.start_time.strftime('%H:%M'),
                            'end_time': r.end_time.strftime('%H:%M'),
                            'is_lunch_break': False
                        })
                if semester.lunch_break_start and semester.lunch_break_end:
                    routines_for_row.append({
                        'start_time': semester.lunch_break_start.strftime('%H:%M'),
                        'end_time': semester.lunch_break_end.strftime('%H:%M'),
                        'is_lunch_break': True
                    })
                routines_for_row.sort(key=lambda r: r['start_time'])
                
                while slot_idx < len(slot_ranges):
                    slot_start, slot_end, slot_label = slot_ranges[slot_idx]
                    found = False
                    for r in routines_for_row:
                        r_start = r['start_time']
                        r_end = r['end_time']
                        if r_start == slot_start:
                            colspan = 0
                            for j in range(slot_idx, len(slot_ranges)):
                                s2, e2, _ = slot_ranges[j]
                                if e2 <= r_end:
                                    colspan += 1
                                else:
                                    break
                            if r.get('is_lunch_break'):
                                content = 'BREAK'
                                cell = {'content': content, 'colspan': colspan, 'is_lunch_break': True}
                            else:
                                content = {
                                    'course_code': r['course_code'],
                                    'teacher': 'Supervisor' if r['course_code'] == 'CSE4246' else r['teacher'],
                                }
                                if 'id' in r and 'course_id' in r:
                                    content['routine_id'] = r['id']
                                    content['course_id'] = r['course_id']
                                cell = {'content': content, 'colspan': colspan, 'is_lunch_break': False}
                            row_cells.append(cell)
                            slot_idx += colspan
                            found = True
                            break
                    if not found:
                        row_cells.append({'content': '', 'colspan': 1, 'is_lunch_break': False})
                        slot_idx += 1
                routine_table_rows.append({'date': date, 'day': day, 'cells': row_cells})
            
            # Add makeup dates for this semester
            makeup_dates = []
            if semester.makeup_dates:
                makeup_dates = [
                    datetime.strptime(date.strip(), "%Y-%m-%d").date()
                    for date in semester.makeup_dates.split(',')
                    if date.strip()
                ]
            semester_routines.append({
                'semester': semester,
                'routine_table_rows': routine_table_rows,
                'time_slot_labels': [label for _, _, label in slot_ranges],
                'routine_count': latest_routines.count(),
                'makeup_dates': makeup_dates,  # <-- Add this line
            })
    
    return render(request, 'bou_routines_app/download_routines.html', {
        'semester_routines': semester_routines
    })

@login_required
def export_to_pdf(request, semester_id):
    """Export the routine to PDF file"""
    try:
        selected_semester = Semester.objects.get(id=semester_id)

        # Read the teacher short name display option from GET params
        teacher_short_name_newline = request.GET.get('teacher_short_name_newline', '1') == '1'

        # Create a response for PDF file
        buffer = io.BytesIO()

        # Create the PDF document with A4 landscape orientation and decent print margins
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=54,  # 0.75 inch
            leftMargin=54,   # 0.75 inch
            topMargin=34,    # 0.75 inch
            bottomMargin=34  # Reduced from 54 (about 1/3 inch)
        )

        # Get page width and height for calculations
        page_width, page_height = landscape(A4)

        # Calculate available width for all tables (accounting for document margins)
        available_width = page_width - doc.leftMargin - doc.rightMargin

        elements = []

        # --- HEADER IMAGE SECTION ---
        header_img_path = 'bou_routines_app/static/pdf_routine_top.png'
        try:
            # Padding for the image cell (matching routine table cell padding of 2)
            padding_for_image = 2

            # Create an Image object, scaled by width to fit within the available padded space
            # Height will be auto-calculated to maintain aspect ratio.
            img_obj = Image(header_img_path, width=available_width - (2 * padding_for_image), height=45)

            # Put the image in a single-cell table whose width spans the available area,
            # and apply padding to the cell to align the image correctly.
            header_img_table = Table([[img_obj]], colWidths=[available_width])
            header_img_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'), # Center the image horizontally within its cell
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), # Center vertically
                ('LEFTPADDING', (0,0), (-1, -1), padding_for_image),
                ('RIGHTPADDING', (0,0), (-1, -1), padding_for_image),
                ('TOPPADDING', (0,0), (-1, -1), 0), # No vertical padding here, handled by spacer
                ('BOTTOMPADDING', (0,0), (-1, -1), 0), # No vertical padding here, handled by spacer
            ]))
            elements.append(header_img_table)
        except Exception as e:
            print(f"Error loading header image: {e}")
            pass # If image not found, skip
        elements.append(Spacer(1, -4))  # Minimal gap above program name

        # Build left column (program/session/term/commencement/study center)
        header_style = ParagraphStyle(
            'HeaderStyle',
            fontName='Helvetica-Bold',
            fontSize=15,  # Reduced from 18
            alignment=1,  # Center
            leading=18,   # Reduced from 28
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_small = ParagraphStyle(
            'HeaderStyleSmall',
            fontName='Helvetica-Bold',
            fontSize=11,  # Reduced from 14
            alignment=1,
            leading=14,   # Reduced from 22
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_normal = ParagraphStyle(
            'HeaderStyleNormal',
            fontName='Helvetica',
            fontSize=10,   # Reduced from 12
            alignment=1,
            leading=11,   # Reduced from 20
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_bold = ParagraphStyle(
            'HeaderStyleBold',
            fontName='Helvetica-Bold',
            fontSize=12,  # Reduced from 15
            alignment=1,
            leading=15,   # Reduced from 24
            spaceAfter=0,
            spaceBefore=0,
        )

        left_content = []
        program_name = 'B. Sc in Computer Science and Engineering Program'
        left_content.append(Paragraph(program_name, header_style))
        session = selected_semester.session or ''
        if session:
            left_content.append(Paragraph(f'{session} Session', header_style_small))
        term = selected_semester.term or ''
        semester_full_name = selected_semester.semester_full_name or ''
        if term or semester_full_name:
            combined = f'{term} Term {semester_full_name}'.strip()
            left_content.append(Paragraph(combined, header_style_small))
        left_content.append(Spacer(1, 2))  # Reduced from 8
        left_content.append(Paragraph('Class Routine', header_style_bold))
        commencement = selected_semester.start_date.strftime('%d %B %Y') if selected_semester.start_date else ''
        study_center = selected_semester.study_center or ''
        if commencement:
            left_content.append(Paragraph(f'<b>Date of Commencement:</b> {commencement}', header_style_normal))
        if study_center:
            left_content.append(Paragraph(f'<b>Study Center:</b> {study_center}', header_style_normal))

        # Build right column (contact person box)
        contact_lines = []
        if selected_semester.contact_person:
            contact_label = Paragraph(
                'Contact Person',
                ParagraphStyle(
                    'ContactLabel',
                    fontName='Helvetica-Bold',
                    fontSize=11,
                    alignment=0,  # Left align
                    textColor=colors.white,
                    spaceAfter=0,
                    spaceBefore=0,
                    leading=14,
                )
            )
            # Add 4px gap below the label using a single-cell table row with bottom padding
            contact_label_table = Table(
                [[contact_label]],
                colWidths=[180],
                hAlign='RIGHT',
                style=TableStyle([
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                    ('TOPPADDING', (0,0), (-1,-1), -3),
                    ('LEFTPADDING', (0,0), (-1,-1), 0),
                    ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ])
            )
            contact_info_lines = []
            contact_info_lines.append(selected_semester.contact_person)
        if selected_semester.contact_person_designation:
            contact_info_lines.append(selected_semester.contact_person_designation)
        contact_info_lines.append('School of Science and Technology')
        contact_info_lines.append('Bangladesh Open University')
        if selected_semester.contact_person_phone:
            contact_info_lines.append(f'Phone/Whatsapp: {selected_semester.contact_person_phone}')
        if selected_semester.contact_person_email:
            contact_info_lines.append(f'email:{selected_semester.contact_person_email}')
        contact_info_para = Paragraph(
            '<br/>'.join(contact_info_lines),
            ParagraphStyle(
                'ContactBox',
                fontName='Helvetica',
                fontSize=10,
                alignment=0,  # Left align
                textColor=colors.black,
                leftIndent=2,
                leading=10,
                spaceBefore=0,
                spaceAfter=0,
            )
        )
        contact_table = Table(
            [[contact_label_table], [contact_info_para]],
            colWidths=[180],
            hAlign='RIGHT',
        )
        contact_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),  # Single, lighter border
            ('ROUNDED', (0, 0), (-1, -1), 6),  # Rounded corners
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#2c3e50')),  # Label bg
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (0, 0), 6),  # Label row
            ('BOTTOMPADDING', (0, 0), (0, 0), 4),  # Label row
            ('TOPPADDING', (0, 1), (0, 1), 4),  # Info row
            ('BOTTOMPADDING', (0, 1), (0, 1), 6),  # Info row
        ]))

        # Vertically center the left header content to match the contact box
        left_box_table = Table(
            [[left_content]],
            colWidths=[available_width-180],
            hAlign='LEFT',
            style=TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ])
        )
        two_col_table = Table(
            [[left_box_table, contact_table]],
            colWidths=[available_width-180, 180],
            hAlign='LEFT'
        )
        two_col_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
            ('VALIGN', (1, 0), (1, 0), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        elements.append(Spacer(1, 4))  # Add slight gap before contact box
        elements.append(two_col_table)
        elements.append(Spacer(1, 4))  # Reduced from 16

        # Get the routines from the database
        routines = NewRoutine.objects.filter(semester=selected_semester).order_by('class_date', 'start_time')

        # Get unique dates and days
        unique_dates_days = []
        seen_dates = set()
        for routine in routines:
            date_str = routine.class_date.strftime('%Y-%m-%d')
            if date_str not in seen_dates:
                seen_dates.add(date_str)
                unique_dates_days.append((routine.class_date, routine.day))

        # Sort dates chronologically
        unique_dates_days.sort(key=lambda x: x[0])

        # Get unique time slots
        time_slot_set = set()
        for routine in routines:
            time_slot = f"{routine.start_time.strftime('%H:%M')} - {routine.end_time.strftime('%H:%M')}"
            time_slot_set.add(time_slot)

        # Add lunch break if configured
        lunch_break = None
        if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
            lunch_break = f"{selected_semester.lunch_break_start.strftime('%H:%M')} - {selected_semester.lunch_break_end.strftime('%H:%M')}"
            time_slot_set.add(lunch_break)

        # Sort time slots
        time_slots = sorted(list(time_slot_set), key=lambda x: x.split(' - ')[0])

        # Title
        styles = getSampleStyleSheet()
        title_style = styles['Title']
        title_style.alignment = 1  # Center alignment
        # title = Paragraph(f"{selected_semester.name} Routine", title_style)
        # elements.append(title)
        elements.append(Paragraph("<br/>", styles['Normal']))

        # --- Build slot_ranges before using it ---
        time_boundaries = set()
        for routine in routines:
            time_boundaries.add(routine.start_time.strftime('%H:%M'))
            time_boundaries.add(routine.end_time.strftime('%H:%M'))
        if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
            time_boundaries.add(selected_semester.lunch_break_start.strftime('%H:%M'))
            time_boundaries.add(selected_semester.lunch_break_end.strftime('%H:%M'))
        time_boundaries = sorted(time_boundaries)

        slot_ranges = []
        for i in range(len(time_boundaries)-1):
            slot_start = time_boundaries[i]
            slot_end = time_boundaries[i+1]
            slot_ranges.append((slot_start, slot_end, f"{slot_start} - {slot_end}"))

        used_slots = set()
        for routine in routines:
            r_start = routine.start_time.strftime('%H:%M')
            r_end = routine.end_time.strftime('%H:%M')
            for i in range(len(time_boundaries)-1):
                slot_start = time_boundaries[i]
                slot_end = time_boundaries[i+1]
                if (slot_start >= r_start and slot_end <= r_end):
                    used_slots.add((slot_start, slot_end))
        if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
            lb_start = selected_semester.lunch_break_start.strftime('%H:%M')
            lb_end = selected_semester.lunch_break_end.strftime('%H:%M')
            for i in range(len(time_boundaries)-1):
                slot_start = time_boundaries[i]
                slot_end = time_boundaries[i+1]
                if (slot_start >= lb_start and slot_end <= lb_end):
                    used_slots.add((slot_start, slot_end))

        filtered_slot_ranges = []
        for slot_start, slot_end, label in slot_ranges:
            if (slot_start, slot_end) in used_slots:
                filtered_slot_ranges.append((slot_start, slot_end, label))
        slot_ranges = filtered_slot_ranges

        # --- Build table_data for PDF with colspans and track spans ---
        span_commands = []  # To collect ('SPAN', ...) commands
        header_row = ["Date", "Day"] + [label for _, _, label in slot_ranges]
        table_data = [header_row]
        # Merge all routine dates and makeup dates, sort, and ensure each date appears only once in order
        makeup_dates = []
        if selected_semester.makeup_dates:
            makeup_dates = [
                datetime.strptime(date.strip(), "%Y-%m-%d").date()
                for date in selected_semester.makeup_dates.split(',')
                if date.strip()
            ]
        day_by_date = {date: day for date, day in unique_dates_days}
        all_dates = set(day_by_date.keys()) | set(makeup_dates)
        sorted_dates = sorted(all_dates)

        for row_idx, date in enumerate(sorted_dates, start=1):
            day = day_by_date.get(date, date.strftime('%A'))
            row = [date.strftime('%d/%m/%y'), day]
            slot_idx = 0
            # Build routines_for_row: all routines for this date, plus lunch break if present
            routines_for_row = []
            for r in routines:
                if r.class_date == date:
                    routines_for_row.append({
                        'course_code': r.course.code,
                        'teacher': 'Supervisor' if r.course.code == 'CSE4246' else r.course.teacher.short_name,
                        'start_time': r.start_time.strftime('%H:%M'),
                        'end_time': r.end_time.strftime('%H:%M'),
                        'is_lunch_break': False
                    })
            if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
                routines_for_row.append({
                    'start_time': selected_semester.lunch_break_start.strftime('%H:%M'),
                    'end_time': selected_semester.lunch_break_end.strftime('%H:%M'),
                    'is_lunch_break': True
                })
            routines_for_row.sort(key=lambda r: r['start_time'])
            col_idx = 2
            while slot_idx < len(slot_ranges):
                slot_start, slot_end, slot_label = slot_ranges[slot_idx]
                found = False
                for r in routines_for_row:
                    r_start = r['start_time']
                    r_end = r['end_time']
                    is_lunch = r.get('is_lunch_break', False)
                    if r_start == slot_start:
                        # Determine colspan
                        colspan = 0
                        for j in range(slot_idx, len(slot_ranges)):
                            s2, e2, _ = slot_ranges[j]
                            if e2 <= r_end:
                                colspan += 1
                            else:
                                break
                        # Add content and None for colspan-1
                        if is_lunch:
                            cell_content = Paragraph("BREAK", ParagraphStyle(
                                'BreakContent',
                                fontName='Helvetica-Bold',
                                fontSize=9,
                                alignment=TA_CENTER,
                                leading=8,
                                spaceBefore=0,
                                spaceAfter=0,
                            ))
                        else:
                            course_code = r['course_code']
                            teacher_short = r['teacher']
                            if teacher_short_name_newline:
                                cell_content = Paragraph(f"{course_code}<br/>({teacher_short})", ParagraphStyle(
                                    'CourseContent',
                                    fontName='Helvetica',
                                    fontSize=9,
                                    alignment=TA_CENTER,
                                    leading=10,
                                    spaceBefore=0,
                                    spaceAfter=0,
                                ))
                            else:
                                cell_content = Paragraph(f"{course_code} ({teacher_short})", ParagraphStyle(
                                    'CourseContent',
                                    fontName='Helvetica',
                                    fontSize=9,
                                    alignment=TA_CENTER,
                                    leading=10,
                                    spaceBefore=0,
                                    spaceAfter=0,
                                ))
                        row.append(cell_content)
                        for _ in range(colspan-1):
                            row.append(None)
                        if colspan > 1:
                            span_commands.append(('SPAN', (col_idx, row_idx), (col_idx + colspan - 1, row_idx)))
                        col_idx += colspan
                        slot_idx += colspan
                        found = True
                        break
                if not found:
                    # If this is a makeup date, show 'Makeup Class'
                    if date in makeup_dates:
                        cell_content = Paragraph("Makeup Class", ParagraphStyle(
                            'MakeupClass',
                            fontName='Helvetica-Bold',
                            fontSize=9,
                            alignment=TA_CENTER,
                            textColor=colors.blue,
                            leading=10,
                            spaceBefore=0,
                            spaceAfter=0,
                        ))
                        row.append(cell_content)
                    else:
                        row.append("")
                    col_idx += 1
                    slot_idx += 1
            table_data.append(row)

        # Calculate available width for all tables
        available_width = page_width - doc.leftMargin - doc.rightMargin

        # Set column widths directly without depending on lunch_col_idx
        num_cols = len(header_row)
        date_col_width = 47   # decreased date column width
        day_col_width = 47    # narrow day column

        # Find the lunch break time label (if present)
        lunch_break_label = None
        if selected_semester.lunch_break_start and selected_semester.lunch_break_end:
            lunch_break_label = f"{selected_semester.lunch_break_start.strftime('%H:%M')} - {selected_semester.lunch_break_end.strftime('%H:%M')}"

        # Identify lunch break column index (if present)
        lunch_col_idx = None
        for idx, label in enumerate(header_row):
            if lunch_break_label and label == lunch_break_label:
                lunch_col_idx = idx
                break
        lunch_col_width = 60  # smaller width for lunch break column
        # Calculate remaining width for other columns
        if lunch_col_idx is not None:
            remaining_width = available_width - date_col_width - day_col_width - lunch_col_width
            other_col_count = num_cols - 3  # date, day, lunch
        else:
            remaining_width = available_width - date_col_width - day_col_width
            other_col_count = num_cols - 2
        other_col_width = remaining_width / other_col_count if other_col_count > 0 else 0

        # Build column widths list
        col_widths = []
        for i in range(num_cols):
            if i == 0:
                col_widths.append(date_col_width)
            elif i == 1:
                col_widths.append(day_col_width)
            elif i == lunch_col_idx:
                col_widths.append(lunch_col_width)
            else:
                col_widths.append(other_col_width)

        # Scale down if sum(col_widths) > available_width
        total_width = sum(col_widths)
        if total_width > available_width:
            scale = available_width / total_width
            col_widths = [w * scale for w in col_widths]

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        # Custom style for the table
        style = TableStyle([
            # Headers styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            # Alignment and spacing
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            # Grid and borders
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            # Set a fixed row height
            ('ROWHEIGHT', (0, 1), (-1, -1), 28),  # Reduced cell height
            # Text wrapping for all cells
            ('WORDWRAP', (0, 0), (-1, -1), True),
        ])
        # Add background color for lunch breaks and classes, and alternate row colors
        for i, row in enumerate(table_data[1:], 1):
            # Row background for non-class, non-break cells
            even_row_bg = colors.HexColor('#e3f0fa')  # Even row background
            odd_class_bg = colors.lightblue           # Odd row class cell
            even_class_bg = colors.HexColor('#d0e6f7') # Even row class cell
            row_bg = even_row_bg if i % 2 == 0 else None
            # Set the background for the entire row if even (for non-class, non-break cells)
            if row_bg:
                style.add('BACKGROUND', (0, i), (-1, i), row_bg)
            # Override with special colors for break and class cells
            for j, cell in enumerate(row[2:], 2):
                if isinstance(cell, Paragraph) and hasattr(cell, 'text') and "BREAK" in cell.text:
                    style.add('BACKGROUND', (j, i), (j, i), colors.lightgrey)
                elif cell:  # If there's content (a class)
                    class_bg = odd_class_bg if i % 2 == 1 else even_class_bg
                    style.add('BACKGROUND', (j, i), (j, i), class_bg)

        # After creating the TableStyle, add the span commands
        for cmd in span_commands:
            style.add(*cmd)
        table.setStyle(style)
        elements.append(table)

        # Add vertical space before the N.B. note
        elements.append(Spacer(1, 6))  # 18 points = 0.25 inch

        # Add the note section as a table for proper border and wrapping
        note_text = (
            "N.B.  For any changes in the schedule, concerned coordinator/class teachers are requested to inform the students and the Dean/Program Co-ordinator, School of Science and Technology, BOU in advance."
        )
        note_table = Table(
            [[note_text]],
            colWidths=[available_width]
        )
        note_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 3, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),  # Decreased font size
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),  # Reduced padding
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(note_table)
        elements.append(Spacer(1, 6))  # Gap below the N.B. note
        elements.append(Paragraph("<br/>", styles['Normal']))

        # Add the summary table of semester courses
        semester_courses = SemesterCourse.objects.filter(semester=selected_semester).select_related('course', 'course__teacher')
        summary_data = [[
            'Course Code', 'Title', 'Number of Class', 'Course Teacher'
        ]]
        for sc in semester_courses:
            teacher_full_name = sc.course.teacher.name + ' ('+sc.course.teacher.short_name+')'
            if(sc.course.teacher.name == "N/A"):
                teacher_full_name = ""
            
            if(sc.number_of_classes == 0):
                sc.number_of_classes = ""
            

            summary_data.append([
                sc.course.code,
                sc.course.name,
                str(sc.number_of_classes),
                teacher_full_name
            ])
        summary_col_widths = [0.12 * available_width, 0.38 * available_width, 0.14 * available_width, 0.36 * available_width]
        summary_table = Table(summary_data, colWidths=summary_col_widths)
        summary_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BOX', (0, 0), (-1, -1), 2, colors.black),
        ])
        summary_table.setStyle(summary_style)
        # --- SIGNATURE FIELD SECTION ---
        signature_style = ParagraphStyle(
            'SignatureStyle',
            fontName='Helvetica',
            fontSize=10,
            alignment=TA_RIGHT,  # Right alignment
            leading=6, # Reduced line height for less gap
            spaceBefore=0,
            spaceAfter=0,
        )
        signature_style_left = ParagraphStyle(
            'SignatureStyleLeft',
            fontName='Helvetica',
            fontSize=10,
            alignment=0,  # Left alignment
            leading=6,
            spaceBefore=0,
            spaceAfter=0,
        )
        dean_line = Paragraph("Dean", signature_style)
        school_line = Paragraph("School of Science and Technology", signature_style)
        bou_line = Paragraph("Bangladesh Open University", signature_style)
        coordinator_line = Paragraph("Program Co-ordinator", signature_style_left)
        school_line_left = Paragraph("School of Science and Technology", signature_style_left)
        bou_line_left = Paragraph("Bangladesh Open University", signature_style_left)
        signature_data = [
            [dean_line],
            [school_line],
            [bou_line]
        ]
        signature_data_left = [
            [coordinator_line],
            [school_line_left],
            [bou_line_left]
        ]
        signature_table_width = 250 # Adjust as needed
        signature_table = Table(signature_data, colWidths=[signature_table_width])
        signature_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
            ('LINEABOVE', (0,0), (0,0), 1, colors.black),
            ('TOPPADDING', (0,0), (0,0), 4),
        ]))
        signature_table_left = Table(signature_data_left, colWidths=[signature_table_width])
        signature_table_left.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('LINEABOVE', (0,0), (0,0), 1, colors.black),
            ('TOPPADDING', (0,0), (0,0), 4),
        ]))
        wrapper_col_widths = [available_width - signature_table_width * 2, signature_table_width, signature_table_width]
        signature_wrapper_table = Table([[signature_table_left, '', signature_table]], colWidths=wrapper_col_widths)
        signature_wrapper_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (0,0), 'LEFT'),
            ('ALIGN', (2,0), (2,0), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        # Wrap summary table and signature together
        elements.append(KeepTogether([
            summary_table,
            Spacer(1, 48), # Gap before signature
            signature_wrapper_table
        ]))

        # Build the PDF (only once)
        doc.build(elements)
        buffer.seek(0)
        #response = FileResponse(buffer, content_type='application/pdf')
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{selected_semester.name}_Routine.pdf"'
        return response

    except Exception as e:
        return HttpResponse(f"Error generating PDF file: {str(e)}", status=500)

@require_POST
@login_required
def reset_routine(request):
    semester_id = request.POST.get('semester')
    if not semester_id:
        messages.error(request, "No semester selected for reset.")
        return redirect('generate-routine')
    try:
        semester = Semester.objects.get(id=semester_id)
        # Delete all routines for this semester, but NOT SemesterCourse
        NewRoutine.objects.filter(semester=semester).delete()
        CurrentRoutine.objects.filter(semester=semester).delete()
        messages.success(request, f"Routine reset for {semester.name} (course schedule preserved).")
    except Semester.DoesNotExist:
        messages.error(request, "Semester not found.")
    return redirect(f"{reverse('generate-routine')}?semester={semester_id}")

@login_required
def export_academic_calendar_pdf(request, semester_id):
    """Export the academic calendar as a PDF file with monthly grid layout"""
    try:
        selected_semester = Semester.objects.get(id=semester_id)
        buffer = io.BytesIO()
        
        # Use the same page size as the routine (landscape A4)
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=54,  # 0.75 inch - same as routine
            leftMargin=54,   # 0.75 inch - same as routine
            topMargin=34,    # 0.75 inch - same as routine
            bottomMargin=34  # Reduced from 54 - same as routine
        )
        page_width, page_height = landscape(A4)
        available_width = page_width - doc.leftMargin - doc.rightMargin
        elements = []

        # Calculate calendar width early for consistent alignment across all elements
        month_day_width = 0.12 * available_width  # Month/Day column
        day_width = 0.10 * available_width        # Each day column (only F,S)
        week_width = 0.12 * available_width       # Week column
        remarks_width = 0.30 * available_width    # Remarks column
        exams_width = 0.22 * available_width      # Exams column
        
        calendar_col_widths = [
            month_day_width,  # Month/Day
            day_width,        # F (Friday)
            day_width,        # S (Saturday)
            week_width,       # Week
            remarks_width,    # Remarks
            exams_width       # Exams
        ]
        
        # Calculate actual calendar width for consistent alignment
        calendar_width = sum(calendar_col_widths)

        # Define colors for different event types
        colors_dict = {
            'semester_begin': colors.HexColor('#90EE90'),  # Light Green
            'class_test': colors.HexColor('#00CED1'),  # Dark Turquoise
            'assignment': colors.HexColor('#FFA500'),  # Orange
            'semester_end': colors.HexColor('#FFB6C1'),  # Light Pink
            'final_exam': colors.HexColor('#D3D3D3'),  # Light Gray
            'holiday': colors.HexColor('#FF6B6B'),  # Red
            'makeup_class': colors.HexColor('#FFFF99'),  # Light Yellow
            'tutorial': colors.HexColor('#DDA0DD'),  # Plum
        }

        # --- HEADER IMAGE SECTION ---
        header_img_path = 'bou_routines_app/static/pdf_routine_top.png'
        try:
            # Padding for the image cell (matching routine table cell padding of 2)
            padding_for_image = 2

            # Create an Image object, scaled by width to fit within the calendar padded space
            # Height will be auto-calculated to maintain aspect ratio.
            img_obj = Image(header_img_path, width=calendar_width - (2 * padding_for_image), height=45)

            # Put the image in a single-cell table whose width spans the calendar area,
            # and apply padding to the cell to align the image correctly.
            header_img_table = Table([[img_obj]], colWidths=[calendar_width])
            header_img_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'), # Center the image horizontally within its cell
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), # Center vertically
                ('LEFTPADDING', (0,0), (-1, -1), padding_for_image),
                ('RIGHTPADDING', (0,0), (-1, -1), padding_for_image),
                ('TOPPADDING', (0,0), (-1, -1), 0), # No vertical padding here, handled by spacer
                ('BOTTOMPADDING', (0,0), (-1, -1), 0), # No vertical padding here, handled by spacer
            ]))
            elements.append(header_img_table)
        except Exception as e:
            print(f"Error loading header image: {e}")
            pass # If image not found, skip
        elements.append(Spacer(1, -4))  # Minimal gap above program name

        # Build left column (program/session/term/commencement/study center)
        header_style = ParagraphStyle(
            'HeaderStyle',
            fontName='Helvetica-Bold',
            fontSize=15,  # Reduced from 18
            alignment=1,  # Center
            leading=18,   # Reduced from 28
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_small = ParagraphStyle(
            'HeaderStyleSmall',
            fontName='Helvetica-Bold',
            fontSize=11,  # Reduced from 14
            alignment=1,
            leading=14,   # Reduced from 22
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_normal = ParagraphStyle(
            'HeaderStyleNormal',
            fontName='Helvetica',
            fontSize=10,   # Reduced from 12
            alignment=1,
            leading=11,   # Reduced from 20
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_bold = ParagraphStyle(
            'HeaderStyleBold',
            fontName='Helvetica-Bold',
            fontSize=12,  # Reduced from 15
            alignment=1,
            leading=15,   # Reduced from 24
            spaceAfter=0,
            spaceBefore=0,
        )

        left_content = []
        program_name = 'B. Sc in Computer Science and Engineering Program'
        left_content.append(Paragraph(program_name, header_style))
        session = selected_semester.session or ''
        if session:
            left_content.append(Paragraph(f'{session} Session', header_style_small))
        term = selected_semester.term or ''
        semester_full_name = selected_semester.semester_full_name or ''
        if term or semester_full_name:
            combined = f'{term} Term {semester_full_name}'.strip()
            left_content.append(Paragraph(combined, header_style_small))
        left_content.append(Spacer(1, 2))  # Reduced from 8
        left_content.append(Paragraph('Academic Calendar', header_style_bold))
        commencement = selected_semester.start_date.strftime('%d %B %Y') if selected_semester.start_date else ''
        study_center = selected_semester.study_center or ''
        if commencement:
            left_content.append(Paragraph(f'<b>Date of Commencement:</b> {commencement}', header_style_normal))
        if study_center:
            left_content.append(Paragraph(f'<b>Study Center:</b> {study_center}', header_style_normal))

        # Build right column (contact person box)
        contact_label = Paragraph(
            'Contact Person',
            ParagraphStyle(
                'ContactLabel',
                fontName='Helvetica-Bold',
                fontSize=11,
                alignment=0,  # Left align
                textColor=colors.white,
                spaceAfter=0,
                spaceBefore=0,
                leading=14,
            )
        )
        # Add 4px gap below the label using a single-cell table row with bottom padding
        contact_label_table = Table(
            [[contact_label]],
            colWidths=[180],
            hAlign='RIGHT',
            style=TableStyle([
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), -3),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ])
        )
        contact_info_lines = []
        if selected_semester.contact_person:
            contact_info_lines.append(selected_semester.contact_person)
        if selected_semester.contact_person_designation:
            contact_info_lines.append(selected_semester.contact_person_designation)
        contact_info_lines.append('School of Science and Technology')
        contact_info_lines.append('Bangladesh Open University')
        if selected_semester.contact_person_phone:
            contact_info_lines.append(f'Phone/Whatsapp: {selected_semester.contact_person_phone}')
        if selected_semester.contact_person_email:
            contact_info_lines.append(f'email:{selected_semester.contact_person_email}')
        contact_info_para = Paragraph(
            '<br/>'.join(contact_info_lines),
            ParagraphStyle(
                'ContactBox',
                fontName='Helvetica',
                fontSize=10,
                alignment=0,  # Left align
                textColor=colors.black,
                leftIndent=2,
                leading=10,
                spaceBefore=0,
                spaceAfter=0,
            )
        )
        contact_table = Table(
            [[contact_label_table], [contact_info_para]],
            colWidths=[180],
        )
        contact_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),  # Single, lighter border
            ('ROUNDED', (0, 0), (-1, -1), 6),  # Rounded corners
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#2c3e50')),  # Label bg
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (0, 0), 6),  # Label row
            ('BOTTOMPADDING', (0, 0), (0, 0), 4),  # Label row
            ('TOPPADDING', (0, 1), (0, 1), 4),  # Info row
            ('BOTTOMPADDING', (0, 1), (0, 1), 6),  # Info row
        ]))

        # Vertically center the left header content to match the contact box
        left_box_table = Table(
            [[left_content]],
            colWidths=[calendar_width-180],
            style=TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ])
        )
        two_col_table = Table(
            [[left_box_table, contact_table]],
            colWidths=[calendar_width-180, 180],
        )
        two_col_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
            ('VALIGN', (1, 0), (1, 0), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(Spacer(1, 4))  # Add slight gap before contact box
        elements.append(two_col_table)
        elements.append(Spacer(1, 4))  # Reduced from 16

        # Use semester's start and end dates as the date range
        if selected_semester.start_date and selected_semester.end_date:
            calendar_start = selected_semester.start_date
            calendar_end = selected_semester.end_date
        else:
            # Fallback to current academic year if semester dates not set
            current_year = datetime.now().year
            calendar_start = datetime(current_year, 7, 1).date()
            calendar_end = datetime(current_year + 1, 6, 30).date()

        # Define academic events based on semester dates
        events_calendar = {}
        
        def get_friday_saturday_of_week(target_date):
            """Get Friday and Saturday dates for the week containing target_date"""
            # Find the Friday of the week containing target_date
            days_since_monday = target_date.weekday()
            friday_date = target_date + timedelta(days=(4 - days_since_monday))
            saturday_date = friday_date + timedelta(days=1)
            return friday_date, saturday_date
        
        try:
            if selected_semester.start_date and selected_semester.end_date:
                semester_start = selected_semester.start_date
                semester_end = selected_semester.end_date
                
                # Mark semester begin and end
                events_calendar[semester_start] = ('semester_begin', 'Semester Begins')
                events_calendar[semester_end] = ('semester_end', 'Class Ends')
                
                # Calculate key academic events based on weeks
                duration_days = (semester_end - semester_start).days
                
                # First Class Test (6th week) - mark both Friday and Saturday
                first_test_week = semester_start + timedelta(weeks=6)
                if first_test_week <= semester_end:
                    friday, saturday = get_friday_saturday_of_week(first_test_week)
                    events_calendar[friday] = ('class_test', 'First Class Test')
                    events_calendar[saturday] = ('class_test', 'First Class Test')
                
                # Second Class Test (10th week) - mark both Friday and Saturday
                second_test_week = semester_start + timedelta(weeks=10)
                if second_test_week <= semester_end:
                    friday, saturday = get_friday_saturday_of_week(second_test_week)
                    events_calendar[friday] = ('class_test', 'Second Class Test')
                    events_calendar[saturday] = ('class_test', 'Second Class Test')
                
                # First Assignment (4th week) - mark both Friday and Saturday
                first_assignment_week = semester_start + timedelta(weeks=4)
                if first_assignment_week <= semester_end:
                    friday, saturday = get_friday_saturday_of_week(first_assignment_week)
                    events_calendar[friday] = ('assignment', 'First Assignment')
                    events_calendar[saturday] = ('assignment', 'First Assignment')
                
                # Second Assignment (8th week) - mark both Friday and Saturday
                second_assignment_week = semester_start + timedelta(weeks=8)
                if second_assignment_week <= semester_end:
                    friday, saturday = get_friday_saturday_of_week(second_assignment_week)
                    events_calendar[friday] = ('assignment', 'Second Assignment')
                    events_calendar[saturday] = ('assignment', 'Second Assignment')
                
                # Third Assignment (12th week) - mark both Friday and Saturday
                third_assignment_week = semester_start + timedelta(weeks=12)
                if third_assignment_week <= semester_end:
                    friday, saturday = get_friday_saturday_of_week(third_assignment_week)
                    events_calendar[friday] = ('assignment', 'Third Assignment')
                    events_calendar[saturday] = ('assignment', 'Third Assignment')
                
                # Add holidays from semester
                if selected_semester.holidays:
                    holiday_dates = [
                        datetime.strptime(date.strip(), "%Y-%m-%d").date()
                        for date in selected_semester.holidays.split(',')
                        if date.strip()
                    ]
                    for holiday_date in holiday_dates:
                        if calendar_start <= holiday_date <= calendar_end:
                            events_calendar[holiday_date] = ('holiday', 'Holiday')
                
                # Add makeup/extra classes from semester and determine final exam date
                latest_makeup_date = None
                if selected_semester.makeup_dates:
                    makeup_dates = [
                        datetime.strptime(date.strip(), "%Y-%m-%d").date()
                        for date in selected_semester.makeup_dates.split(',')
                        if date.strip()
                    ]
                    for makeup_date in makeup_dates:
                        # Include makeup dates even if they're after semester end
                        events_calendar[makeup_date] = ('makeup_class', 'Makeup/Extra Class')
                        if latest_makeup_date is None or makeup_date > latest_makeup_date:
                            latest_makeup_date = makeup_date
                
                # Set Tentative Semester Final Exam date - mark 4 weeks starting from the first exam week
                if latest_makeup_date:
                    # If there are makeup classes, final exam is 1 week after the latest makeup date
                    final_exam_week = latest_makeup_date + timedelta(weeks=1)
                else:
                    # If no makeup classes, final exam is 1 week after semester end
                    final_exam_week = semester_end + timedelta(weeks=1)
                
                # Calculate the end of the 4-week final exam period
                final_exam_end_week = final_exam_week + timedelta(weeks=3)  # 4 weeks total (0, 1, 2, 3)
                final_exam_end_saturday = get_friday_saturday_of_week(final_exam_end_week)[1]  # Get Saturday of the last week
                
                # Mark 4 weeks for final exam period (both Friday and Saturday for each week)
                for week_offset in range(4):
                    current_exam_week = final_exam_week + timedelta(weeks=week_offset)
                    friday, saturday = get_friday_saturday_of_week(current_exam_week)
                    events_calendar[friday] = ('final_exam', 'Tentative Semester Final Exam')
                    events_calendar[saturday] = ('final_exam', 'Tentative Semester Final Exam')
                
        except Exception as e:
            # If there's an error calculating events, continue with empty events
            pass

        # Create monthly calendar grids with error handling
        months_data = []
        cross_month_weeks = {}  # Track weeks that span across months
        
        try:
            # Calculate the smart end date for calendar generation
            # Use the end of the 4-week final exam period if it exists, otherwise use the regular extended_end
            smart_calendar_end = calendar_end
            
            # Check if we have final exam events and find the actual end of the final exam period
            final_exam_dates = [date for date, (event_type, _) in events_calendar.items() if event_type == 'final_exam']
            if final_exam_dates:
                # Use the latest final exam date as our smart cutoff
                smart_calendar_end = max(final_exam_dates)
            else:
                # Fallback: extend calendar range to include all events (makeup dates, etc.)
                for event_date, (event_type, _) in events_calendar.items():
                    if event_date > smart_calendar_end:
                        smart_calendar_end = event_date
            
            current_date = calendar_start.replace(day=1)  # Start from the 1st of the starting month
            
            # Safety check to prevent infinite loops
            max_months = 24  # Maximum 2 years
            month_count = 0
            
            while current_date <= smart_calendar_end and month_count < max_months:
                month_name = current_date.strftime('%B').upper()
                year = current_date.year
                
                # Get calendar for this month
                cal = calendar.monthcalendar(year, current_date.month)
                
                # For the first month, create the overall header
                if month_count == 0:
                    # Create the main header rows - two-row structure
                    header_row_1 = ['Month', 'Day & Date', '', 'Weeks', 'Events', 'Exams']
                    header_row_2 = ['', 'F', 'S', '', '', '']
                    months_data.append([header_row_1])
                    months_data.append([header_row_2])
                
                # Calculate how many week rows this month will have
                num_weeks = len(cal)
                
                # Track if we've completed all necessary events in this month
                month_has_relevant_events = False
                first_week_of_month_added = False
                
                # Add month rows - process weeks with cross-month awareness
                for week_num, week in enumerate(cal):
                    # Extract Friday and Saturday information
                    friday_day = week[4] if len(week) > 4 and week[4] != 0 else None
                    saturday_day = week[5] if len(week) > 5 and week[5] != 0 else None
                    friday_date = None
                    saturday_date = None
                    
                    # Check if this week contains any dates we need to show
                    week_has_relevant_events = False
                    if friday_day:
                        friday_date = datetime(year, current_date.month, friday_day).date()
                        if friday_date <= smart_calendar_end:
                            week_has_relevant_events = True
                    
                    if saturday_day:
                        saturday_date = datetime(year, current_date.month, saturday_day).date()
                        if saturday_date <= smart_calendar_end:
                            week_has_relevant_events = True
                    
                    # Skip this week if it has no relevant events
                    if not week_has_relevant_events:
                        continue
                    
                    month_has_relevant_events = True
                    
                    # Calculate week identifier for cross-month tracking
                    week_id = None
                    if friday_date and selected_semester.start_date:
                        days_diff = (friday_date - selected_semester.start_date).days
                        week_id = (days_diff // 7) + 1
                    elif saturday_date and selected_semester.start_date:
                        # If no Friday, calculate from Saturday (subtract 1 day to get Friday equivalent)
                        adjusted_date = saturday_date - timedelta(days=1)
                        days_diff = (adjusted_date - selected_semester.start_date).days
                        week_id = (days_diff // 7) + 1
                    
                    # Determine if this is a cross-month week continuation
                    is_cross_month_continuation = week_id and week_id in cross_month_weeks
                    
                    # Handle month column display
                    if not first_week_of_month_added and not is_cross_month_continuation:
                        # First week row added for this month - show month name and year
                        first_week_of_month_added = True
                        month_style = ParagraphStyle(
                            'MonthStyle',
                            fontName='Helvetica-Bold',
                            fontSize=10,
                            alignment=1,  # Center
                            leading=12,
                        )
                        month_year_para = Paragraph(f"{month_name}<br/>{year}", month_style)
                        week_data = [month_year_para]
                    else:
                        # Other week rows for this month - empty first column
                        week_data = ['']
                    
                    # Add day numbers with event markers
                    friday_str = ''
                    saturday_str = ''
                    
                    if friday_day:
                        friday_str = str(friday_day)
                        if friday_date in events_calendar:
                            event_type, description = events_calendar[friday_date]
                            if event_type == 'semester_begin':
                                friday_str += ' (SB)'
                            elif event_type == 'semester_end':
                                friday_str += ' (CE)'
                            elif event_type == 'class_test':
                                friday_str += ' (CT)'
                            elif event_type == 'assignment':
                                friday_str += ' (Assn.)'
                            elif event_type == 'final_exam':
                                friday_str += ' (FE)'
                            elif event_type == 'holiday':
                                friday_str += ' (H)'
                            elif event_type == 'makeup_class':
                                friday_str += ' (MC)'
                    
                    if saturday_day:
                        saturday_str = str(saturday_day)
                        if saturday_date in events_calendar:
                            event_type, description = events_calendar[saturday_date]
                            if event_type == 'semester_begin':
                                saturday_str += ' (SB)'
                            elif event_type == 'semester_end':
                                saturday_str += ' (CE)'
                            elif event_type == 'class_test':
                                saturday_str += ' (CT)'
                            elif event_type == 'assignment':
                                saturday_str += ' (Assn.)'
                            elif event_type == 'final_exam':
                                saturday_str += ' (FE)'
                            elif event_type == 'holiday':
                                saturday_str += ' (H)'
                            elif event_type == 'makeup_class':
                                saturday_str += ' (MC)'
                    
                    week_data.extend([friday_str, saturday_str])
                    
                    # Calculate week number based on semester start date
                    week_number = ''
                    if week_id and week_id > 0:
                        if week_id == 1:
                            week_number = '1st Week'
                        elif week_id == 2:
                            week_number = '2nd Week'
                        elif week_id == 3:
                            week_number = '3rd Week'
                        else:
                            week_number = f'{week_id}th Week'
                    
                    # Collect remarks and exams for this week part
                    remarks_set = set()
                    exams_set = set()
                    
                    # Check events for Friday and Saturday
                    for date_obj in [friday_date, saturday_date]:
                        if date_obj and date_obj in events_calendar:
                            event_type, description = events_calendar[date_obj]
                            if event_type in ['class_test', 'final_exam']:
                                exams_set.add(description)
                            else:
                                remarks_set.add(description)
                    
                    # Handle cross-month week logic
                    if is_cross_month_continuation:
                        # This is a continuation of a week from previous month
                        prev_week_data = cross_month_weeks[week_id]
                        
                        # Merge events from both parts of the week
                        remarks_set.update(prev_week_data['remarks_set'])
                        exams_set.update(prev_week_data['exams_set'])
                        
                        # Mark the previous row for spanning
                        prev_week_data['needs_spanning'] = True
                        prev_week_data['span_end_row'] = len(months_data)  # Current row index
                        
                        # Use empty week number for continuation row (will be spanned)
                        week_number = ''
                    else:
                        # Check if this week will continue into next month
                        week_continues_next_month = False
                        if friday_day and not saturday_day:
                            # Friday exists but Saturday is missing - likely continues next month
                            week_continues_next_month = True
                        elif not friday_day and saturday_day:
                            # Saturday exists but Friday is missing - this is a continuation from previous month
                            # This should have been handled by is_cross_month_continuation, but just in case
                            pass
                        
                        if week_continues_next_month and week_id:
                            # Store this week data for merging with next month
                            cross_month_weeks[week_id] = {
                                'remarks_set': remarks_set.copy(),
                                'exams_set': exams_set.copy(),
                                'week_number': week_number,
                                'start_row': len(months_data),  # Current row index
                                'needs_spanning': False
                            }
                    
                    # Convert sets to comma-separated strings
                    remarks = ', '.join(sorted(remarks_set)) if remarks_set else ''
                    exams = ', '.join(sorted(exams_set)) if exams_set else ''
                    
                    week_data.extend([week_number, remarks, exams])
                    months_data.append([week_data])
                
                # If this month had no relevant events, we can stop here
                if not month_has_relevant_events:
                    break
                
                month_count += 1
                
                # Move to next month
                try:
                    if current_date.month == 12:
                        current_date = current_date.replace(year=current_date.year + 1, month=1)
                    else:
                        current_date = current_date.replace(month=current_date.month + 1)
                except Exception:
                    # If there's an error moving to next month, break the loop
                    break
                    
        except Exception as e:
            # If there's any error in calendar generation, create a fallback
            months_data = []

        # Create the main calendar table - flatten the structure
        all_calendar_data = []
        for month_week_data in months_data:
            all_calendar_data.extend(month_week_data)

        # Use pre-calculated column widths for consistent alignment
        col_widths = calendar_col_widths
        
        # Ensure we have data to create the table
        if not all_calendar_data:
            # If no calendar data, create a simple message
            all_calendar_data = [['No calendar data available for the selected semester date range.']]
            col_widths = [calendar_width]
        
        calendar_table = Table(all_calendar_data, colWidths=col_widths)
        
        # Style the calendar table with event colors
        calendar_style = []
        
        # Only add styling if we have actual calendar data
        if all_calendar_data:
            # Style the main header rows (first two rows)
            calendar_style.extend([
                # First header row
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                # Second header row
                ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#4472C4')),
                ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
                ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 1), (-1, 1), 10),
                ('ALIGN', (0, 1), (-1, 1), 'CENTER'),
                ('VALIGN', (0, 1), (-1, 1), 'MIDDLE'),
                # Merge cells for header structure
                ('SPAN', (0, 0), (0, 1)),  # Month column spans both rows
                ('SPAN', (1, 0), (2, 0)),  # Day spans across F and S in first row
                ('SPAN', (3, 0), (3, 1)),  # Weeks column spans both rows
                ('SPAN', (4, 0), (4, 1)),  # Remarks column spans both rows
                ('SPAN', (5, 0), (5, 1)),  # Exams column spans both rows
            ])
            
            # Process each row after the header (starting from row 2 now)
            current_month_start_row = None
            current_month_rows = 0
            
            for row_idx in range(2, len(all_calendar_data)):
                row_data = all_calendar_data[row_idx]
                
                # Check if this is the start of a new month (first column has Paragraph object)
                if len(row_data) > 0 and row_data[0] and hasattr(row_data[0], '__class__') and 'Paragraph' in str(type(row_data[0])):
                    # This is a month header row with Paragraph
                    current_month_start_row = row_idx
                    current_month_rows = 1
                    
                    # Style month/year cell specially (Paragraph objects don't need font styling)
                    calendar_style.extend([
                        ('VALIGN', (0, row_idx), (0, row_idx), 'MIDDLE'),
                        ('BACKGROUND', (0, row_idx), (0, row_idx), colors.HexColor('#E7E6E6')),
                    ])
                elif current_month_start_row is not None:
                    # This is a continuation row for the current month
                    current_month_rows += 1
                
                # Apply general row styling
                calendar_style.extend([
                    ('FONTNAME', (1, row_idx), (-1, row_idx), 'Helvetica'),
                    ('FONTSIZE', (1, row_idx), (-1, row_idx), 10),
                    ('ALIGN', (1, row_idx), (2, row_idx), 'CENTER'),  # Only F and S columns (1,2)
                    ('VALIGN', (0, row_idx), (-1, row_idx), 'MIDDLE'),
                    ('GRID', (0, row_idx), (-1, row_idx), 0.5, colors.black),
                    ('ROWHEIGHT', (0, row_idx), (-1, row_idx), 16),  # Reduced row height for compactness
                ])
                
                # Check for events in this week and apply row coloring
                if len(row_data) >= 6:  # Ensure we have all columns including exams
                    week_event_color = None
                    has_exam_event = False
                    
                    # Check if this row has exam events by looking at the exams column (index 5)
                    exams_column = row_data[5] if len(row_data) > 5 else ''
                    if exams_column and exams_column.strip():
                        has_exam_event = True
                    
                    # Extract month and year for this row
                    current_year = datetime.now().year  # Default fallback
                    current_month = 1  # Default fallback
                    
                    # Find the month/year from current or previous month header
                    if current_month_start_row is not None:
                        month_header_data = all_calendar_data[current_month_start_row]
                        if len(month_header_data) > 0 and month_header_data[0]:
                            # Handle Paragraph objects
                            if hasattr(month_header_data[0], '__class__') and 'Paragraph' in str(type(month_header_data[0])):
                                # Extract text from Paragraph object
                                para_text = str(month_header_data[0])
                                # Look for month and year in the paragraph text
                                month_match = re.search(r'(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)', para_text)
                                year_match = re.search(r'(\d{4})', para_text)
                                if month_match and year_match:
                                    month_name = month_match.group(1)
                                    current_year = int(year_match.group(1))
                                    month_names = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE',
                                                 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
                                    if month_name in month_names:
                                        current_month = month_names.index(month_name) + 1
                            elif '\n' in str(month_header_data[0]):
                                # Handle plain text with newlines
                                month_year_text = str(month_header_data[0])
                                parts = month_year_text.split('\n')
                                if len(parts) == 2:
                                    try:
                                        month_name = parts[0].strip()
                                        current_year = int(parts[1].strip())
                                        month_names = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE',
                                                     'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
                                        if month_name in month_names:
                                            current_month = month_names.index(month_name) + 1
                                    except (ValueError, IndexError):
                                        pass
                    
                    # Check Friday and Saturday columns for any events (columns 1 and 2)
                    non_holiday_event_color = None
                    for day_col in range(1, 3):  # Friday and Saturday are in columns 1-2
                        if day_col < len(row_data):
                            day_text = row_data[day_col]
                            if day_text and day_text.strip():
                                try:
                                    day_num = int(str(day_text).split()[0])  # Get day number before any markers
                                    date_obj = datetime(current_year, current_month, day_num).date()
                                    if date_obj in events_calendar:
                                        event_type, _ = events_calendar[date_obj]
                                        if event_type == 'holiday':
                                            # For holidays, apply red color only to the specific date cell
                                            calendar_style.append(
                                                ('TEXTCOLOR', (day_col, row_idx), (day_col, row_idx), colors.HexColor('#FF0000'))
                                            )
                                        elif event_type in colors_dict and non_holiday_event_color is None:
                                            # For non-holiday events, store color for row highlighting
                                            non_holiday_event_color = colors_dict[event_type]
                                except (ValueError, TypeError):
                                    continue
                    
                    # Apply background color for non-holiday events
                    if non_holiday_event_color:
                        if has_exam_event:
                            # For exam events: highlight entire row including Exams column (columns 1-5)
                            calendar_style.append(
                                ('BACKGROUND', (1, row_idx), (-1, row_idx), non_holiday_event_color)
                            )
                        else:
                            # For non-exam events: highlight only up to Remarks column (columns 1-4)
                            calendar_style.append(
                                ('BACKGROUND', (1, row_idx), (4, row_idx), non_holiday_event_color)
                            )
                    
                    # Store color for potential cross-month week matching
                    if non_holiday_event_color:
                        # Store the row's color information for cross-month spanning
                        all_calendar_data[row_idx].append(non_holiday_event_color)
                        all_calendar_data[row_idx].append(has_exam_event)
            
            # Track months for cell spanning in first column
            month_ranges = []
            current_month_start = None
            
            for row_idx in range(2, len(all_calendar_data)):  # Start from row 2 due to two-row header
                row_data = all_calendar_data[row_idx]
                
                # Check for month start (Paragraph object or text with newlines)
                is_month_start = False
                if len(row_data) > 0 and row_data[0]:
                    if hasattr(row_data[0], '__class__') and 'Paragraph' in str(type(row_data[0])):
                        is_month_start = True
                    elif '\n' in str(row_data[0]):
                        is_month_start = True
                
                if is_month_start:
                    # This is a month start - close previous month if exists
                    if current_month_start is not None:
                        month_ranges.append((current_month_start, row_idx - 1))
                    current_month_start = row_idx
            
            # Close the last month
            if current_month_start is not None:
                month_ranges.append((current_month_start, len(all_calendar_data) - 1))
            
            # Apply cell spanning for months (only if month spans multiple rows)
            for start_row, end_row in month_ranges:
                if end_row > start_row:  # Only span if more than one row
                    calendar_style.append(
                        ('SPAN', (0, start_row), (0, end_row))
                    )
            
            # Apply cell spanning for cross-month weeks
            for week_id, week_data in cross_month_weeks.items():
                if week_data.get('needs_spanning', False):
                    start_row = week_data['start_row']
                    end_row = week_data['span_end_row']
                    
                    # Span the week number column (column 3)
                    calendar_style.append(
                        ('SPAN', (3, start_row), (3, end_row))
                    )
                    
                    # Span the remarks column (column 4) if both rows have the same remarks
                    start_row_data = all_calendar_data[start_row]
                    end_row_data = all_calendar_data[end_row]
                    if (len(start_row_data) > 4 and len(end_row_data) > 4 and 
                        start_row_data[4] == end_row_data[4]):
                        calendar_style.append(
                            ('SPAN', (4, start_row), (4, end_row))
                        )
                    
                    # Span the exams column (column 5) if both rows have the same exams
                    if (len(start_row_data) > 5 and len(end_row_data) > 5 and 
                        start_row_data[5] == end_row_data[5]):
                        calendar_style.append(
                            ('SPAN', (5, start_row), (5, end_row))
                        )
                    
                    # Apply same background color to both parts of cross-month weeks
                    start_row_color = None
                    start_row_has_exam = False
                    end_row_color = None
                    end_row_has_exam = False
                    
                    # Check if rows have color information stored
                    if len(start_row_data) > 7:  # Color info at index 6, exam info at index 7
                        start_row_color = start_row_data[6]
                        start_row_has_exam = start_row_data[7]
                    if len(end_row_data) > 7:
                        end_row_color = end_row_data[6]
                        end_row_has_exam = end_row_data[7]
                    
                    # Use color from either row that has an event (priority to exam events)
                    final_color = None
                    final_has_exam = False
                    
                    if start_row_has_exam and start_row_color:
                        final_color = start_row_color
                        final_has_exam = True
                    elif end_row_has_exam and end_row_color:
                        final_color = end_row_color
                        final_has_exam = True
                    elif start_row_color:
                        final_color = start_row_color
                        final_has_exam = start_row_has_exam
                    elif end_row_color:
                        final_color = end_row_color
                        final_has_exam = end_row_has_exam
                    
                    # Apply the same background color to both rows
                    if final_color:
                        if final_has_exam:
                            # For exam events: highlight entire row including Exams column (columns 1-5)
                            calendar_style.append(
                                ('BACKGROUND', (1, start_row), (-1, start_row), final_color)
                            )
                            calendar_style.append(
                                ('BACKGROUND', (1, end_row), (-1, end_row), final_color)
                            )
                        else:
                            # For non-exam events: highlight only up to Remarks column (columns 1-4)
                            calendar_style.append(
                                ('BACKGROUND', (1, start_row), (4, start_row), final_color)
                            )
                            calendar_style.append(
                                ('BACKGROUND', (1, end_row), (4, end_row), final_color)
                            )
            
            # Track and merge cells for 4-week final exam period in Exams column
            final_exam_rows = []
            current_year = datetime.now().year  # Default fallback
            current_month = 1  # Default fallback
            current_month_start_row = None
            
            for row_idx in range(2, len(all_calendar_data)):  # Start from row 2 due to two-row header
                row_data = all_calendar_data[row_idx]
                
                # Update current month context
                if len(row_data) > 0 and row_data[0]:
                    if hasattr(row_data[0], '__class__') and 'Paragraph' in str(type(row_data[0])):
                        current_month_start_row = row_idx
                        # Extract month and year from Paragraph
                        para_text = str(row_data[0])
                        month_match = re.search(r'(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)', para_text)
                        year_match = re.search(r'(\d{4})', para_text)
                        if month_match and year_match:
                            month_name = month_match.group(1)
                            current_year = int(year_match.group(1))
                            month_names = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE',
                                         'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
                            if month_name in month_names:
                                current_month = month_names.index(month_name) + 1
                
                # Check if this row has final exam events
                if len(row_data) >= 6:  # Ensure we have all columns including exams
                    exams_column = row_data[5] if len(row_data) > 5 else ''
                    if exams_column and 'Tentative Semester Final Exam' in str(exams_column):
                        final_exam_rows.append(row_idx)
            
            # Apply cell spanning for final exam period in Exams column (column 5)
            if len(final_exam_rows) > 1:
                # Sort rows to ensure correct spanning
                final_exam_rows.sort()
                start_row = final_exam_rows[0]
                end_row = final_exam_rows[-1]
                calendar_style.append(
                    ('SPAN', (5, start_row), (5, end_row))  # Span column 5 (Exams) across all final exam rows
                )
        
        # Add borders
        calendar_style.extend([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ])
        
        calendar_table.setStyle(TableStyle(calendar_style))
        elements.append(calendar_table)
        
        # Add legend with reduced spacing
        elements.append(Spacer(1, 4))  # Reduced from 20 to 8
        
        # Create single-row legend with all items
        legend_data = [[
            Table([['Semester Begin (SB)']], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors_dict['semester_begin']),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOX', (0,0), (-1,-1), 1, colors.black),
            ])),
            Table([['Class Test (CT)']], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors_dict['class_test']),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOX', (0,0), (-1,-1), 1, colors.black),
            ])),
            Table([['Assignment (Assn.)']], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors_dict['assignment']),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOX', (0,0), (-1,-1), 1, colors.black),
            ])),
            Table([['Class Ends (CE)']], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors_dict['semester_end']),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOX', (0,0), (-1,-1), 1, colors.black),
            ])),
            Table([['Final Exam (FE)']], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors_dict['final_exam']),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOX', (0,0), (-1,-1), 1, colors.black),
            ])),
            Table([['Holiday (H)']], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors_dict['holiday']),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOX', (0,0), (-1,-1), 1, colors.black),
            ])),
            Table([['Makeup Class (MC)']], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors_dict['makeup_class']),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOX', (0,0), (-1,-1), 1, colors.black),
            ])),
        ]]
        
        # Calculate column widths to match calendar width - 7 columns now
        legend_col_width = calendar_width / 7
        legend_table = Table(legend_data, colWidths=[legend_col_width] * 7)
        legend_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),   # Uniform left padding
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),  # Uniform right padding
            ('TOPPADDING', (0, 0), (-1, -1), 2),    # Uniform top padding
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2), # Uniform bottom padding
        ]))
        elements.append(legend_table)

        # --- SIGNATURE FIELD SECTION (same as routine) ---
        elements.append(Spacer(1, 48)) # Gap before signature
        
        signature_style = ParagraphStyle(
            'SignatureStyle',
            fontName='Helvetica',
            fontSize=10,
            alignment=TA_RIGHT,  # Right alignment
            leading=4, # Reduced line height for less gap
            spaceBefore=0,
            spaceAfter=0,
        )
        signature_style_left = ParagraphStyle(
            'SignatureStyleLeft',
            fontName='Helvetica',
            fontSize=10,
            alignment=0,  # Left alignment
            leading=4,
            spaceBefore=0,
            spaceAfter=0,
        )
        dean_line = Paragraph("Dean", signature_style)
        school_line = Paragraph("School of Science and Technology", signature_style)
        bou_line = Paragraph("Bangladesh Open University", signature_style)
        coordinator_line = Paragraph("Program Co-ordinator", signature_style_left)
        school_line_left = Paragraph("School of Science and Technology", signature_style_left)
        bou_line_left = Paragraph("Bangladesh Open University", signature_style_left)
        signature_data = [
            [dean_line],
            [school_line],
            [bou_line]
        ]
        signature_data_left = [
            [coordinator_line],
            [school_line_left],
            [bou_line_left]
        ]
        signature_table_width = 250 # Adjust as needed
        signature_table = Table(signature_data, colWidths=[signature_table_width])
        signature_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
            ('LINEABOVE', (0,0), (0,0), 1, colors.black),
            ('TOPPADDING', (0,0), (0,0), 4),
        ]))
        signature_table_left = Table(signature_data_left, colWidths=[signature_table_width])
        signature_table_left.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('LINEABOVE', (0,0), (0,0), 1, colors.black),
            ('TOPPADDING', (0,0), (0,0), 4),
        ]))
        wrapper_col_widths = [calendar_width - signature_table_width * 2, signature_table_width, signature_table_width]
        signature_wrapper_table = Table([[signature_table_left, '', signature_table]], colWidths=wrapper_col_widths)
        signature_wrapper_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (0,0), 'LEFT'),
            ('ALIGN', (2,0), (2,0), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        elements.append(signature_wrapper_table)

        # Build the PDF
        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{selected_semester.name}_Academic_Calendar.pdf"'
        return response
    except Exception as e:
        return HttpResponse(f"Error generating Academic Calendar PDF: {str(e)}", status=500)

# Attendance Management Views

def check_teacher_permission(user, permission_codename):
    """Check if a user has a specific permission"""
    return user.has_perm(f'bou_routines_app.{permission_codename}')

def get_teacher_from_user(user):
    """Get teacher profile from user"""
    try:
        return user.teacher
    except Teacher.DoesNotExist:
        return None

@login_required
def attendance_calendar(request):
    """Display attendance calendar for marking attendance"""
    # Check if user is admin/superuser or has attendance permission
    if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_mark_attendance')):
        messages.error(request, "You don't have permission to access attendance management.")
        return redirect('generate-routine')
    
    # Get teacher from logged-in user (optional for admin users)
    teacher = get_teacher_from_user(request.user)
    if not teacher and not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "You don't have a teacher profile. Please contact administrator.")
        return redirect('generate-routine')
    
    # Get all curricula
    curricula = Curriculum.objects.filter(is_active=True).order_by('name')
    
    # Get selected curriculum from request
    selected_curriculum_id = request.GET.get('curriculum') or request.POST.get('curriculum')
    selected_curriculum = None
    
    if selected_curriculum_id:
        try:
            # Convert to integer to ensure type consistency
            selected_curriculum_id = int(selected_curriculum_id)
            selected_curriculum = Curriculum.objects.get(id=selected_curriculum_id)
        except (Curriculum.DoesNotExist, ValueError):
            selected_curriculum = None
            selected_curriculum_id = None
    
    # If no curriculum selected, use the Old Curriculum by default
    if not selected_curriculum and curricula.exists():
        try:
            selected_curriculum = Curriculum.objects.get(code='OLD')
            selected_curriculum_id = selected_curriculum.id
        except Curriculum.DoesNotExist:
            selected_curriculum = curricula.first()
            selected_curriculum_id = selected_curriculum.id if selected_curriculum else None
    
    # Filter semesters by selected curriculum
    if selected_curriculum:
        semesters = Semester.objects.filter(curriculum=selected_curriculum).order_by('order', 'name')
    else:
        semesters = Semester.objects.all().order_by('order', 'name')
    
    # Get semester and course from request
    semester_id = request.GET.get('semester')
    course_id = request.GET.get('course')
    selected_date = request.GET.get('date')
    
    # Filter courses by semester and teacher
    courses_queryset = Course.objects.none()  # Default to empty queryset
    if semester_id:
        if teacher:
            # For teachers, show only their courses in the selected semester
            courses_queryset = Course.objects.filter(
                teacher=teacher,
                semestercourse__semester_id=semester_id
            ).distinct()
        else:
            # For admin users, show all courses in the selected semester
            courses_queryset = Course.objects.filter(
                semestercourse__semester_id=semester_id
            ).distinct()
    
    context = {
        'teacher': teacher,
        'is_admin': request.user.is_superuser or request.user.is_staff,
        'curricula': curricula,
        'selected_curriculum_id': selected_curriculum_id,
        'selected_curriculum': selected_curriculum,
        'semesters': semesters,
        'courses': courses_queryset.order_by('code'),
        'selected_semester_id': semester_id,
        'selected_course_id': course_id,
        'selected_date': selected_date,
    }
    
    if semester_id and course_id:
        try:
            semester = Semester.objects.get(id=semester_id)
            if teacher:
                course = Course.objects.get(id=course_id, teacher=teacher)
            else:
                course = Course.objects.get(id=course_id)
            
            # Get students for this semester with custom sorting
            # Sort by first two digits (descending), then last three digits (ascending)
            from django.db.models import Case, When, IntegerField
            from django.db.models.functions import Cast, Substr
            
            students = Student.objects.filter(semesters=semester).extra(
                select={
                    'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                    'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
                }
            ).order_by('-first_two_digits', 'last_three_digits')
            
            # Get actual course schedule dates from CurrentRoutine table for this specific course
            from datetime import datetime, timedelta
            from bou_routines_app.models import CurrentRoutine
            
            # Get the course's scheduled days from CurrentRoutine table
            course_routines = CurrentRoutine.objects.filter(
                course=course,
                semester=semester
            ).values_list('day', flat=True).distinct()
            
            # Get actual class duration from routine data
            actual_class_duration = None
            class_ratio = 1.0
            try:
                # Get a sample routine entry to determine actual class duration
                sample_routine = NewRoutine.objects.filter(
                    course=course,
                    semester=semester
                ).first()
                
                if sample_routine and sample_routine.start_time and sample_routine.end_time:
                    # Calculate actual duration in minutes
                    start_time = sample_routine.start_time
                    end_time = sample_routine.end_time
                    start_minutes = start_time.hour * 60 + start_time.minute
                    end_minutes = end_time.hour * 60 + end_time.minute
                    actual_class_duration = end_minutes - start_minutes
                    
                    # Calculate class ratio
                    if course.is_lab:
                        standard_duration = semester.lab_class_duration_minutes
                    else:
                        standard_duration = semester.theory_class_duration_minutes
                    
                    if standard_duration > 0:
                        class_ratio = actual_class_duration / standard_duration
                    
                    print(f"DEBUG: Actual class duration for {course.name}: {actual_class_duration} minutes")
                    print(f"DEBUG: Standard duration: {standard_duration} minutes")
                    print(f"DEBUG: Class ratio: {class_ratio}")
                else:
                    # Fallback to semester default duration
                    if course.is_lab:
                        actual_class_duration = semester.lab_class_duration_minutes
                    else:
                        actual_class_duration = semester.theory_class_duration_minutes
                    class_ratio = 1.0
                    print(f"DEBUG: Using semester default duration for {course.name}: {actual_class_duration} minutes")
            except Exception as e:
                print(f"DEBUG: Error getting actual class duration: {e}")
                # Fallback to semester default duration
                if course.is_lab:
                    actual_class_duration = semester.lab_class_duration_minutes
                else:
                    actual_class_duration = semester.theory_class_duration_minutes
                class_ratio = 1.0
            
            print(f"DEBUG: Course {course.name} is scheduled on days: {list(course_routines)}")
            
            semester_dates = []
            current_date = semester.start_date
            end_date = semester.end_date
            
            # Parse holiday dates from semester
            holiday_dates = set()
            if semester.holidays:
                for date_str in semester.holidays.split(','):
                    if date_str.strip():
                        try:
                            holiday_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
                            holiday_dates.add(holiday_date)
                        except ValueError:
                            pass  # Skip invalid date formats
            
            # Parse makeup dates from semester
            makeup_dates = set()
            if semester.makeup_dates:
                for date_str in semester.makeup_dates.split(','):
                    if date_str.strip():
                        try:
                            makeup_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
                            makeup_dates.add(makeup_date)
                        except ValueError:
                            pass  # Skip invalid date formats
            
            # Determine which days to show based on course schedule
            days_to_show = []
            if 'Friday' in course_routines and 'Saturday' in course_routines:
                # Course has both Friday and Saturday classes - show all dates
                days_to_show = ['Friday', 'Saturday']
                print(f"DEBUG: Course has both Friday and Saturday classes - showing all dates")
            elif 'Friday' in course_routines:
                # Course has only Friday classes - show all Friday dates
                days_to_show = ['Friday']
                print(f"DEBUG: Course has only Friday classes - showing Friday dates only")
            elif 'Saturday' in course_routines:
                # Course has only Saturday classes - show all Saturday dates
                days_to_show = ['Saturday']
                print(f"DEBUG: Course has only Saturday classes - showing Saturday dates only")
            else:
                # Fallback: show Friday and Saturday if no specific schedule found
                days_to_show = ['Friday', 'Saturday']
                print(f"DEBUG: No specific schedule found - showing both Friday and Saturday dates")
            
            # Generate dates based on the determined days to show
            while current_date <= end_date:
                # Check if it's one of the days to show
                day_name = current_date.strftime('%A')  # Get day name (Monday, Tuesday, etc.)
                if day_name in days_to_show:
                    # Only add if not a holiday
                    if current_date not in holiday_dates:
                        semester_dates.append(current_date)
                current_date += timedelta(days=1)
            
            # Add makeup dates to the semester dates
            for makeup_date in makeup_dates:
                # Allow makeup dates both within and outside semester range (makeup classes can extend beyond normal semester)
                if makeup_date not in semester_dates:
                    semester_dates.append(makeup_date)
            
            # Sort all dates chronologically
            semester_dates.sort()
            
            print(f"DEBUG: Generated {len(semester_dates)} dates for course {course.name}")
            print(f"DEBUG: Days to show: {days_to_show}")
            print(f"DEBUG: First 5 dates: {semester_dates[:5]}")
            print(f"DEBUG: Last 5 dates: {semester_dates[-5:]}")
            
            # Get all attendance data for this course and semester
            attendance_records = Attendance.objects.filter(
                course=course,
                semester=semester
            ).select_related('student')
            
            # Create attendance matrix: {student_id: {date: is_present}}
            attendance_matrix = {}
            for record in attendance_records:
                student_id = record.student.id
                if student_id not in attendance_matrix:
                    attendance_matrix[student_id] = {}
                attendance_matrix[student_id][record.attendance_date] = record.is_present
            
            # Create a simpler attendance status lookup for template
            attendance_status = {}
            for student in students:
                attendance_status[student.id] = {}
                for date in semester_dates:
                    if student.id in attendance_matrix and date in attendance_matrix[student.id]:
                        attendance_status[student.id][date] = attendance_matrix[student.id][date]
                    else:
                        attendance_status[student.id][date] = None
            
            # Calculate attendance totals for each student
            attendance_totals = {}
            try:
                # Get number_of_classes from SemesterCourse
                semester_course = SemesterCourse.objects.get(
                    semester=semester,
                    course=course
                )
                number_of_classes = semester_course.number_of_classes
                print(f"DEBUG: Found SemesterCourse with number_of_classes: {number_of_classes}")
            except SemesterCourse.DoesNotExist:
                number_of_classes = len(semester_dates)  # Fallback to number of dates
                print(f"DEBUG: No SemesterCourse found, using fallback: {number_of_classes}")
            
            for student in students:
                # Simple count of present days (for reference)
                attendance_days = sum(1 for date in semester_dates 
                                     if student.id in attendance_matrix and 
                                     date in attendance_matrix[student.id] and 
                                     attendance_matrix[student.id][date])
                
                # Calculate duration-based classes attended
                if class_ratio != 1.0:
                    classes_attended = round(attendance_days * class_ratio, 1)
                else:
                    classes_attended = attendance_days
                
                attendance_totals[student.id] = {
                    'attendance_days': attendance_days,
                    'classes_attended': classes_attended,
                    'number_of_classes': number_of_classes
                }
                
                print(f"DEBUG: Student {student.id} - Attendance days: {attendance_days}, Classes attended: {classes_attended}, Total classes: {number_of_classes}")
            
            # Get attendance data for the selected date if provided (for backward compatibility)
            attendance_data = {}
            if selected_date:
                for record in attendance_records.filter(attendance_date=selected_date):
                    attendance_data[record.student.id] = record.is_present
            
            from datetime import date
            # Find the current week column (closest upcoming date to today)
            current_week_date = None
            today = date.today()
            
            # Find the closest upcoming date (including today if it's a class day)
            for semester_date in semester_dates:
                if semester_date >= today:
                    current_week_date = semester_date
                    break
            
            # If no upcoming date found, use the last date in the semester
            if not current_week_date and semester_dates:
                current_week_date = semester_dates[-1]
            
            print(f"DEBUG: Current week date selected: {current_week_date}")

            context.update({
                'semester': semester,
                'course': course,
                'students': students,
                'semester_dates': semester_dates,
                'attendance_matrix': attendance_matrix,
                'attendance_status': attendance_status,
                'attendance_data': attendance_data,
                'attendance_totals': attendance_totals,
                'today': today,
                'current_week_date': current_week_date,
                'holiday_dates': holiday_dates,
                'makeup_dates': makeup_dates,
                'actual_class_duration': actual_class_duration,
                'class_ratio': class_ratio,
            })
            
            print("=" * 80)
            print("FINAL CONTEXT CHECK:")
            print(f"attendance_totals: {attendance_totals}")
            print(f"len(semester_dates): {len(semester_dates)}")
            print("=" * 80)
            
        except (Semester.DoesNotExist, Course.DoesNotExist):
            messages.error(request, "Invalid semester or course selected.")
    
    return render(request, 'bou_routines_app/attendance_calendar.html', context)

@login_required
def get_semesters_for_curriculum(request):
    """AJAX endpoint to get semesters for a specific curriculum"""
    # Check if user is admin/superuser or has attendance permission
    if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_mark_attendance')):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    curriculum_id = request.GET.get('curriculum_id')
    if not curriculum_id:
        return JsonResponse({'error': 'Curriculum ID required'}, status=400)
    
    try:
        curriculum = Curriculum.objects.get(id=curriculum_id)
        semesters = Semester.objects.filter(curriculum=curriculum).order_by('order', 'name')
        
        semesters_data = []
        for semester in semesters:
            semesters_data.append({
                'id': semester.id,
                'name': semester.name,
                'semester_full_name': semester.semester_full_name
            })
        
        return JsonResponse({'semesters': semesters_data})
    except Curriculum.DoesNotExist:
        return JsonResponse({'error': 'Curriculum not found'}, status=404)

@login_required
def get_courses_for_semester(request):
    """AJAX endpoint to get courses for a specific semester"""
    # Check if user is admin/superuser or has attendance permission
    if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_mark_attendance')):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    semester_id = request.GET.get('semester_id')
    if not semester_id:
        return JsonResponse({'error': 'Semester ID required'}, status=400)
    
    # Get teacher from logged-in user (optional for admin users)
    teacher = get_teacher_from_user(request.user)
    
    # Filter courses by semester and teacher
    if teacher:
        courses = Course.objects.filter(
            teacher=teacher,
            semestercourse__semester_id=semester_id
        ).distinct().order_by('code')
    else:
        courses = Course.objects.filter(
            semestercourse__semester_id=semester_id
        ).distinct().order_by('code')
    
    courses_data = []
    for course in courses:
        courses_data.append({
            'id': course.id,
            'code': course.code,
            'name': course.name,
            'display_name': f"{course.code} - {course.name}"
        })
    
    return JsonResponse({'courses': courses_data})

@login_required
def mark_individual_attendance(request):
    """AJAX endpoint to mark individual student attendance"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)
    
    # Check permissions
    if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_mark_attendance')):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        teacher = get_teacher_from_user(request.user)
        # For admin users, use the first teacher or create a default one
        if not teacher:
            teacher = Teacher.objects.first()
            if not teacher:
                return JsonResponse({'error': 'No teacher found in system'}, status=400)
        
        student_id = request.POST.get('student_id')
        course_id = request.POST.get('course_id')
        semester_id = request.POST.get('semester_id')
        attendance_date = request.POST.get('attendance_date')
        is_present = request.POST.get('is_present') == 'true'
        
        if not all([student_id, course_id, semester_id, attendance_date]):
            return JsonResponse({'error': 'Missing required parameters'}, status=400)
        
        # Get objects
        student = Student.objects.get(id=student_id)
        semester = Semester.objects.get(id=semester_id)
        
        if get_teacher_from_user(request.user):
            course = Course.objects.get(id=course_id, teacher=teacher)
        else:
            course = Course.objects.get(id=course_id)
        
        # Create or update attendance record
        attendance, created = Attendance.objects.update_or_create(
            student=student,
            course=course,
            semester=semester,
            attendance_date=attendance_date,
            defaults={
                'is_present': is_present,
                'marked_by': teacher,
                'marked_at': timezone.now()
            }
        )
        
        return JsonResponse({
            'success': True,
            'created': created,
            'is_present': is_present,
            'message': 'Attendance marked successfully'
        })
        
    except (Student.DoesNotExist, Course.DoesNotExist, Semester.DoesNotExist) as e:
        return JsonResponse({'error': f'Invalid data: {str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)

@login_required
@require_POST
def mark_attendance(request):
    """Mark attendance for students on a specific date"""
    try:
        # Check permissions
        if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_mark_attendance')):
            return JsonResponse({'success': False, 'message': 'Permission denied'})
        
        teacher = get_teacher_from_user(request.user)
        # For admin users, use the first teacher or create a default one
        if not teacher:
            teacher = Teacher.objects.first()
            if not teacher:
                return JsonResponse({'success': False, 'message': 'No teacher found in system'})
        
        semester_id = request.POST.get('semester_id')
        course_id = request.POST.get('course_id')
        attendance_date = request.POST.get('attendance_date')
        
        semester = Semester.objects.get(id=semester_id)
        if get_teacher_from_user(request.user):
            course = Course.objects.get(id=course_id, teacher=teacher)
        else:
            course = Course.objects.get(id=course_id)
        
        # Get all students for this semester with custom sorting
        # Sort by first two digits (descending), then last three digits (ascending)
        students = Student.objects.filter(semesters=semester).extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        
        attendance_count = 0
        for student in students:
            is_present = request.POST.get(f'student_{student.id}') == 'on'
            
            # Create or update attendance record
            attendance, created = Attendance.objects.update_or_create(
                student=student,
                course=course,
                semester=semester,
                attendance_date=attendance_date,
                defaults={
                    'is_present': is_present,
                    'marked_by': teacher,
                }
            )
            attendance_count += 1
        
        messages.success(request, f'Attendance marked for {attendance_count} students on {attendance_date}')
        return JsonResponse({'success': True, 'message': f'Attendance marked for {attendance_count} students'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@login_required
def get_attendance_data(request):
    """AJAX endpoint to get attendance data for a specific date"""
    try:
        semester_id = request.GET.get('semester_id')
        course_id = request.GET.get('course_id')
        attendance_date = request.GET.get('attendance_date')
        
        if not all([semester_id, course_id, attendance_date]):
            return JsonResponse({'error': 'Missing parameters'}, status=400)
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        
        attendance_records = Attendance.objects.filter(
            course=course,
            semester=semester,
            attendance_date=attendance_date
        )
        
        data = {record.student.id: record.is_present for record in attendance_records}
        return JsonResponse(data)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def attendance_report(request):
    """Generate attendance report for a course"""
    try:
        # Check permissions
        if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_mark_attendance')):
            messages.error(request, "You don't have permission to access attendance reports.")
            return redirect('generate-routine')
        
        teacher = get_teacher_from_user(request.user)
        if not teacher and not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, "You don't have a teacher profile.")
            return redirect('generate-routine')
        
        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        
        if not semester_id or not course_id:
            messages.error(request, "Please select a semester and course.")
            return redirect('attendance-calendar')
        
        semester = Semester.objects.get(id=semester_id)
        if teacher:
            course = Course.objects.get(id=course_id, teacher=teacher)
        else:
            course = Course.objects.get(id=course_id)
        
        # Get all students and their attendance records with custom sorting
        # Sort by first two digits (descending), then last three digits (ascending)
        students = Student.objects.filter(semesters=semester).extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        
        # Get all attendance dates for this course
        attendance_dates = Attendance.objects.filter(
            course=course,
            semester=semester
        ).values_list('attendance_date', flat=True).distinct().order_by('attendance_date')
        
        # Create attendance matrix
        attendance_matrix = {}
        for student in students:
            attendance_matrix[student.id] = {
                'student': student,
                'attendance': {}
            }
            
            # Get attendance records for this student
            student_attendance = Attendance.objects.filter(
                student=student,
                course=course,
                semester=semester
            )
            
            for record in student_attendance:
                attendance_matrix[student.id]['attendance'][record.attendance_date] = record.is_present
        
        # Calculate statistics
        total_classes = len(attendance_dates)
        for student_id in attendance_matrix:
            present_count = sum(1 for is_present in attendance_matrix[student_id]['attendance'].values() if is_present)
            attendance_matrix[student_id]['present_count'] = present_count
            attendance_matrix[student_id]['absent_count'] = total_classes - present_count
            attendance_matrix[student_id]['percentage'] = (present_count / total_classes * 100) if total_classes > 0 else 0
        
        context = {
            'semester': semester,
            'course': course,
            'students': students,
            'attendance_dates': attendance_dates,
            'attendance_matrix': attendance_matrix,
            'total_classes': total_classes,
        }
        
        return render(request, 'bou_routines_app/attendance_report.html', context)
        
    except Exception as e:
        messages.error(request, f"Error generating attendance report: {str(e)}")
        return redirect('attendance-calendar')

# Teacher Registration Views

def teacher_register(request):
    """Teacher registration form"""
    if request.method == 'POST':
        form = TeacherRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}. You can now login!')
            return redirect('login')
    else:
        form = TeacherRegistrationForm()
    
    return render(request, 'registration/teacher_register.html', {'form': form})

def teacher_dashboard(request):
    """Teacher dashboard showing their profile and permissions"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    teacher = get_teacher_from_user(request.user)
    if not teacher:
        messages.error(request, "You don't have a teacher profile.")
        return redirect('generate-routine')
    
    # Get user permissions
    user_permissions = request.user.get_all_permissions()
    teacher_permissions = [perm for perm in user_permissions if perm.startswith('bou_routines_app.')]
    
    context = {
        'teacher': teacher,
        'permissions': teacher_permissions,
        'can_mark_attendance': check_teacher_permission(request.user, 'can_mark_attendance'),
        'can_manage_ca': check_teacher_permission(request.user, 'can_manage_ca'),
        'can_manage_final_marks': check_teacher_permission(request.user, 'can_manage_final_marks'),
    }
    
    return render(request, 'bou_routines_app/teacher_dashboard.html', context)


@login_required
def ca_management(request):
    """
    CA (Continuous Assessment) management page
    Similar to attendance calendar but for CA marks
    """
    # Check permissions
    if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_manage_ca')):
        messages.error(request, "You don't have permission to manage CA marks.")
        return redirect('teacher-dashboard')
    
    # Get teacher profile
    teacher = None
    if hasattr(request.user, 'teacher'):
        teacher = request.user.teacher
    elif request.user.is_superuser or request.user.is_staff:
        teacher = None  # Admin can manage all courses
    
    # Get all curricula
    curricula = Curriculum.objects.filter(is_active=True).order_by('name')
    
    # Get selected curriculum from request
    selected_curriculum_id = request.GET.get('curriculum') or request.POST.get('curriculum')
    selected_curriculum = None
    
    if selected_curriculum_id:
        try:
            selected_curriculum_id = int(selected_curriculum_id)
            selected_curriculum = Curriculum.objects.get(id=selected_curriculum_id)
        except (Curriculum.DoesNotExist, ValueError):
            selected_curriculum = None
            selected_curriculum_id = None
    
    # If no curriculum selected, use the Old Curriculum by default
    if not selected_curriculum and curricula.exists():
        try:
            selected_curriculum = Curriculum.objects.get(code='OLD')
            selected_curriculum_id = selected_curriculum.id
        except Curriculum.DoesNotExist:
            selected_curriculum = curricula.first()
            selected_curriculum_id = selected_curriculum.id if selected_curriculum else None
    
    # Filter semesters by selected curriculum
    if selected_curriculum:
        semesters = Semester.objects.filter(curriculum=selected_curriculum).order_by('order', 'name')
    else:
        semesters = Semester.objects.all().order_by('order', 'name')
    
    # Get semester and course from request
    semester_id = request.GET.get('semester') or request.POST.get('semester')
    course_id = request.GET.get('course') or request.POST.get('course')
    
    # Get courses for the selected semester
    courses_queryset = Course.objects.none()
    if semester_id:
        if teacher:
            # Teacher can only see their own courses
            courses_queryset = Course.objects.filter(
                semestercourse__semester_id=semester_id,
                teacher=teacher
            ).distinct()
        else:
            # Admin users can see all courses in the selected semester
            courses_queryset = Course.objects.filter(
                semestercourse__semester_id=semester_id
            ).distinct()
    
    # Get students for the selected course and semester
    students = Student.objects.none()
    ca_marks = {}
    if semester_id and course_id:
        try:
            semester = Semester.objects.get(id=semester_id)
            course = Course.objects.get(id=course_id)
            
            # Get students enrolled in this semester
            students = Student.objects.filter(semesters=semester).order_by('id')
            
            # Get existing CA marks for these students
            existing_marks = CAMark.objects.filter(
                student__in=students,
                course=course,
                semester=semester
            )
            
            # Create a dictionary for easy lookup
            for mark in existing_marks:
                ca_marks[mark.student.id] = mark
            
            # For students without existing CA marks, create temporary objects with calculated attendance
            for student in students:
                if student.id not in ca_marks:
                    # Create a temporary CA mark object with calculated attendance
                    temp_mark = CAMark(
                        student=student,
                        course=course,
                        semester=semester
                    )
                    # Calculate attendance mark
                    temp_mark.attendance_mark = temp_mark.calculate_attendance_mark()
                    ca_marks[student.id] = temp_mark
                
        except (Semester.DoesNotExist, Course.DoesNotExist):
            messages.error(request, "Invalid semester or course selected.")
    
    context = {
        'teacher': teacher,
        'is_admin': request.user.is_superuser or request.user.is_staff,
        'curricula': curricula,
        'selected_curriculum_id': selected_curriculum_id,
        'selected_curriculum': selected_curriculum,
        'semesters': semesters,
        'courses': courses_queryset.order_by('code'),
        'selected_semester_id': semester_id,
        'selected_course_id': course_id,
        'students': students,
        'ca_marks': ca_marks,
    }
    
    if semester_id and course_id:
        try:
            semester = Semester.objects.get(id=semester_id)
            course = Course.objects.get(id=course_id)
            context['selected_semester'] = semester
            context['selected_course'] = course
        except (Semester.DoesNotExist, Course.DoesNotExist):
            pass
    
    return render(request, 'bou_routines_app/ca_management.html', context)


@login_required
def save_ca_marks(request):
    """
    Save CA marks for students
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
    # Check permissions
    if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_manage_ca')):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        semester_id = request.POST.get('semester_id')
        course_id = request.POST.get('course_id')
        
        if not semester_id or not course_id:
            return JsonResponse({'error': 'Semester and course are required'}, status=400)
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        
        # Get teacher
        teacher = None
        if hasattr(request.user, 'teacher'):
            teacher = request.user.teacher
        elif request.user.is_superuser or request.user.is_staff:
            # For admin users, we need to get the course teacher
            teacher = course.teacher
        
        if not teacher:
            return JsonResponse({'error': 'Teacher not found'}, status=400)
        
        # Process each student's marks
        students_data = request.POST.get('students_data')
        if students_data:
            import json
            students_marks = json.loads(students_data)
            
            for student_id, marks_data in students_marks.items():
                try:
                    student = Student.objects.get(id=student_id)
                    
                    # Get or create CA mark record
                    ca_mark, created = CAMark.objects.get_or_create(
                        student=student,
                        course=course,
                        semester=semester,
                        defaults={'marked_by': teacher}
                    )
                    
                    # Update marks based on course type
                    if course.is_lab:
                        # Lab course marks
                        ca_mark.lab_assignment_mark = float(marks_data.get('lab_assignment_mark', 0))
                        ca_mark.lab_practical_mark = float(marks_data.get('lab_practical_mark', 0))
                    else:
                        # Theory course marks
                        ca_mark.assignment_mark = float(marks_data.get('assignment_mark', 0))
                        ca_mark.quiz_mark = float(marks_data.get('quiz_mark', 0))
                        ca_mark.midterm_mark = float(marks_data.get('midterm_mark', 0))
                    
                    # Update metadata
                    ca_mark.marked_by = teacher
                    ca_mark.notes = marks_data.get('notes', '')
                    
                    # Save (this will trigger auto-calculation of attendance and total marks)
                    ca_mark.save()
                    
                except Student.DoesNotExist:
                    continue
                except (ValueError, TypeError) as e:
                    continue
        
        return JsonResponse({'success': True, 'message': 'CA marks saved successfully'})
        
    except (Semester.DoesNotExist, Course.DoesNotExist):
        return JsonResponse({'error': 'Invalid semester or course'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
