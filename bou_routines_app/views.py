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
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


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
    semesters = Semester.objects.all()
    courses = Course.objects.select_related('teacher').all()
    teachers = Teacher.objects.all()

    # Check if we have any semester courses at all
    if not SemesterCourse.objects.exists():
        messages.warning(request, "No courses have been assigned to any semester yet. Please add courses to a semester first via the 'Semester Courses' menu.")

    generated_routines = []
    overlap_conflicts = []
    form_rows = []

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
        "generated_routines": generated_routines
    }
    
    # Add calendar view data if routines were generated
    if request.method == "POST" and generated_routines:
        context.update({
            "routine_dates": unique_dates,
            "time_slots": time_slots,
            "calendar_routines": calendar_routines,
            "lunch_break": lunch_break
        })

    # Include the selected semester ID if available in POST
    if request.method == "POST" and request.POST.get("semester"):
        context["selected_semester_id"] = request.POST.get("semester")
        
    return render(request, "bou_routines_app/generate_routine.html", context)

def update_semester_courses(request):
    semesters = Semester.objects.all()
    courses = Course.objects.all()
    context = {
        "semesters": semesters,
        "courses": courses,
    }
    
    if request.method == "POST":
        semester_id = request.POST.get("semester")
        # Include the selected semester ID in the context
        context["selected_semester_id"] = semester_id
        
        # Remove duplicates by converting to set and back to list
        selected_courses = list(set(request.POST.getlist("courses[]")))

        # Get the selected semester
        semester = Semester.objects.get(id=semester_id)

        # Remove all existing SemesterCourse entries for this semester
        SemesterCourse.objects.filter(semester=semester).delete()

        # Create semester courses
        for course_id in selected_courses:
            course = Course.objects.get(id=course_id)
            # No need to get teacher as it's already part of the course
            SemesterCourse.objects.create(
                semester=semester,
                course=course
            )

        return render(request, "bou_routines_app/semester_courses.html", context)

    return render(request, "bou_routines_app/semester_courses.html", context)

def get_semester_courses(request):
    """AJAX view to get courses for a specific semester"""
    if request.method == "GET":
        semester_id = request.GET.get("semester_id")
        if semester_id:
            # Get the semester object
            try:
                semester = Semester.objects.get(id=semester_id)
                # Get all SemesterCourse objects for this semester
                semester_courses = SemesterCourse.objects.filter(semester_id=semester_id).select_related('course', 'course__teacher')
                
                # Format the data for response
                courses_data = [{
                    'id': sc.course.id,
                    'code': sc.course.code,
                    'name': sc.course.name,
                    'teacher_name': sc.course.teacher.name,
                    'teacher_id': sc.course.teacher.id
                } for sc in semester_courses]
                
                # Include lunch break information if available
                lunch_break_info = None
                if semester.lunch_break_start and semester.lunch_break_end:
                    lunch_break_info = {
                        'start': semester.lunch_break_start.strftime('%H:%M'),
                        'end': semester.lunch_break_end.strftime('%H:%M')
                    }
                
                # Include semester date range information if available
                date_range_info = None
                if semester.start_date and semester.end_date:
                    date_range_info = {
                        'start_date': semester.start_date.strftime('%m/%d/%Y'),
                        'end_date': semester.end_date.strftime('%m/%d/%Y')
                    }
                
                # Include government holidays if available
                holidays_info = None
                if semester.holidays:
                    holidays_info = semester.holidays

                return JsonResponse({
                    'courses': courses_data,
                    'lunch_break': lunch_break_info,
                    'date_range': date_range_info,
                    'holidays': holidays_info
                })
            except Semester.DoesNotExist:
                return JsonResponse({'courses': [], 'lunch_break': None})
    
    return JsonResponse({'courses': [], 'lunch_break': None})

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

        # Get unique dates
        unique_dates = routines.values_list('class_date', flat=True).distinct().order_by('class_date')

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

        # Add title
        worksheet.merge_range(0, 0, 0, len(time_slots) + 1, f"{selected_semester.name} Routine", title_format)

        # Write headers
        row = 2
        worksheet.write(row, 0, "Date", header_format)
        worksheet.write(row, 1, "Day", header_format)
        for col, time_slot in enumerate(time_slots):
            worksheet.write(row, col + 2, time_slot, header_format)

        # Set column widths
        worksheet.set_column(0, 0, 12)  # Date column
        worksheet.set_column(1, 1, 10)  # Day column
        worksheet.set_column(2, len(time_slots) + 1, 15)  # Time slot columns

        # Write data
        row = 3
        for date in unique_dates:
            day_name = date.strftime('%A')
            worksheet.write(row, 0, date, date_format)
            worksheet.write(row, 1, day_name, cell_format)

            for col, time_slot in enumerate(time_slots):
                # Check if this is a lunch break
                if lunch_break and time_slot == lunch_break:
                    worksheet.write(row, col + 2, "PRAYER & LUNCH BREAK", lunch_format)
                else:
                    # Check if there's a class in this time slot
                    cell_content = ""
                    for routine in routines:
                        routine_time_slot = f"{routine.start_time.strftime('%H:%M')} - {routine.end_time.strftime('%H:%M')}"
                        if routine.class_date == date and routine_time_slot == time_slot:
                            cell_content = f"{routine.course.code}\n({routine.course.teacher.name})"
                            break

                    if cell_content:
                        worksheet.write(row, col + 2, cell_content, course_format)
                    else:
                        worksheet.write(row, col + 2, "", cell_format)

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

def export_to_pdf(request, semester_id):
    """Export the routine to PDF file"""
    try:
        selected_semester = Semester.objects.get(id=semester_id)

        # Create a response for PDF file
        buffer = io.BytesIO()

        # Create the PDF document with A4 landscape orientation
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=20,
            leftMargin=20,
            topMargin=20,
            bottomMargin=20
        )

        # Get page width and height for calculations
        page_width, page_height = landscape(A4)

        elements = []

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
        title = Paragraph(f"{selected_semester.name} Routine", title_style)
        elements.append(title)
        elements.append(Paragraph("<br/>", styles['Normal']))

        # Create the data for the table
        table_data = []

        # Headers
        header_row = ["Date", "Day"] + time_slots
        table_data.append(header_row)

        # Data rows
        for date, day in unique_dates_days:
            row = [date.strftime('%d/%m/%Y'), day]

            for time_slot in time_slots:
                # Check if this is a lunch break
                if lunch_break and time_slot == lunch_break:
                    row.append(" PRAYER \n & LUNCH \n BREAK ")
                else:
                    # Check if there's a class in this time slot
                    cell_content = ""
                    for routine in routines:
                        routine_time_slot = f"{routine.start_time.strftime('%H:%M')} - {routine.end_time.strftime('%H:%M')}"
                        if routine.class_date == date and routine_time_slot == time_slot:
                            # Create styles for course code and teacher name
                            course_style = ParagraphStyle(
                                'CourseStyle',
                                parent=styles['Normal'],
                                fontSize=9,
                                alignment=TA_CENTER,
                                spaceAfter=2,
                                leading=9,  # Fixed line height for course code
                                spaceBefore=0  # Remove space before course code
                            )
                            teacher_style = ParagraphStyle(
                                'TeacherStyle',
                                parent=styles['Normal'],
                                fontSize=7,
                                alignment=TA_CENTER,
                                textColor=colors.darkblue,
                                leading=7,  # Line height
                                maxLines=3,  # Maximum number of lines
                                ellipsis='...',  # Add ellipsis if text is truncated
                                spaceBefore=0  # Remove space before teacher name
                            )
                            
                            # Format teacher name with parentheses
                            teacher_name = f"({routine.course.teacher.name})"
                            
                            # Create the cell content with course code and teacher name
                            # Use non-breaking space to ensure course code stays on one line
                            cell_content = Paragraph(
                                f"<b>{routine.course.code.replace(' ', '&nbsp;')}</b><br/>{teacher_name}",
                                course_style
                            )
                            break

                    row.append(cell_content)

            table_data.append(row)

        # Calculate optimal column widths based on available space
        # Reserve fixed width for date and day columns
        date_col_width = 55  # Fixed width for date column
        day_col_width = 45   # Fixed width for day column

        # Calculate remaining width for time slot columns
        available_width = page_width - doc.leftMargin - doc.rightMargin - date_col_width - day_col_width

        # Calculate width per time slot column (with a little margin for safety)
        time_slot_width = max(35, min(65, available_width / len(time_slots)))

        # Set column widths
        col_widths = [date_col_width, day_col_width] + [time_slot_width] * len(time_slots)

        # Create the table with defined column widths
        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # Custom style for the table
        style = TableStyle([
            # Headers styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),  # Slightly smaller font for headers

            # Alignment and spacing
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),  # Changed to TOP alignment
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 4),  # Reduced top padding
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
                if cell == "PRAYER & LUNCH BREAK":
                    style.add('BACKGROUND', (j, i), (j, i), colors.lightyellow)
                    style.add('TEXTCOLOR', (j, i), (j, i), colors.black)
                    style.add('FONTNAME', (j, i), (j, i), 'Helvetica-Bold')
                    style.add('FONTSIZE', (j, i), (j, i), 6)  # Decreased font size for lunch break text
                elif cell:  # If there's content (a class)
                    style.add('BACKGROUND', (j, i), (j, i), colors.lightblue)
                    # Create styles for course code and teacher name
                    course_style = ParagraphStyle(
                        'CourseStyle',
                        parent=styles['Normal'],
                        fontSize=9,
                        alignment=TA_CENTER,
                        spaceAfter=2,
                        leading=9,  # Fixed line height for course code
                        spaceBefore=0  # Remove space before course code
                    )
                    teacher_style = ParagraphStyle(
                        'TeacherStyle',
                        parent=styles['Normal'],
                        fontSize=7,
                        alignment=TA_CENTER,
                        textColor=colors.darkblue,
                        leading=7,  # Line height
                        maxLines=3,  # Maximum number of lines
                        ellipsis='...',  # Add ellipsis if text is truncated
                        spaceBefore=0  # Remove space before teacher name
                    )
                    
                    # Format teacher name with parentheses
                    teacher_name = f"({routine.course.teacher.name})"
                    
                    # Create the cell content with course code and teacher name
                    # Use non-breaking space to ensure course code stays on one line
                    cell_content = Paragraph(
                        f"{routine.course.code.replace(' ', '&nbsp;')}<br/>{teacher_name}",
                        course_style
                    )

        table.setStyle(style)

        # Add the table to elements
        elements.append(table)

        # Build the PDF
        doc.build(elements)

        # Prepare the response
        buffer.seek(0)
        response = FileResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{selected_semester.name}_Routine.pdf"'
        return response

    except Exception as e:
        return HttpResponse(f"Error generating PDF file: {str(e)}", status=500)
