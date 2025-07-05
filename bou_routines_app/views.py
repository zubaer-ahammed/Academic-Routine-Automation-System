from django.shortcuts import render, redirect
from .models import CurrentRoutine, Teacher, Semester, Course, NewRoutine, SemesterCourse
from .forms import RoutineForm
from datetime import datetime, timedelta
from collections import defaultdict
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, FileResponse
import io
import xlsxwriter
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from django.urls import reverse
from django.utils.http import urlencode


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
            
            return redirect('routine-entry')
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

def generate_routine(request):
    semesters = Semester.objects.all().order_by('name')
    courses = Course.objects.select_related('teacher').all().order_by('code')
    teachers = Teacher.objects.all()

    # Pre-select semester if provided in query params (GET)
    selected_semester_id = request.GET.get('semester')

    # Check if we have any semester courses at all
    if not SemesterCourse.objects.exists():
        messages.warning(request, "No courses have been assigned to any semester yet. Please add courses to a semester first via the 'Semester Courses' menu.")

    generated_routines = []
    overlap_conflicts = []
    form_rows = []

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
                                            'teacher': r['teacher'],
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

                selected_semester.save()
                #messages.success(request, f"Updated lunch break for {selected_semester.name} to {lunch_break_start} - {lunch_break_end}")
            except Exception as e:
                messages.error(request, f"Error updating semester settings: {str(e)}")
        
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

            while current_date <= end_date:
                day_name = current_date.strftime('%A')
                processed_days.append(day_name)
                
                # Skip if current date is a holiday
                if current_date in holiday_dates:
                    skipped_holidays.append(current_date.strftime('%Y-%m-%d'))
                    current_date += timedelta(days=1)
                    continue

                # Only process Friday and Saturday (or expand for other days if needed)
                if day_name in ['Friday', 'Saturday']:
                    day_matched = False
                    for i in range(len(days)):
                        if days[i] == day_name:
                            day_matched = True
                            course_id = course_codes[i]
                            start_time_str = start_times[i]
                            end_time_str = end_times[i]
                            
                            try:
                                course = Course.objects.get(id=course_id)
                                start = datetime.strptime(start_time_str, "%H:%M").time()
                                end = datetime.strptime(end_time_str, "%H:%M").time()
                                
                                # Create the new routine entry
                                new_routine = NewRoutine.objects.create(
                                    semester=selected_semester,
                                    course=course,
                                    start_time=start,
                                    end_time=end,
                                    day=day_name,
                                    class_date=current_date
                                )
                                
                                # Also create or update the corresponding CurrentRoutine entry
                                CurrentRoutine.objects.update_or_create(
                                    semester=selected_semester,
                                    course=course,
                                    day=day_name,
                                    defaults={
                                        'start_time': start,
                                        'end_time': end
                                    }
                                )
                                
                                # Add to generated_routines for display
                                generated_routines.append({
                                    'id': new_routine.id,
                                    'course_id': course.id,
                                    'date': current_date,
                                    'day': day_name,
                                    'course_code': course.code,
                                    'course_name': course.name,
                                    'teacher': course.teacher.name,
                                    'start_time': start.strftime('%H:%M'),
                                    'end_time': end.strftime('%H:%M')
                                })
                                
                                # Log each successful routine creation
                                matched_days.append(f"{day_name} - {course.code}")
                            except Course.DoesNotExist:
                                # Skip if course doesn't exist
                                continue
                    
                    # If no matches were found for this day, log it
                    if not day_matched and day_name in ['Friday', 'Saturday']:
                        matched_days.append(f"{day_name} - No matching courses")
                
                # Move to next day
                current_date += timedelta(days=1)
                
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
                            # Prepare cell content
                            if r.get('is_lunch_break'):
                                content = 'BREAK'
                                cell = {'content': content, 'colspan': colspan, 'is_lunch_break': True}
                            else:
                                content = {
                                    'course_code': r['course_code'],
                                    'teacher': r['teacher'],
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
                        # Empty cell: attach start_time and end_time from slot_ranges
                        cell = {
                            'content': '',
                            'colspan': 1,
                            'is_lunch_break': False,
                            'start_time': slot_start,
                            'end_time': slot_end,
                        }
                        row_cells.append(cell)
                        slot_idx += 1
                routine_table_rows.append({'date': date, 'day': day, 'cells': row_cells})
            # --- END NEW ---
            
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
            "time_slot_labels": time_slot_labels
        })

    # Include the selected semester ID if available in POST
    if request.method == "POST" and request.POST.get("semester"):
        context["selected_semester_id"] = request.POST.get("semester")
        
    return render(request, "bou_routines_app/generate_routine.html", context)

def update_semester_courses(request):
    semesters = Semester.objects.all().order_by('name')
    courses = Course.objects.all().order_by('code')
    from .models import Teacher
    teachers = Teacher.objects.all().order_by('name')
    context = {
        "semesters": semesters,
        "courses": courses,
        "teachers": teachers,
    }
    
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
                }
                return JsonResponse({
                    'courses': courses_data,
                    'lunch_break': lunch_break_info,
                    'date_range': date_range_info,
                    'holidays': holidays_info,
                    'semester_data': semester_data
                })
            except Semester.DoesNotExist:
                return JsonResponse({'courses': [], 'lunch_break': None})
    return JsonResponse({'courses': [], 'lunch_break': None})

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

        # Write data with merging
        row = 3
        for date, day in unique_dates_days:
            worksheet.write(row, 0, date, date_format)
            worksheet.write(row, 1, day, cell_format)

            # Build routines for this row
            routines_for_row = []
            for r in routines:
                if r.class_date == date and r.day == day:
                    routines_for_row.append({
                        'course_code': r.course.code,
                        'teacher': r.course.teacher.short_name,
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
                            format_to_use = course_format
                        
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
                    worksheet.write(row, col_idx, "", cell_format)
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
                            'teacher': r.course.teacher.short_name,
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
                                    'teacher': r['teacher'],
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
            
            semester_routines.append({
                'semester': semester,
                'routine_table_rows': routine_table_rows,
                'time_slot_labels': [label for _, _, label in slot_ranges],
                'routine_count': latest_routines.count()
            })
    
    return render(request, 'bou_routines_app/download_routines.html', {
        'semester_routines': semester_routines
    })

def export_to_pdf(request, semester_id):
    """Export the routine to PDF file"""
    try:
        selected_semester = Semester.objects.get(id=semester_id)

        # Create a response for PDF file
        buffer = io.BytesIO()

        # Create the PDF document with A4 landscape orientation and decent print margins
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=54,  # 0.75 inch
            leftMargin=54,   # 0.75 inch
            topMargin=54,    # 0.75 inch
            bottomMargin=54  # 0.75 inch
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
        elements.append(Spacer(1, 12))

        # Build left column (program/session/term/commencement/study center)
        header_style = ParagraphStyle(
            'HeaderStyle',
            fontName='Helvetica-Bold',
            fontSize=18,
            alignment=1,  # Center
            leading=28,   # Increased line height
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_small = ParagraphStyle(
            'HeaderStyleSmall',
            fontName='Helvetica-Bold',
            fontSize=14,
            alignment=1,
            leading=22,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_normal = ParagraphStyle(
            'HeaderStyleNormal',
            fontName='Helvetica',
            fontSize=12,
            alignment=1,
            leading=20,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_bold = ParagraphStyle(
            'HeaderStyleBold',
            fontName='Helvetica-Bold',
            fontSize=15,
            alignment=1,
            leading=24,
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
        left_content.append(Spacer(1, 8))
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
            contact_lines.append(f'<b><u>Contact Person</u></b>')
            contact_lines.append('&nbsp;')  # Minimal gap
            contact_lines.append(selected_semester.contact_person)
        if selected_semester.contact_person_designation:
            contact_lines.append(selected_semester.contact_person_designation)
        contact_lines.append('School of Science and Technology')
        contact_lines.append('Bangladesh Open University')
        if selected_semester.contact_person_phone:
            contact_lines.append(f'Telephone: {selected_semester.contact_person_phone}')
        if selected_semester.contact_person_email:
            contact_lines.append(f'email:{selected_semester.contact_person_email}')
        contact_box = '<br/>'.join(contact_lines)
        contact_box_para = Paragraph(contact_box, ParagraphStyle('ContactBox', fontSize=10, borderWidth=1, borderColor=colors.black, borderPadding=6, leading=14, spaceBefore=0, spaceAfter=0))
        contact_table = Table([[contact_box_para]], colWidths=[180], hAlign='RIGHT')
        contact_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 2, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        # Combine into a two-column table with reduced contact box width, aligned to margins
        two_col_table = Table(
            [[left_content, contact_table]],
            colWidths=[available_width-180, 180],
            hAlign='LEFT'
        )
        two_col_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (0, 0), 'TOP'),
            ('VALIGN', (1, 0), (1, 0), 'TOP'),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        elements.append(two_col_table)
        elements.append(Spacer(1, 16))

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
        for row_idx, (date, day) in enumerate(unique_dates_days, start=1):
            row = [date.strftime('%d/%m/%Y'), day]
            slot_idx = 0
            # Build routines_for_row: all routines for this date/day, plus lunch break if present
            routines_for_row = []
            for r in routines:
                if r.class_date == date and r.day == day:
                    routines_for_row.append({
                        'course_code': r.course.code,
                        'teacher': r.course.teacher.short_name,
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
            col_idx = 2  # first two columns are date and day
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
                            cell_content = "BREAK"
                        else:
                            cell_content = f"{r['course_code']} ({r['teacher']})"
                        row.append(cell_content)
                        for _ in range(colspan-1):
                            row.append(None)
                        # Add SPAN command if colspan > 1
                        if colspan > 1:
                            span_commands.append(('SPAN', (col_idx, row_idx), (col_idx + colspan - 1, row_idx)))
                        col_idx += colspan
                        slot_idx += colspan
                        found = True
                        break
                if not found:
                    row.append("")
                    col_idx += 1
                    slot_idx += 1
            table_data.append(row)

        # Calculate available width for all tables
        available_width = page_width - doc.leftMargin - doc.rightMargin

        # Set column widths directly without depending on lunch_col_idx
        num_cols = len(header_row)
        date_col_width = 65   # narrow date column
        day_col_width = 55    # narrow day column

        # Calculate remaining width for other columns
        remaining_width = available_width - date_col_width - day_col_width
        other_col_width = remaining_width / (num_cols - 2) if num_cols > 2 else 0

        # Build column widths list
        col_widths = []
        for i in range(num_cols):
            if i == 0:
                col_widths.append(date_col_width)
            elif i == 1:
                col_widths.append(day_col_width)
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
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            # Grid and borders
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            # Set a fixed row height
            ('ROWHEIGHT', (0, 1), (-1, -1), 35),
            # Text wrapping for all cells
            ('WORDWRAP', (0, 0), (-1, -1), True),
        ])
        # Add background color for lunch breaks and classes
        for i, row in enumerate(table_data[1:], 1):
            for j, cell in enumerate(row[2:], 2):
                if cell == "BREAK":
                    style.add('BACKGROUND', (j, i), (j, i), colors.lightgrey)
                    style.add('TEXTCOLOR', (j, i), (j, i), colors.black)
                    style.add('FONTNAME', (j, i), (j, i), 'Helvetica-Bold')
                    style.add('FONTSIZE', (j, i), (j, i), 9)
                elif cell:  # If there's content (a class)
                    style.add('BACKGROUND', (j, i), (j, i), colors.lightblue)
        # After creating the TableStyle, add the span commands
        for cmd in span_commands:
            style.add(*cmd)
        table.setStyle(style)
        elements.append(table)

        # Add vertical space before the N.B. note
        elements.append(Spacer(1, 18))  # 18 points = 0.25 inch

        # Add the note section as a table for proper border and wrapping
        note_text = (
            "N.B.  For any changes in the schedule, concerned coordinator/class teachers are requested to inform the students as well as the Dean, School of Science and Technology, BOU in advance."
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
        elements.append(Spacer(1, 18))  # Gap below the N.B. note
        elements.append(Paragraph("<br/>", styles['Normal']))

        # Add the summary table of semester courses
        semester_courses = SemesterCourse.objects.filter(semester=selected_semester).select_related('course', 'course__teacher')
        summary_data = [[
            'Course Code', 'Title', 'Number of Class', 'Course Teacher'
        ]]
        for sc in semester_courses:
            summary_data.append([
                sc.course.code,
                sc.course.name,
                str(sc.number_of_classes),
                sc.course.teacher.name + ' ('+sc.course.teacher.short_name+')'
            ])
        summary_col_widths = [0.12 * available_width, 0.38 * available_width, 0.14 * available_width, 0.36 * available_width]
        summary_table = Table(summary_data, colWidths=summary_col_widths)
        summary_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BOX', (0, 0), (-1, -1), 2, colors.black),
        ])
        summary_table.setStyle(summary_style)
        elements.append(summary_table)

        # Add vertical space before the signature field
        elements.append(Spacer(1, 48)) # Gap before signature (e.g., 0.66 inch)

        # --- SIGNATURE FIELD SECTION ---
        signature_style = ParagraphStyle(
            'SignatureStyle',
            fontName='Helvetica',
            fontSize=10,
            alignment=TA_RIGHT,  # Right alignment
            leading=12, # Line height
            spaceBefore=0,
            spaceAfter=0,
        )

        # Create signature lines
        dean_line = Paragraph("Dean", signature_style)
        school_line = Paragraph("School of Science and Technology", signature_style)
        bou_line = Paragraph("Bangladesh Open University", signature_style)

        # Create the signature table
        signature_data = [
            [dean_line],
            [school_line],
            [bou_line]
        ]

        # Set a fixed width for the signature table
        signature_table_width = 250 # Adjust as needed
        signature_table = Table(signature_data, colWidths=[signature_table_width])

        # Style for the signature table
        signature_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'RIGHT'), # Right align all content in the table
            ('LINEABOVE', (0,0), (0,0), 1, colors.black), # Line above "Dean"
            ('TOPPADDING', (0,0), (0,0), 4), # Padding above the line
        ]))

        # Create a wrapper table to place the signature table at the bottom right
        # This table will span the full available width, with an empty left column
        # to push the signature table to the right.
        wrapper_col_widths = [available_width - signature_table_width, signature_table_width]
        signature_wrapper_table = Table([['', signature_table]], colWidths=wrapper_col_widths)
        signature_wrapper_table.setStyle(TableStyle([
            ('ALIGN', (1,0), (1,0), 'RIGHT'), # Align the second column (where signature table is) to the right
            ('VALIGN', (0,0), (-1,-1), 'BOTTOM'), # Align content to bottom if there's vertical space
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))

        elements.append(signature_wrapper_table)

        # Build the PDF (only once)
        doc.build(elements)
        buffer.seek(0)
        response = FileResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{selected_semester.name}_Routine.pdf"'
        return response

    except Exception as e:
        return HttpResponse(f"Error generating PDF file: {str(e)}", status=500)
