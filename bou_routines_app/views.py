from django.shortcuts import render, redirect
from .models import (
    CurrentRoutine,
    Teacher,
    Semester,
    Course,
    NewRoutine,
    SemesterCourse,
    Student,
    Attendance,
    Curriculum,
    CAMark,
    MidtermExamMark,
    FinalExamMark,
    Centre,
    ProgramCoordinator,
    SemesterCentreCoordinator,
)
from .forms import RoutineForm, TeacherRegistrationForm
from datetime import datetime, timedelta, date
from collections import defaultdict
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, FileResponse
import io
import os
import calendar
import xlsxwriter
import re
import math
from reportlab.lib.pagesizes import landscape, A4, portrait
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from django.urls import reverse
from django.utils.http import urlencode
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.utils import timezone


@login_required
def routine_entry(request):
    # Teacher is now accessed through SemesterCourse
    routines = CurrentRoutine.objects.select_related("course", "semester")
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

def filter_students_queryset_by_centre(students_qs, centre_id):
    """
    Restrict a Student queryset to the selected study centre when centre_id is valid.
    Matches attendance / routine exports: only students with Student.centre set to that centre.
    """
    if centre_id is None or centre_id == '':
        return students_qs
    try:
        centre = Centre.objects.get(id=int(centre_id))
        return students_qs.filter(centre=centre)
    except (Centre.DoesNotExist, ValueError, TypeError):
        return students_qs


def _pdf_page_number_label(page_num, total_pages):
    """Standard footer page label for marks/attendance PDF exports."""
    return f'Page {page_num} of {total_pages}'


def _draw_course_teacher_signature_pdf_footer(cnv, page_num, total_pages, left_margin, right_margin):
    """CA / Mid-Term marks PDF: course-teacher signature line left, page number right."""
    pw, _ph = landscape(A4)
    left_x = left_margin
    right_x = pw - right_margin
    footer_y_line = 48
    footer_y_text = 34
    line_w = 280
    cnv.saveState()
    cnv.setLineWidth(1)
    cnv.setStrokeColor(colors.black)
    cnv.line(left_x, footer_y_line, left_x + line_w, footer_y_line)
    cnv.setFont('Helvetica', 10)
    cnv.drawString(left_x, footer_y_text, 'Signature of the course teacher')
    cnv.setFont('Helvetica', 9)
    cnv.drawRightString(right_x, footer_y_text, _pdf_page_number_label(page_num, total_pages))
    cnv.restoreState()


def _pdf_add_page_number(canvas, doc):
    """Footer page number for PDF exports (total unknown; current page only)."""
    canvas.saveState()
    canvas.setFont('Helvetica', 9)
    page_width, _page_height = doc.pagesize
    canvas.drawRightString(page_width - doc.rightMargin, 20, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _make_deferred_footer_canvas_class(footer_draw):
    """
    ReportLab Canvas that draws a per-page footer after the total page count is known.
    Avoids merging with PyPDF2/pypdf (production WSGI often uses a different Python than
    the one `pip` targeted, so merge silently failed and exports had no signature/footer).

    footer_draw: callable (canvas, page_num, total_pages) -> None

    Important: pass the returned class as canvasmaker=... to SimpleDocTemplate.build(),
    not to SimpleDocTemplate(...) — ReportLab ignores unknown constructor kwargs.
    """
    from reportlab.pdfgen import canvas as pdfgen_canvas

    class _DeferredFooterCanvas(pdfgen_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            self._footer_draw = footer_draw
            self._saved_page_states = []
            pdfgen_canvas.Canvas.__init__(self, *args, **kwargs)

        def showPage(self):
            state = dict(self.__dict__)
            state.pop('_saved_page_states', None)
            self._saved_page_states.append(state)
            self._startPage()

        def save(self):
            # Platypus calls showPage only between pages, not after the last page.
            # Parent Canvas.save() would flush that final stream with showPage(); we must
            # capture it here or single-page PDFs never enter _saved_page_states and
            # multi-page PDFs lose the last page footer (and can render incorrectly).
            if len(self._code):
                state = dict(self.__dict__)
                state.pop('_saved_page_states', None)
                self._saved_page_states.append(state)
            if not self._saved_page_states:
                pdfgen_canvas.Canvas.save(self)
                return
            total_pages = len(self._saved_page_states)
            for page_num, state in enumerate(self._saved_page_states, start=1):
                self.__dict__.update(state)
                if self._footer_draw:
                    self._footer_draw(self, page_num, total_pages)
                pdfgen_canvas.Canvas.showPage(self)
            pdfgen_canvas.Canvas.save(self)

    return _DeferredFooterCanvas


def _default_new_curriculum(curricula_qs):
    """
    When no curriculum is selected, prefer new curriculum (NEW / NEW2024).
    Old curriculum remains in the database for legacy rows only.
    Returns (curriculum, id) or (None, None).
    """
    if not curricula_qs.exists():
        return None, None
    for code in ('NEW', 'NEW2024'):
        c = curricula_qs.filter(code=code).first()
        if c:
            return c, c.id
    c = curricula_qs.first()
    return c, (c.id if c else None)


def _new_curriculum_special_event_labels(semester):
    """CSE Tech Carnival / Cultural Fest labels keyed by date (New curriculum only)."""
    labels = {}
    if not semester or not semester.curriculum or semester.curriculum.code == 'OLD':
        return labels
    if semester.cse_tech_carnival_date:
        labels[semester.cse_tech_carnival_date] = 'CSE Tech Carnival'
    if semester.cultural_fest_date:
        labels[semester.cultural_fest_date] = 'Cultural Fest'
    return labels


# Marks / attendance filters: prefer this term when present (GET default, no explicit `term=`).
_MARKS_ATTENDANCE_DEFAULT_TERM_CANDIDATES = ("251 Term", "251")


def _pick_default_term_for_curriculum(curriculum):
    """If the curriculum has a semester using one of the preferred terms, return that value."""
    if not curriculum:
        return ""
    terms = {
        (t or "").strip()
        for t in Semester.objects.filter(curriculum=curriculum)
        .exclude(term__isnull=True)
        .exclude(term="")
        .values_list("term", flat=True)
    }
    for cand in _MARKS_ATTENDANCE_DEFAULT_TERM_CANDIDATES:
        if cand in terms:
            return cand
    # Case-insensitive match; return the DB spelling so queryset filter(term=…) matches.
    lower_map = {(t or "").strip().lower(): (t or "").strip() for t in terms}
    for cand in _MARKS_ATTENDANCE_DEFAULT_TERM_CANDIDATES:
        key = (cand or "").strip().lower()
        if key and key in lower_map:
            return lower_map[key]
    return ""


def _first_semester_id_matching_term(semester_list, term_value):
    """Pick one semester id from a list of Semester instances matching term_value (stable order)."""
    if not semester_list or not (term_value or "").strip():
        return None
    tv = (term_value or "").strip()
    matching = [s for s in semester_list if (s.term or "").strip() == tv]
    if not matching:
        return None
    best = min(matching, key=lambda s: (s.order, s.name or "", s.id))
    return best.id


def _student_session_choices_for_semester(semester_id, centre_id=None):
    """Distinct Student.session values for students enrolled in this semester (optional centre)."""
    if not semester_id:
        return []
    qs = Student.objects.filter(semesters__id=int(semester_id)).exclude(
        session__isnull=True
    ).exclude(session="")
    if centre_id:
        try:
            qs = qs.filter(centre_id=int(centre_id))
        except (ValueError, TypeError):
            pass
    return sorted(
        {(s or "").strip() for s in qs.values_list("session", flat=True)},
        key=lambda x: (x.lower(), x),
    )


def _attendance_calendar_class_dates(semester, course, selected_centre):
    """
    Class-date columns for attendance exports: same rules as attendance_calendar —
    routine + filtered makeup + semester mid-term dates (as possible class days),
    minus effective mid-term exclusions (SemesterCourse.attendance_midterm_override_dates
    when set for semester+centre, else Semester.mid_term_exam_dates).
    """
    def _parse_date_list_csv(value):
        dates = []
        if not value:
            return dates
        for part in str(value).split(','):
            part = part.strip()
            if not part:
                continue
            try:
                dates.append(datetime.strptime(part, "%Y-%m-%d").date())
            except ValueError:
                continue
        return dates

    routine_dates = set(
        NewRoutine.objects.filter(course=course, semester=semester).values_list(
            'class_date', flat=True
        ).distinct()
    )
    course_routines = NewRoutine.objects.filter(
        course=course, semester=semester
    ).values_list('day', flat=True).distinct()

    makeup_dates = []
    if semester.makeup_dates:
        for date_str in semester.makeup_dates.split(','):
            if date_str.strip():
                try:
                    makeup_dates.append(
                        datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
                    )
                except ValueError:
                    pass

    if 'Friday' in course_routines and 'Saturday' in course_routines:
        days_to_show = ['Friday', 'Saturday']
    elif 'Friday' in course_routines:
        days_to_show = ['Friday']
    elif 'Saturday' in course_routines:
        days_to_show = ['Saturday']
    else:
        days_to_show = ['Friday', 'Saturday']

    filtered_makeup_dates = []
    for makeup_date in makeup_dates:
        if makeup_date.strftime('%A') in days_to_show:
            filtered_makeup_dates.append(makeup_date)

    attendance_override_scope = None
    if selected_centre:
        attendance_override_scope = SemesterCourse.objects.filter(
            semester=semester,
            centre=selected_centre,
            attendance_midterm_override_dates__isnull=False,
        ).first()

    if attendance_override_scope and attendance_override_scope.attendance_midterm_override_dates is not None:
        mid_term_source = attendance_override_scope.attendance_midterm_override_dates
    else:
        mid_term_source = semester.mid_term_exam_dates

    mid_term_exam_dates = set()
    if mid_term_source and semester.curriculum and semester.curriculum.code != 'OLD':
        mid_term_exam_dates = set(_parse_date_list_csv(mid_term_source))

    semester_mid_term_dates = set()
    if semester.mid_term_exam_dates and semester.curriculum and semester.curriculum.code != 'OLD':
        semester_mid_term_dates = set(_parse_date_list_csv(semester.mid_term_exam_dates))
    semester_mid_term_dates = {
        d for d in semester_mid_term_dates if d.strftime('%A') in days_to_show
    }

    all_dates = (
        set(routine_dates) | set(filtered_makeup_dates) | set(semester_mid_term_dates)
    )
    all_dates = all_dates - mid_term_exam_dates
    return sorted(all_dates)


def final_exam_mark_sample_for_scope(course, semester, centre_id):
    """
    One FinalExamMark row to read teacher1/2/3_evaluator for the UI.

    When centre_id is set, only marks for students in that study centre are
    considered — same scope as assign_evaluator / save marks. Without this,
    .first() can pick another centre's row and the page shows stale examiners
    after save/reload.
    """
    qs = FinalExamMark.objects.filter(
        course=course,
        semester=semester,
    ).select_related(
        'teacher1_evaluator',
        'teacher2_evaluator',
        'teacher3_evaluator',
        'student',
    )
    if centre_id is not None and centre_id != '':
        try:
            centre = Centre.objects.get(id=int(centre_id))
            qs = qs.filter(student__centre=centre)
        except (Centre.DoesNotExist, ValueError, TypeError):
            pass
    return qs.order_by('student_id').first()


def _sync_final_exam_evaluators_from_semester_course(semester, course, centre):
    """
    Copy final_exam_evaluator1–3 from SemesterCourse onto FinalExamMark rows for students
    in that centre (keeps PDFs / exports that read FinalExamMark in sync).
    """
    sc = SemesterCourse.objects.filter(
        semester=semester, course=course, centre=centre
    ).first()
    if not sc:
        return
    students = Student.objects.filter(semesters=semester)
    students = filter_students_queryset_by_centre(students, str(centre.id))
    marked_by = (
        sc.final_exam_evaluator1
        or sc.final_exam_evaluator2
        or sc.final_exam_evaluator3
        or sc.teacher
    )
    if not marked_by:
        marked_by = Teacher.objects.first()
    if not marked_by:
        return
    for student in students:
        fm, _ = FinalExamMark.objects.get_or_create(
            student=student,
            course=course,
            semester=semester,
            defaults={'marked_by': marked_by},
        )
        fm.teacher1_evaluator = sc.final_exam_evaluator1
        fm.teacher2_evaluator = sc.final_exam_evaluator2
        if course.is_lab:
            fm.teacher3_evaluator = None
        else:
            fm.teacher3_evaluator = sc.final_exam_evaluator3
        if not fm.marked_by:
            fm.marked_by = marked_by
        fm.save()


def time_overlap(start1, end1, start2, end2):
    # Two time ranges overlap if:
    # 1. The start time of one range is less than the end time of the other range
    # 2. AND the start time of the other range is less than the end time of the first range
    # This correctly handles cases where ranges share exactly the same start or end time
    return start1 < end2 and start2 < end1

@login_required
def generate_routine(request):
    # Restrict access to teachers (unless superuser)
    # Check if user has a teacher profile
    try:
        teacher = request.user.teacher
        # If they have a teacher profile but are not superuser, restrict access
        if teacher is not None and not request.user.is_superuser:
            messages.error(request, "You don't have permission to access this page. Teachers can only access Download Routines, Attendance, and Marks pages.")
            return redirect('download-routines')
    except Teacher.DoesNotExist:
        # User doesn't have a teacher profile, allow access
        pass
    except AttributeError:
        # User object doesn't have teacher attribute, allow access
        pass
    
    # Get all curricula
    curricula = Curriculum.objects.filter(is_active=True).order_by('name')
    
    # Get all centres
    centres = Centre.objects.filter(is_active=True).order_by('name')
    
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
    
    # If no curriculum selected, default to new curriculum
    if not selected_curriculum and curricula.exists():
        selected_curriculum, selected_curriculum_id = _default_new_curriculum(curricula)
    
    # Get selected centre from request
    selected_centre_id = request.GET.get('centre') or request.POST.get('centre')
    selected_centre = None
    
    if selected_centre_id:
        try:
            selected_centre_id = int(selected_centre_id)
            selected_centre = Centre.objects.get(id=selected_centre_id)
        except (Centre.DoesNotExist, ValueError):
            selected_centre = None
            selected_centre_id = None
    
    # If no centre selected, default to DRC (Dhaka Regional Center)
    if not selected_centre:
        try:
            selected_centre = Centre.objects.get(code='DRC')
            selected_centre_id = selected_centre.id
        except Centre.DoesNotExist:
            selected_centre = None
            selected_centre_id = None
    
    # Filter semesters and courses by selected curriculum and centre
    if selected_curriculum:
        semesters = Semester.objects.filter(curriculum=selected_curriculum)
        courses = Course.objects.filter(curriculum=selected_curriculum)
    else:
        semesters = Semester.objects.all()
        courses = Course.objects.all()
    
    # Note: Semesters are now shared across centres. Centre-specific filtering happens at SemesterCourse level.
    
    semesters = semesters.order_by('name')
    courses = courses.order_by('code')
    
    # Filter teachers by centre if selected
    if selected_centre:
        teachers = Teacher.objects.filter(centre=selected_centre)
    else:
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
    hide_teacher_name_in_pdf = False  # Default
    
    # If semester is provided but no curriculum, determine curriculum from semester
    # Also determine centre from semester if not already selected
    if selected_semester_id and not selected_curriculum:
        try:
            selected_semester = Semester.objects.get(id=selected_semester_id)
            if selected_semester.curriculum:
                selected_curriculum = selected_semester.curriculum
                selected_curriculum_id = selected_curriculum.id
                # Re-filter semesters and courses by the determined curriculum
                semesters = Semester.objects.filter(curriculum=selected_curriculum).order_by('name')
                courses = Course.objects.filter(curriculum=selected_curriculum).order_by('code')
            # Note: Semesters no longer have a centre. Centre is selected separately.
        except Semester.DoesNotExist:
            selected_semester = None

    # Check if we have any semester courses at all
    if not SemesterCourse.objects.exists():
        messages.warning(request, "No courses have been assigned to any semester yet. Please add courses to a semester first via the 'Semester Courses' menu.")

    generated_routines = []
    overlap_conflicts = []
    form_rows = []

    # On POST, save the teacher_short_name_newline and hide_teacher_name_in_pdf values to the Semester
    if request.method == "POST" and request.POST.get("semester"):
        try:
            selected_semester = Semester.objects.get(id=request.POST.get("semester"))
            # Save the checkbox values to the Semester
            tsn_newline = request.POST.get("teacher_short_name_newline") == "1"
            hide_teacher = request.POST.get("hide_teacher_name_in_pdf") == "1"
            selected_semester.teacher_short_name_newline = tsn_newline
            selected_semester.hide_teacher_name_in_pdf = hide_teacher
            selected_semester.save()
            teacher_short_name_newline = tsn_newline
            hide_teacher_name_in_pdf = hide_teacher
        except Semester.DoesNotExist:
            selected_semester = None
    elif selected_semester_id:
        try:
            selected_semester = Semester.objects.get(id=selected_semester_id)
            teacher_short_name_newline = selected_semester.teacher_short_name_newline
            hide_teacher_name_in_pdf = selected_semester.hide_teacher_name_in_pdf
            # Note: Semesters no longer have a centre. Centre is selected separately.
            # Re-filter by curriculum (centre filtering happens at SemesterCourse level)
            if selected_curriculum:
                semesters = Semester.objects.filter(curriculum=selected_curriculum).order_by('name')
                courses = Course.objects.filter(curriculum=selected_curriculum).order_by('code')
            else:
                semesters = Semester.objects.all().order_by('name')
                courses = Course.objects.all().order_by('code')
            if selected_centre:
                teachers = Teacher.objects.filter(centre=selected_centre)
            else:
                teachers = Teacher.objects.all()
        except Semester.DoesNotExist:
            selected_semester = None

    # Load existing generated routines if semester is selected via GET
    if selected_semester_id and request.method == "GET":
        try:
            selected_semester = Semester.objects.get(id=selected_semester_id)
            existing_routines = NewRoutine.objects.filter(semester=selected_semester).select_related('course', 'semester').order_by('class_date', 'start_time')
            # Filter by centre if selected (semester already has centre, so routines are implicitly filtered)
            # Note: Teacher filtering is no longer needed since teacher is per semester via SemesterCourse
            
            if existing_routines.exists():
                for routine in existing_routines:
                    # Get teacher from SemesterCourse for the selected centre (same logic as PDF export)
                    teacher_name = 'N/A'
                    if routine.course.code == 'CSE4246':
                        teacher_name = 'Supervisor'
                    else:
                        # Get SemesterCourse for this course, semester, and centre
                        semester_course = None
                        if selected_centre:
                            semester_course = SemesterCourse.objects.filter(
                                semester=selected_semester,
                                course=routine.course,
                                centre=selected_centre
                            ).select_related('teacher').first()
                        
                        # Fallback if centre not provided or not found
                        if not semester_course:
                            semester_course = SemesterCourse.objects.filter(
                                semester=selected_semester,
                                course=routine.course
                            ).select_related('teacher').first()
                        
                        if semester_course and semester_course.teacher:
                            teacher = semester_course.teacher
                            teacher_name = teacher.short_name if teacher.short_name else teacher.name
                    
                    generated_routines.append({
                        'id': routine.id,
                        'course_id': routine.course.id,
                        'date': routine.class_date,
                        'day': routine.day,
                        'course_code': routine.course.code,
                        'course_name': routine.course.name,
                        'teacher': teacher_name,
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

                    # New curriculum special events for existing routines display
                    if selected_semester.curriculum and selected_semester.curriculum.code != 'OLD':
                        for special_date in (
                            selected_semester.cse_tech_carnival_date,
                            selected_semester.cultural_fest_date,
                        ):
                            if not special_date:
                                continue
                            day_name = special_date.strftime('%A')
                            if day_name not in ['Friday', 'Saturday']:
                                continue
                            date_str = special_date.strftime('%Y-%m-%d')
                            date_already_exists = any(
                                date[0].strftime('%Y-%m-%d') == date_str for date in unique_dates
                            )
                            if not date_already_exists:
                                unique_dates.append((special_date, day_name))

                    # Add mid-term exam dates to unique_dates for existing routines display (only for new curriculum)
                    if selected_semester.mid_term_exam_dates and selected_semester.curriculum and selected_semester.curriculum.code != 'OLD':
                        mid_term_exam_dates = [
                            datetime.strptime(date.strip(), "%Y-%m-%d").date()
                            for date in selected_semester.mid_term_exam_dates.split(',')
                            if date.strip()
                        ]
                        for mid_term_date in mid_term_exam_dates:
                            day_name = mid_term_date.strftime('%A')
                            # Only add Friday and Saturday mid-term exam dates
                            if day_name in ['Friday', 'Saturday']:
                                date_str = mid_term_date.strftime('%Y-%m-%d')
                                # Check if this date is not already in unique_dates
                                date_already_exists = any(date[0].strftime('%Y-%m-%d') == date_str for date in unique_dates)
                                if not date_already_exists:
                                    unique_dates.append((mid_term_date, day_name))

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

                    # Build a set of mid-term exam dates for existing routines display (only for new curriculum)
                    mid_term_exam_dates_set_existing = set()
                    if selected_semester.mid_term_exam_dates and selected_semester.curriculum and selected_semester.curriculum.code != 'OLD':
                        mid_term_exam_dates_list = [
                            datetime.strptime(date.strip(), "%Y-%m-%d").date()
                            for date in selected_semester.mid_term_exam_dates.split(',')
                            if date.strip()
                        ]
                        mid_term_exam_dates_set_existing = set(mid_term_exam_dates_list)

                    routine_table_rows = []
                    for date, day in unique_dates:
                        row_cells = []
                        slot_idx = 0
                        
                        # Check if this is a mid-term exam date - if so, display "Mid-Term Exam" across entire row
                        if date in mid_term_exam_dates_set_existing:
                            # Create a single cell that spans all time slots
                            total_colspan = len(slot_ranges)
                            row_cells.append({'content': 'Mid-Term Exam', 'colspan': total_colspan, 'is_mid_term_exam': True})
                            routine_table_rows.append({'date': date, 'day': day, 'cells': row_cells})
                            continue  # Skip the rest of the loop for this date

                        special_labels = _new_curriculum_special_event_labels(selected_semester)
                        if date in special_labels:
                            total_colspan = len(slot_ranges) or 1
                            row_cells.append({
                                'content': special_labels[date],
                                'colspan': total_colspan,
                                'is_special_event': True,
                            })
                            routine_table_rows.append({'date': date, 'day': day, 'cells': row_cells})
                            continue
                        
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
                                            'start_time': r.get('start_time'),
                                            'end_time': r.get('end_time'),
                                        }
                                        if r.get('course_id'):
                                            content['course_id'] = r['course_id']
                                        if r.get('id'):
                                            content['routine_id'] = r['id']
                                        cell = {'content': content, 'colspan': colspan, 'is_lunch_break': False}
                                    row_cells.append(cell)
                                    slot_idx += colspan
                                    found = True
                                    break
                            if not found:
                                # Keep slot times so "Click to add course" saves into the correct window
                                row_cells.append({
                                    'content': '',
                                    'colspan': 1,
                                    'is_lunch_break': False,
                                    'start_time': slot_start,
                                    'end_time': slot_end,
                                })
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
        # Get semester from POST, but also check if curriculum and centre are in POST
        selected_semester_id = request.POST.get("semester")
        # Update selected_curriculum_id and selected_centre_id from POST if present
        if request.POST.get("curriculum"):
            try:
                selected_curriculum_id = int(request.POST.get("curriculum"))
                selected_curriculum = Curriculum.objects.get(id=selected_curriculum_id)
            except (Curriculum.DoesNotExist, ValueError):
                pass
        if request.POST.get("centre"):
            try:
                selected_centre_id = int(request.POST.get("centre"))
                selected_centre = Centre.objects.get(id=selected_centre_id)
            except (Centre.DoesNotExist, ValueError):
                pass
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
                # Process and save mid-term exam dates (only for new curriculum)
                mid_term_exam_dates = request.POST.get('mid_term_exam_date_list')
                if mid_term_exam_dates:
                    # Save comma-separated list of mid-term exam dates directly
                    selected_semester.mid_term_exam_dates = mid_term_exam_dates
                elif mid_term_exam_dates == '':
                    # Clear mid-term exam dates if empty string is sent
                    selected_semester.mid_term_exam_dates = None

                # New curriculum special events (after makeup; push SEFE)
                carnival_raw = (request.POST.get('cse_tech_carnival_date') or '').strip()
                if carnival_raw:
                    try:
                        selected_semester.cse_tech_carnival_date = datetime.strptime(
                            carnival_raw, "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        messages.error(request, "Invalid CSE Tech Carnival date.")
                elif 'cse_tech_carnival_date' in request.POST:
                    selected_semester.cse_tech_carnival_date = None

                fest_raw = (request.POST.get('cultural_fest_date') or '').strip()
                if fest_raw:
                    try:
                        selected_semester.cultural_fest_date = datetime.strptime(
                            fest_raw, "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        messages.error(request, "Invalid Cultural Fest date.")
                elif 'cultural_fest_date' in request.POST:
                    selected_semester.cultural_fest_date = None

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
            
            # Get the teacher for this course from SemesterCourse
            try:
                course = Course.objects.get(id=course_id)
                # Get teacher from SemesterCourse for the selected semester and centre
                semester_course_query = SemesterCourse.objects.filter(
                    semester=selected_semester,
                    course=course
                ).select_related('teacher')
                
                # Filter by centre if selected
                if selected_centre:
                    semester_course_query = semester_course_query.filter(centre=selected_centre)
                
                semester_course = semester_course_query.first()
                
                if semester_course and semester_course.teacher:
                    teacher_id = semester_course.teacher.id
                
                # Only check for routines with the same teacher, same day, and overlapping time
                # But exclude the course we're currently checking
                    # Filter by semester and centre (via SemesterCourse)
                    # Note: We need to check routines by their teacher property, not course__teacher
                    routines_query = CurrentRoutine.objects.filter(
                        day=day,
                        semester=selected_semester
                    ).exclude(course_id=course_id)
                    
                    # Filter by centre: only check routines where the course has a SemesterCourse for the selected centre
                    if selected_centre:
                        # Get course IDs that have SemesterCourse for the selected centre
                        centre_course_ids = SemesterCourse.objects.filter(
                            semester=selected_semester,
                            centre=selected_centre
                        ).values_list('course_id', flat=True)
                        routines_query = routines_query.filter(course_id__in=centre_course_ids)
                    
                    for routine in routines_query:
                        if routine.teacher and routine.teacher.id == teacher_id:
                            if time_overlap(start, end, routine.start_time, routine.end_time):
                                # Create a unique key for this conflict to avoid duplicates
                                conflict_key = f"{routine.course.code}_{routine.day}_{routine.start_time}_{routine.end_time}"
                                
                                if conflict_key not in unique_conflicts:
                                    unique_conflicts.add(conflict_key)
                                    overlap_conflicts.append({
                                        "course": routine.course.code,
                                        "teacher": routine.teacher.name if routine.teacher else 'N/A',
                                        "day": routine.day,
                                        "start": routine.start_time.strftime("%H:%M"),
                                        "end": routine.end_time.strftime("%H:%M"),
                                    })
            except Course.DoesNotExist:
                # Skip if course doesn't exist
                continue
                
        if overlap_conflicts:
            messages.error(request, "Time conflicts detected. Please resolve all overlaps before generating a routine.")
            # Re-filter semesters and courses based on selected curriculum (in case they changed)
            if selected_curriculum:
                semesters = Semester.objects.filter(curriculum=selected_curriculum).order_by('name')
                courses = Course.objects.filter(curriculum=selected_curriculum).order_by('code')
            else:
                semesters = Semester.objects.all().order_by('name')
                courses = Course.objects.all().order_by('code')
            # Re-filter teachers based on selected centre
            if selected_centre:
                teachers = Teacher.objects.filter(centre=selected_centre).order_by('name')
            else:
                teachers = Teacher.objects.all().order_by('name')
            return render(request, "bou_routines_app/generate_routine.html", {
                "semesters": semesters,
                "courses": courses,
                "teachers": teachers,
                "generated_routines": generated_routines,
                "overlap_conflicts": overlap_conflicts,
                "form_rows": form_rows,
                "curricula": curricula,
                "selected_curriculum": selected_curriculum,
                "selected_curriculum_id": selected_curriculum_id,
                "centres": centres,
                "selected_centre": selected_centre,
                "selected_centre_id": selected_centre_id,
                "selected_semester_id": selected_semester_id,
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
                    "curricula": curricula,
                    "selected_curriculum": selected_curriculum,
                    "selected_curriculum_id": selected_curriculum.id if selected_curriculum else None,
                    "centres": centres,
                    "selected_centre": selected_centre,
                    "selected_centre_id": selected_centre_id,
                    "selected_semester_id": selected_semester_id,
                })
            
            # Check if there are courses for this semester
            semester_courses = SemesterCourse.objects.filter(semester=selected_semester)
            if not semester_courses.exists():
                messages.warning(request, f"No courses found for semester {selected_semester.name}. Please add courses to this semester first.")
                return render(request, "bou_routines_app/generate_routine.html", {
                    "semesters": semesters,
                    "courses": courses,
                    "teachers": teachers,
                    "curricula": curricula,
                    "selected_curriculum": selected_curriculum,
                    "selected_curriculum_id": selected_curriculum.id if selected_curriculum else None,
                    "centres": centres,
                    "selected_centre": selected_centre,
                    "selected_centre_id": selected_centre_id,
                    "selected_semester_id": selected_semester_id,
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

            # Get mid-term exam dates from the semester model (only for new curriculum)
            mid_term_exam_dates = []
            if selected_semester.mid_term_exam_dates and selected_semester.curriculum and selected_semester.curriculum.code != 'OLD':
                mid_term_exam_dates = [
                    datetime.strptime(date.strip(), "%Y-%m-%d").date()
                    for date in selected_semester.mid_term_exam_dates.split(',')
                    if date.strip()
                ]

            # --- CLASS COUNT LIMIT LOGIC ---
            # Build a map: course_id -> (allowed_classes, is_lab, slot_minutes)
            course_limits = {}
            for sc in semester_courses:
                # Use database field to detect lab course instead of checking course code
                is_lab = sc.course.is_lab
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
                    'semester_course': sc,  # Store SemesterCourse to access teacher
                }

            # Build a set of makeup/reserve dates
            makeup_dates_set = set(makeup_dates)
            # New curriculum special events — no classes scheduled on these dates
            if selected_semester.curriculum and selected_semester.curriculum.code != 'OLD':
                if selected_semester.cse_tech_carnival_date:
                    makeup_dates_set.add(selected_semester.cse_tech_carnival_date)
                if selected_semester.cultural_fest_date:
                    makeup_dates_set.add(selected_semester.cultural_fest_date)
            # Build a set of holiday dates
            holiday_dates_set = set(holiday_dates)
            # Build a set of mid-term exam dates
            mid_term_exam_dates_set = set(mid_term_exam_dates)

            # For each course, build a list of all valid dates (Fridays/Saturdays, not in makeup_dates, not in holidays, not in mid_term_exam_dates, not after end_date)
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
                    if current_date in makeup_dates_set or current_date in holiday_dates_set or current_date in mid_term_exam_dates_set:
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
                    new_routine = NewRoutine.objects.create(
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
                    # Get teacher from SemesterCourse
                    teacher_name = 'N/A'
                    if limit.get('semester_course') and limit['semester_course'].teacher:
                        teacher_name = limit['semester_course'].teacher.name
                    
                    generated_routines.append({
                        'id': new_routine.id,
                        'course_id': limit['course'].id,
                        'date': d,
                        'day': limit['day'],
                        'course_code': limit['course'].code,
                        'course_name': limit['course'].name,
                        'teacher': teacher_name,
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

            # Add mid-term exam dates to unique_dates as blank rows (only date and day, no classes)
            if mid_term_exam_dates:
                for mid_term_date in mid_term_exam_dates:
                    # Only add if the mid-term exam date is within the date range
                    if start_date <= mid_term_date <= end_date:
                        day_name = mid_term_date.strftime('%A')
                        # Only add Friday and Saturday mid-term exam dates
                        if day_name in ['Friday', 'Saturday']:
                            date_str = mid_term_date.strftime('%Y-%m-%d')
                            # Check if this date is not already in unique_dates
                            date_already_exists = any(date[0].strftime('%Y-%m-%d') == date_str for date in unique_dates)
                            if not date_already_exists:
                                unique_dates.append((mid_term_date, day_name))

            # New curriculum: CSE Tech Carnival / Cultural Fest rows (after makeup)
            if selected_semester.curriculum and selected_semester.curriculum.code != 'OLD':
                for special_date in (
                    selected_semester.cse_tech_carnival_date,
                    selected_semester.cultural_fest_date,
                ):
                    if not special_date:
                        continue
                    day_name = special_date.strftime('%A')
                    if day_name not in ['Friday', 'Saturday']:
                        continue
                    date_str = special_date.strftime('%Y-%m-%d')
                    date_already_exists = any(
                        date[0].strftime('%Y-%m-%d') == date_str for date in unique_dates
                    )
                    if not date_already_exists:
                        unique_dates.append((special_date, day_name))

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
                
                # Check if this is a mid-term exam date - if so, display "Mid-Term Exam" across entire row
                if date in mid_term_exam_dates_set:
                    # Create a single cell that spans all time slots
                    total_colspan = len(slot_ranges)
                    row_cells.append({'content': 'Mid-Term Exam', 'colspan': total_colspan, 'is_mid_term_exam': True})
                    routine_table_rows.append({'date': date, 'day': day, 'cells': row_cells})
                    continue  # Skip the rest of the loop for this date

                special_labels = _new_curriculum_special_event_labels(selected_semester)
                if date in special_labels:
                    total_colspan = len(slot_ranges) or 1
                    row_cells.append({
                        'content': special_labels[date],
                        'colspan': total_colspan,
                        'is_special_event': True,
                    })
                    routine_table_rows.append({'date': date, 'day': day, 'cells': row_cells})
                    continue
                
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
                                    'start_time': r.get('start_time'),
                                    'end_time': r.get('end_time'),
                                }
                                if r.get('course_id'):
                                    content['course_id'] = r['course_id']
                                if r.get('id'):
                                    content['routine_id'] = r['id']
                                cell = {'content': content, 'colspan': colspan, 'is_lunch_break': False}
                            row_cells.append(cell)
                            slot_idx += colspan
                            found = True
                            break
                    if not found:
                        # If this is a makeup/reserved date, show 'Reserved Class'
                        if date in makeup_dates:
                            row_cells.append({
                                'content': 'Review Class',
                                'colspan': 1,
                                'is_makeup_class': True,
                                'start_time': slot_start,
                                'end_time': slot_end,
                            })
                        else:
                            # Keep slot times so "Click to add course" saves into the correct window
                            row_cells.append({
                                'content': '',
                                'colspan': 1,
                                'is_lunch_break': False,
                                'start_time': slot_start,
                                'end_time': slot_end,
                            })
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
                "selected_semester_id": selected_semester_id,
                "curricula": curricula,
                "selected_curriculum": selected_curriculum,
                "selected_curriculum_id": selected_curriculum.id if selected_curriculum else None,
                "centres": centres,
                "selected_centre": selected_centre,
                "selected_centre_id": selected_centre_id,
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
        "hide_teacher_name_in_pdf": hide_teacher_name_in_pdf,
        "curricula": curricula,
        "selected_curriculum": selected_curriculum,
        "selected_curriculum_id": selected_curriculum.id if selected_curriculum else None,
        "centres": centres,
        "selected_centre": selected_centre,
        "selected_centre_id": selected_centre_id,
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
            "special_event_labels": (
                _new_curriculum_special_event_labels(selected_semester)
                if selected_semester else {}
            ),
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
    # Restrict access to teachers (unless superuser)
    # Check if user has a teacher profile
    try:
        teacher = request.user.teacher
        # If they have a teacher profile but are not superuser, restrict access
        if teacher is not None and not request.user.is_superuser:
            messages.error(request, "You don't have permission to access this page. Teachers can only access Download Routines, Attendance, and Marks pages.")
            return redirect('download-routines')
    except (Teacher.DoesNotExist, AttributeError):
        # User doesn't have a teacher profile, allow access
        pass
    
    # Get all curricula
    curricula = Curriculum.objects.filter(is_active=True).order_by('name')
    
    # Get all centres
    centres = Centre.objects.filter(is_active=True).order_by('name')
    
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
    
    # If no curriculum selected, default to new curriculum
    if not selected_curriculum and curricula.exists():
        selected_curriculum, selected_curriculum_id = _default_new_curriculum(curricula)
    
    # Get selected centre from request
    selected_centre_id = request.GET.get('centre') or request.POST.get('centre')
    selected_centre = None
    
    if selected_centre_id:
        try:
            selected_centre_id = int(selected_centre_id)
            selected_centre = Centre.objects.get(id=selected_centre_id)
        except (Centre.DoesNotExist, ValueError):
            selected_centre = None
            selected_centre_id = None
    
    # If no centre selected, default to DRC (Dhaka Regional Center)
    if not selected_centre:
        try:
            selected_centre = Centre.objects.get(code='DRC')
            selected_centre_id = selected_centre.id
        except Centre.DoesNotExist:
            selected_centre = None
            selected_centre_id = None
    
    # Filter semesters and courses by selected curriculum and centre
    if selected_curriculum:
        semesters = Semester.objects.filter(curriculum=selected_curriculum)
        courses = Course.objects.filter(curriculum=selected_curriculum)
    else:
        semesters = Semester.objects.all()
        courses = Course.objects.all()
    
    # Note: Semesters are now shared across centres. Centre-specific filtering happens at SemesterCourse level.
    
    semesters = semesters.order_by('name')
    courses = courses.order_by('code')
    
    # Filter teachers by centre if selected
    if selected_centre:
        teachers = Teacher.objects.filter(centre=selected_centre).order_by('name')
    else:
        teachers = Teacher.objects.all().order_by('name')
    
    # Get program coordinators (filter by centre if selected)
    if selected_centre:
        program_coordinators = ProgramCoordinator.objects.filter(centre=selected_centre, is_active=True).select_related('teacher', 'centre').order_by('teacher__name')
    else:
        program_coordinators = ProgramCoordinator.objects.filter(is_active=True).select_related('teacher', 'centre').order_by('centre', 'teacher__name')
    
    context = {
        "semesters": semesters,
        "courses": courses,
        "teachers": teachers,
        "curricula": curricula,
        "selected_curriculum": selected_curriculum,
        "selected_curriculum_id": selected_curriculum.id if selected_curriculum else None,
        "centres": centres,
        "selected_centre": selected_centre,
        "selected_centre_id": selected_centre_id,
        "program_coordinators": program_coordinators,
    }
    
    # Debug output
    print(f"DEBUG: selected_curriculum_id = {selected_curriculum_id}")
    print(f"DEBUG: selected_curriculum = {selected_curriculum}")
    print(f"DEBUG: context selected_curriculum_id = {context['selected_curriculum_id']}")
    print(f"DEBUG: curricula = {[(c.id, c.name) for c in curricula]}")
    
    
    
    if request.method == "POST":
        semester_id = request.POST.get("semester")
        context["selected_semester_id"] = semester_id
        
        # Get parameters for redirect (preserve on errors)
        selected_curriculum_id = request.POST.get("curriculum") or request.GET.get('curriculum')
        selected_centre_id = request.POST.get("centre") or request.GET.get('centre')
        
        # Helper function to build redirect URL with preserved parameters
        def build_redirect_url():
            base_url = reverse('update-semester-courses')
            params = {}
            if selected_curriculum_id:
                params['curriculum'] = selected_curriculum_id
            if selected_centre_id:
                params['centre'] = selected_centre_id
            if semester_id:
                params['semester'] = semester_id
            if params:
                query_string = urlencode(params)
                return f"{base_url}?{query_string}"
            return base_url
        
        if not semester_id:
            messages.error(request, "Semester is required.")
            return redirect(build_redirect_url())
        
        try:
            semester = Semester.objects.get(id=semester_id)
        except Semester.DoesNotExist:
            messages.error(request, "Invalid semester selected.")
            return redirect(build_redirect_url())

        # Update semester info fields from POST
        semester.semester_full_name = request.POST.get("semester_full_name", semester.semester_full_name)
        semester.term = request.POST.get("term", semester.term)
        semester.session = request.POST.get("session", semester.session)
        
        # Get centre from request first (needed for validation)
        centre_id = request.POST.get("centre")
        if not centre_id:
            messages.error(request, "Centre is required when updating semester courses.")
            return redirect(build_redirect_url())
        
        try:
            centre = Centre.objects.get(id=centre_id)
        except Centre.DoesNotExist:
            messages.error(request, "Invalid centre selected.")
            return redirect(build_redirect_url())
        
        # Update program coordinator - now centre-specific using SemesterCentreCoordinator
        program_coordinator_id = request.POST.get("program_coordinator")
        if program_coordinator_id:
            try:
                coordinator = ProgramCoordinator.objects.get(id=program_coordinator_id)
                # Validate that the coordinator belongs to the selected centre
                if coordinator.centre != centre:
                    messages.error(request, f"Selected Program Coordinator belongs to {coordinator.centre.name}, but you selected {centre.name}. Please select a coordinator for the correct centre.")
                    return redirect(build_redirect_url())
                
                # Create or update SemesterCentreCoordinator for this semester/centre combination
                SemesterCentreCoordinator.objects.update_or_create(
                    semester=semester,
                    centre=centre,
                    defaults={'program_coordinator': coordinator}
                )
            except ProgramCoordinator.DoesNotExist:
                pass
        elif program_coordinator_id == '':
            # Clear coordinator for this specific semester/centre combination
            SemesterCentreCoordinator.objects.filter(semester=semester, centre=centre).delete()
        
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

        # Centre is already retrieved above for validation
        
        # Delete existing SemesterCourse records for this semester and centre
        SemesterCourse.objects.filter(semester=semester, centre=centre).delete()
        
        course_ids = request.POST.getlist("courses[]")
        teacher_ids = request.POST.getlist("teachers[]")
        number_of_classes = request.POST.getlist("classes")
        for i, course_id in enumerate(course_ids):
            course = Course.objects.get(id=course_id)
            try:
                num_classes = int(number_of_classes[i]) if i < len(number_of_classes) else 1
                if num_classes < 1:
                    num_classes = 0
            except (ValueError, IndexError):
                num_classes = 0
            
            # Create SemesterCourse with centre
            semester_course = SemesterCourse.objects.create(
                semester=semester,
                course=course,
                centre=centre,
                number_of_classes=num_classes
            )
            if i < len(teacher_ids) and teacher_ids[i]:
                semester_course.teacher = Teacher.objects.get(id=teacher_ids[i])
                semester_course.save()
        #messages.success(request, f"Successfully updated courses for {semester.name}")
        # Redirect to the same page with selected semester, curriculum, centre and success param
        # Use the POST values for redirect (they're already set in build_redirect_url scope)
        base_url = reverse('update-semester-courses')
        params = {'semester': semester_id, 'success': 1}
        if selected_curriculum_id:
            params['curriculum'] = selected_curriculum_id
        if selected_centre_id:
            params['centre'] = selected_centre_id
        query_string = urlencode(params)
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
        centre_id = request.GET.get("centre_id")
        curriculum_id = request.GET.get("curriculum_id")
        if semester_id:
            try:
                semester = Semester.objects.get(id=semester_id)
                semester_courses = SemesterCourse.objects.filter(semester_id=semester_id).select_related('course', 'course__curriculum', 'teacher', 'centre')
                
                # Filter by centre if provided
                if centre_id:
                    try:
                        # Convert to int to ensure proper comparison
                        centre_id = int(centre_id)
                        centre = Centre.objects.get(id=centre_id)
                        semester_courses = semester_courses.filter(centre=centre)
                        print(f"DEBUG: Filtering by centre_id={centre_id}, found {semester_courses.count()} courses")
                    except (Centre.DoesNotExist, ValueError):
                        print(f"DEBUG: Centre not found or invalid centre_id: {centre_id}")
                        pass
                
                # Filter by curriculum if provided
                if curriculum_id:
                    try:
                        curriculum = Curriculum.objects.get(id=curriculum_id)
                        semester_courses = semester_courses.filter(course__curriculum=curriculum)
                    except Curriculum.DoesNotExist:
                        pass
                
                # Build courses_data, ensuring we only return one entry per course
                # If centre is filtered, we'll only get one entry per course anyway
                # But if not filtered, we need to deduplicate by course.id
                courses_dict = {}
                for sc in semester_courses:
                    course_id = sc.course.id
                    # If centre is filtered, we only want courses for that centre
                    # If not filtered, we'll take the first occurrence of each course
                    if course_id not in courses_dict:
                        courses_dict[course_id] = {
                    'id': sc.course.id,
                    'code': sc.course.code,
                    'name': sc.course.name,
                            'teacher_name': sc.effective_teacher.name if sc.effective_teacher else 'N/A',
                            'teacher_id': sc.effective_teacher.id if sc.effective_teacher else None,
                    'number_of_classes': sc.number_of_classes
                        }
                
                courses_data = list(courses_dict.values())
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
                
                mid_term_exam_dates_info = None
                if semester.mid_term_exam_dates:
                    mid_term_exam_dates_info = semester.mid_term_exam_dates
                
                # Add all semester info fields
                # Get coordinator for this specific semester/centre combination
                coordinator_id = None
                coordinator = None
                if centre_id:
                    try:
                        centre = Centre.objects.get(id=centre_id)
                        semester_centre_coordinator = SemesterCentreCoordinator.objects.filter(
                            semester=semester,
                            centre=centre
                        ).select_related('program_coordinator', 'program_coordinator__teacher').first()
                        if semester_centre_coordinator:
                            coordinator = semester_centre_coordinator.program_coordinator
                            coordinator_id = coordinator.id
                    except Centre.DoesNotExist:
                        pass
                
                semester_data = {
                    'semester_full_name': semester.semester_full_name,
                    'term': semester.term,
                    'session': semester.session,
                    'centre': '',  # Centre is now at SemesterCourse level, not Semester level
                    'program_coordinator_id': coordinator_id,
                    'contact_person': coordinator.teacher.name if coordinator and coordinator_id else '',
                    'contact_person_designation': coordinator.designation if coordinator and coordinator_id else '',
                    'contact_person_secondary_designation': coordinator.secondary_designation if coordinator and coordinator_id else '',
                    'contact_person_phone': coordinator.phone if coordinator and coordinator_id else '',
                    'contact_person_email': coordinator.email if coordinator and coordinator_id else '',
                    'theory_class_duration_minutes': semester.theory_class_duration_minutes,
                    'lab_class_duration_minutes': semester.lab_class_duration_minutes,
                }
                return JsonResponse({
                    'courses': courses_data,
                    'lunch_break': lunch_break_info,
                    'date_range': date_range_info,
                    'holidays': holidays_info,
                    'makeup_dates': makeup_dates_info,
                    'mid_term_exam_dates': mid_term_exam_dates_info,
                    'cse_tech_carnival_date': (
                        semester.cse_tech_carnival_date.strftime('%Y-%m-%d')
                        if semester.cse_tech_carnival_date else None
                    ),
                    'cultural_fest_date': (
                        semester.cultural_fest_date.strftime('%Y-%m-%d')
                        if semester.cultural_fest_date else None
                    ),
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
                existing_routines = NewRoutine.objects.filter(semester=semester).select_related('course', 'semester').order_by('class_date', 'start_time')
                
                routines_data = []
                if existing_routines.exists():
                    for routine in existing_routines:
                        routines_data.append({
                            'id': routine.id,
                            'date': routine.class_date.strftime('%Y-%m-%d'),
                            'day': routine.day,
                            'course_code': routine.course.code,
                            'course_name': routine.course.name,
                            'teacher': routine.teacher.name if routine.teacher else 'N/A',
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
                    routines = CurrentRoutine.objects.filter(semester_id=semester_id).select_related('course', 'semester')
                    
                    # Format the data for response
                    routines_data = [{
                        'course_id': routine.course.id,
                        'course_code': routine.course.code,
                        'course_name': routine.course.name,
                        'teacher_name': routine.teacher.name if routine.teacher else 'N/A',
                        'teacher_id': routine.teacher.id if routine.teacher else None,
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
            # Note: We can't filter by course__teacher_id anymore, so we filter by day and check teacher in Python
            query = CurrentRoutine.objects.filter(day=day)
            
            # Exclude current course if provided (for editing scenarios)
            if course_id:
                query = query.exclude(course_id=course_id)
                
            for routine in query:
                # Check if routine has the same teacher
                if routine.teacher and routine.teacher.id == teacher_id:
                    if time_overlap(start, end, routine.start_time, routine.end_time):
                        overlaps.append({
                            "course": routine.course.code,
                            "course_name": routine.course.name,
                            "teacher": routine.teacher.name if routine.teacher else 'N/A',
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
            routine_id = _parse_optional_pk(request.POST.get('routine_id'))
            new_course_id = _parse_optional_pk(request.POST.get('course_id'))
            
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
                    
                    # Get centre from request (if available)
                    centre_id = request.POST.get('centre_id')
                    selected_centre = None
                    if centre_id:
                        try:
                            selected_centre = Centre.objects.get(id=centre_id)
                        except Centre.DoesNotExist:
                            pass
                    
                    # Get teacher from SemesterCourse
                    teacher = None
                    if selected_centre:
                        semester_course = SemesterCourse.objects.filter(
                            semester=routine.semester,
                            course=new_course,
                            centre=selected_centre
                        ).select_related('teacher').first()
                        if semester_course:
                            teacher = semester_course.effective_teacher
                    
                    # Fallback: try to get any SemesterCourse for this course/semester
                    if not teacher:
                        semester_course = SemesterCourse.objects.filter(
                            semester=routine.semester,
                            course=new_course
                        ).select_related('teacher').first()
                        if semester_course:
                            teacher = semester_course.effective_teacher
                    
                    teacher_name, teacher_short_name = _routine_teacher_payload(new_course, teacher)
                    
                    # Return updated course information
                    return JsonResponse({
                        "success": True,
                        "course_code": new_course.code,
                        "course_name": new_course.name,
                        "teacher_name": teacher_name,
                        "teacher_short_name": teacher_short_name
                    })
                except NewRoutine.DoesNotExist:
                    return JsonResponse({"error": "Routine not found"}, status=404)
            else:
                # Creating new routine entry (or updating a slot whose routine_id was missing)
                date_str = request.POST.get('date')
                day = request.POST.get('day')
                semester_id = _parse_optional_pk(request.POST.get('semester_id'))
                start_time_str = request.POST.get('start_time')
                end_time_str = request.POST.get('end_time')
                
                if not all([date_str, day, semester_id, start_time_str, end_time_str]):
                    return JsonResponse({"error": "Missing required fields for new routine"}, status=400)
                
                try:
                    semester = Semester.objects.get(id=semester_id)
                    class_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    start_time = datetime.strptime(start_time_str, '%H:%M').time()
                    end_time = datetime.strptime(end_time_str, '%H:%M').time()
                    
                    # Get centre from request (if available)
                    centre_id = request.POST.get('centre_id')
                    selected_centre = None
                    if centre_id:
                        try:
                            selected_centre = Centre.objects.get(id=centre_id)
                        except Centre.DoesNotExist:
                            pass
                    
                    # If no centre provided, try to get from semester or use first available
                    if not selected_centre:
                        # Try to get centre from SemesterCourse if available
                        semester_course = SemesterCourse.objects.filter(
                            semester=semester,
                            course=new_course
                        ).first()
                        if semester_course:
                            selected_centre = semester_course.centre
                    
                    original_course_id = _parse_optional_pk(request.POST.get('original_course_id'))
                    slot_query = NewRoutine.objects.filter(
                        semester=semester,
                        class_date=class_date,
                        day=day,
                        start_time=start_time,
                        end_time=end_time,
                    )
                    existing_routine = None
                    if original_course_id:
                        existing_routine = slot_query.filter(course_id=original_course_id).first()
                    if not existing_routine:
                        existing_routine = slot_query.first()

                    if existing_routine:
                        existing_routine.course = new_course
                        existing_routine.save()
                        new_routine = existing_routine
                    else:
                        new_routine = NewRoutine.objects.create(
                            semester=semester,
                            course=new_course,
                            class_date=class_date,
                            day=day,
                            start_time=start_time,
                            end_time=end_time
                        )
                    
                    # Get teacher from SemesterCourse
                    teacher = None
                    if selected_centre:
                        semester_course = SemesterCourse.objects.filter(
                            semester=semester,
                            course=new_course,
                            centre=selected_centre
                        ).select_related('teacher').first()
                        if semester_course:
                            teacher = semester_course.effective_teacher
                    
                    # Fallback: try to get any SemesterCourse for this course/semester
                    if not teacher:
                        semester_course = SemesterCourse.objects.filter(
                            semester=semester,
                            course=new_course
                        ).select_related('teacher').first()
                        if semester_course:
                            teacher = semester_course.effective_teacher
                    
                    teacher_name, teacher_short_name = _routine_teacher_payload(new_course, teacher)
                    
                    # Return new routine information
                    return JsonResponse({
                        "success": True,
                        "routine_id": new_routine.id,
                        "course_code": new_course.code,
                        "course_name": new_course.name,
                        "teacher_name": teacher_name,
                        "teacher_short_name": teacher_short_name
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
            routine_id = _parse_optional_pk(request.POST.get('routine_id'))
            
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


def _centre_filename_prefix(centre):
    """Prefix download filenames with the study centre short code (e.g. DRC_, DUET_)."""
    code = (getattr(centre, 'code', None) or '').strip()
    return f'{code}_' if code else ''


def _parse_optional_pk(value):
    """Parse a primary key from request data; treat None/'None'/blank as missing."""
    if value in (None, '', 'None', 'null', 'undefined'):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _routine_teacher_payload(course, teacher):
    if course and course.code == 'CSE4246':
        return 'Supervisor', 'Supervisor'
    teacher_name = teacher.name if teacher else 'N/A'
    teacher_short_name = teacher.short_name if teacher and teacher.short_name else teacher_name
    return teacher_name, teacher_short_name

@login_required
def export_to_excel(request, semester_id):
    """Export the routine to Excel file"""
    try:
        selected_semester = Semester.objects.get(id=semester_id)
        
        # Get centre from request parameter
        centre_id = request.GET.get('centre')
        centre = None
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
            except Centre.DoesNotExist:
                pass

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
        routines_by_date = {date: day for date, day in unique_dates_days}
        all_dates = set(routines_by_date.keys()) | set(makeup_dates)
        special_event_labels = {}
        if selected_semester.curriculum and selected_semester.curriculum.code != 'OLD':
            if selected_semester.cse_tech_carnival_date:
                all_dates.add(selected_semester.cse_tech_carnival_date)
                special_event_labels[selected_semester.cse_tech_carnival_date] = 'CSE Tech Carnival'
            if selected_semester.cultural_fest_date:
                all_dates.add(selected_semester.cultural_fest_date)
                special_event_labels[selected_semester.cultural_fest_date] = 'Cultural Fest'
        sorted_dates = sorted(all_dates)
        # Write data with merging
        row = 3
        for date_idx, date in enumerate(sorted_dates):
            day = routines_by_date.get(date, date.strftime('%A'))
            is_even_row = (date_idx % 2 == 1)
            worksheet.write(row, 0, date, date_format if not is_even_row else even_row_bg_format)
            worksheet.write(row, 1, day, cell_format if not is_even_row else even_row_bg_format)

            if date in special_event_labels:
                label = special_event_labels[date]
                if len(slot_ranges) > 1:
                    worksheet.merge_range(
                        row, 2, row, 1 + len(slot_ranges),
                        label,
                        cell_format if not is_even_row else even_row_bg_format,
                    )
                elif len(slot_ranges) == 1:
                    worksheet.write(row, 2, label, cell_format if not is_even_row else even_row_bg_format)
                row += 1
                continue
            # Build routines for this row
            routines_for_row = []
            for r in routines:
                if r.class_date == date and r.day == day:
                    # Get teacher from SemesterCourse for the selected centre
                    teacher_name = 'N/A'
                    if r.course.code == 'CSE4246':
                        teacher_name = 'Supervisor'
                    else:
                        # Get SemesterCourse for this course, semester, and centre
                        semester_course = None
                        if centre:
                            semester_course = SemesterCourse.objects.filter(
                                semester=selected_semester,
                                course=r.course,
                                centre=centre
                            ).select_related('teacher').first()
                        
                        # Fallback if centre not provided or not found
                        if not semester_course:
                            semester_course = SemesterCourse.objects.filter(
                                semester=selected_semester,
                                course=r.course
                            ).select_related('teacher').first()
                        
                        if semester_course and semester_course.teacher:
                            teacher = semester_course.teacher
                            teacher_name = teacher.short_name if teacher.short_name else teacher.name
                    
                    routines_for_row.append({
                        'course_code': r.course.code,
                        'teacher': teacher_name,
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
                        worksheet.write(row, col_idx, "Review Class", cell_format if not is_even_row else even_row_bg_format)
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
        response['Content-Disposition'] = f'attachment; filename="{_centre_filename_prefix(centre)}{selected_semester.name}_Routine.xlsx"'
        return response

    except Exception as e:
        return HttpResponse(f"Error generating Excel file: {str(e)}", status=500)

@login_required
def download_routines(request):
    """Display the last generated routines for all semesters"""
    # Get all curricula and centres for filters
    curricula = Curriculum.objects.filter(is_active=True).order_by('name')
    centres = Centre.objects.filter(is_active=True).order_by('name')
    
    # Get selected curriculum from request
    selected_curriculum_id = request.GET.get('curriculum')
    selected_curriculum = None
    curriculum_param_present = 'curriculum' in request.GET
    
    if selected_curriculum_id:
        try:
            selected_curriculum_id = int(selected_curriculum_id)
            selected_curriculum = Curriculum.objects.get(id=selected_curriculum_id)
        except (Curriculum.DoesNotExist, ValueError):
            selected_curriculum = None
            selected_curriculum_id = None
    
    # Only set default if curriculum parameter was not in the request at all
    if not selected_curriculum and not curriculum_param_present and curricula.exists():
        selected_curriculum, selected_curriculum_id = _default_new_curriculum(curricula)
    
    # Get selected centre from request
    selected_centre_id = request.GET.get('centre')
    selected_centre = None
    centre_param_present = 'centre' in request.GET
    
    if selected_centre_id:
        try:
            selected_centre_id = int(selected_centre_id)
            selected_centre = Centre.objects.get(id=selected_centre_id)
        except (Centre.DoesNotExist, ValueError):
            selected_centre = None
            selected_centre_id = None
    
    # Only set default if centre parameter was not in the request at all
    if not selected_centre and not centre_param_present and centres.exists():
        try:
            selected_centre = Centre.objects.get(code='DRC')
            selected_centre_id = selected_centre.id
        except Centre.DoesNotExist:
            selected_centre = None
            selected_centre_id = None
    
    # Get all semesters that have generated routines
    semesters_with_routines = Semester.objects.filter(
        newroutine__isnull=False
    ).distinct()
    
    # Filter by curriculum if selected
    if selected_curriculum:
        semesters_with_routines = semesters_with_routines.filter(curriculum=selected_curriculum)
    
    # Filter by centre if selected (through SemesterCourse)
    if selected_centre:
        semesters_with_routines = semesters_with_routines.filter(
            semestercourse__centre=selected_centre
        ).distinct()
    
    semesters_with_routines = semesters_with_routines.order_by('order', 'name')
    
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
                            'id': r.id,
                            'course_id': r.course.id,
                            'course_code': r.course.code,
                            'teacher': 'Supervisor' if r.course.code == 'CSE4246' else (r.teacher.short_name if r.teacher and r.teacher.short_name else (r.teacher.name if r.teacher else 'N/A')),
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
                                    'start_time': r.get('start_time'),
                                    'end_time': r.get('end_time'),
                                }
                                if r.get('course_id'):
                                    content['course_id'] = r['course_id']
                                if r.get('id'):
                                    content['routine_id'] = r['id']
                                cell = {'content': content, 'colspan': colspan, 'is_lunch_break': False}
                            row_cells.append(cell)
                            slot_idx += colspan
                            found = True
                            break
                    if not found:
                        # Keep slot times so "Click to add course" saves into the correct window
                        row_cells.append({
                            'content': '',
                            'colspan': 1,
                            'is_lunch_break': False,
                            'start_time': slot_start,
                            'end_time': slot_end,
                        })
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
            # Get centre from selected_centre if available, otherwise from first SemesterCourse for this semester
            if selected_centre:
                centre_id = selected_centre.id
                centre_name = selected_centre.name
            else:
                first_sc = SemesterCourse.objects.filter(semester=semester).select_related('centre').first()
                centre_id = first_sc.centre.id if first_sc and first_sc.centre else None
                centre_name = first_sc.centre.name if first_sc and first_sc.centre else None
            
            semester_routines.append({
                'semester': semester,
                'routine_table_rows': routine_table_rows,
                'time_slot_labels': [label for _, _, label in slot_ranges],
                'routine_count': latest_routines.count(),
                'makeup_dates': makeup_dates,
                'centre_id': centre_id,  # Add centre_id for PDF export links
                'centre_name': centre_name,  # Add centre_name for display
            })
    
    return render(request, 'bou_routines_app/download_routines.html', {
        'semester_routines': semester_routines,
        'curricula': curricula,
        'selected_curriculum': selected_curriculum,
        'selected_curriculum_id': selected_curriculum_id,
        'centres': centres,
        'selected_centre': selected_centre,
        'selected_centre_id': selected_centre_id,
    })

@login_required
def export_to_pdf(request, semester_id):
    """Export the routine to PDF file"""
    try:
        selected_semester = Semester.objects.get(id=semester_id)
        # Get centre from request parameter
        centre_id = request.GET.get('centre')
        centre = None
        centre_name = ''
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
                centre_name = centre.name
            except Centre.DoesNotExist:
                pass

        # Read the teacher short name display option from GET params
        teacher_short_name_newline = request.GET.get('teacher_short_name_newline', '1') == '1'
        # Read the hide teacher name option from GET params or from semester
        hide_teacher_name_in_pdf = request.GET.get('hide_teacher_name_in_pdf', '0') == '1'
        if not hide_teacher_name_in_pdf:
            hide_teacher_name_in_pdf = selected_semester.hide_teacher_name_in_pdf

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
        # centre_name is already set from request parameter above (in export_to_pdf function)
        # If not set, try to get from first SemesterCourse for this semester
        if not centre_name:
            first_sc = SemesterCourse.objects.filter(semester=selected_semester).select_related('centre').first()
            if first_sc and first_sc.centre:
                centre_name = first_sc.centre.name
        if commencement:
            left_content.append(Paragraph(f'<b>Date of Commencement:</b> {commencement}', header_style_normal))
        if centre_name:
            left_content.append(Paragraph(f'<b>Study Center:</b> {centre_name}', header_style_normal))

        # Build right column (contact person box)
        contact_lines = []
        # Get coordinator for this specific semester/centre combination
        coordinator = None
        if centre:
            semester_centre_coordinator = SemesterCentreCoordinator.objects.filter(
                semester=selected_semester,
                centre=centre
            ).select_related('program_coordinator', 'program_coordinator__teacher').first()
            if semester_centre_coordinator:
                coordinator = semester_centre_coordinator.program_coordinator
        contact_info_lines = []
        
        if coordinator:
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
                colWidths=[190],
                hAlign='RIGHT',
                style=TableStyle([
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                    ('TOPPADDING', (0,0), (-1,-1), -3),
                    ('LEFTPADDING', (0,0), (-1,-1), 0),
                    ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ])
            )
            if coordinator.teacher:
                contact_info_lines.append(coordinator.teacher.name)
            if coordinator.designation:
                contact_info_lines.append(coordinator.designation)
            if coordinator.secondary_designation:
                contact_info_lines.append(coordinator.secondary_designation)
        contact_info_lines.append('Bangladesh Open University')
        if coordinator.phone:
            contact_info_lines.append(f'Phone/Whatsapp: {coordinator.phone}')
        if coordinator.email:
            contact_info_lines.append(f'email:{coordinator.email}')
        else:
            # Default contact info if no coordinator
            contact_info_lines.append('Bangladesh Open University')
            # Create a simple label table for when there's no coordinator
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
            contact_label_table = Table(
                [[contact_label]],
                colWidths=[190],
                hAlign='RIGHT',
                style=TableStyle([
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                    ('TOPPADDING', (0,0), (-1,-1), -3),
                    ('LEFTPADDING', (0,0), (-1,-1), 0),
                    ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ])
            )
        
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
            colWidths=[190],
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
            colWidths=[available_width-190],
            hAlign='LEFT',
            style=TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ])
        )
        two_col_table = Table(
            [[left_box_table, contact_table]],
            colWidths=[available_width-190, 190],
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

        # Get the routines from the database, filtered by centre if provided
        routines = NewRoutine.objects.filter(semester=selected_semester)
        
        # Filter by centre: only include routines where the course has a SemesterCourse for the selected centre
        if centre:
            # Get course IDs that have SemesterCourse for the selected centre
            centre_course_ids = SemesterCourse.objects.filter(
                semester=selected_semester,
                centre=centre
            ).values_list('course_id', flat=True)
            routines = routines.filter(course_id__in=centre_course_ids)
        
        routines = routines.order_by('class_date', 'start_time')

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
        # Merge all routine dates, makeup dates, and mid-term exam dates, sort, and ensure each date appears only once in order
        makeup_dates = []
        if selected_semester.makeup_dates:
            makeup_dates = [
                datetime.strptime(date.strip(), "%Y-%m-%d").date()
                for date in selected_semester.makeup_dates.split(',')
                if date.strip()
            ]
        # Get mid-term exam dates (only for new curriculum)
        mid_term_exam_dates = []
        if selected_semester.mid_term_exam_dates and selected_semester.curriculum and selected_semester.curriculum.code != 'OLD':
            mid_term_exam_dates = [
                datetime.strptime(date.strip(), "%Y-%m-%d").date()
                for date in selected_semester.mid_term_exam_dates.split(',')
                if date.strip()
            ]
        day_by_date = {date: day for date, day in unique_dates_days}
        all_dates = set(day_by_date.keys()) | set(makeup_dates) | set(mid_term_exam_dates)
        special_event_labels = {}
        if selected_semester.curriculum and selected_semester.curriculum.code != 'OLD':
            if selected_semester.cse_tech_carnival_date:
                all_dates.add(selected_semester.cse_tech_carnival_date)
                special_event_labels[selected_semester.cse_tech_carnival_date] = 'CSE Tech Carnival'
            if selected_semester.cultural_fest_date:
                all_dates.add(selected_semester.cultural_fest_date)
                special_event_labels[selected_semester.cultural_fest_date] = 'Cultural Fest'
        sorted_dates = sorted(all_dates)

        for row_idx, date in enumerate(sorted_dates, start=1):
            day = day_by_date.get(date, date.strftime('%A'))
            row = [date.strftime('%d/%m/%y'), day]
            slot_idx = 0
            
            # Check if this is a mid-term exam date - if so, display "Mid-Term Exam" across entire row
            if date in mid_term_exam_dates:
                # Create a single cell that spans all time slots
                mid_term_exam_content = Paragraph("Mid-Term Exam", ParagraphStyle(
                    'MidTermExam',
                    fontName='Helvetica-Bold',
                    fontSize=10,
                    alignment=TA_CENTER,
                    textColor=colors.white,
                    leading=12,
                    spaceBefore=0,
                    spaceAfter=0,
                ))
                row.append(mid_term_exam_content)
                # Add None for remaining columns (they will be merged)
                for _ in range(len(slot_ranges) - 1):
                    row.append(None)
                # Add span command to merge all time slot columns
                if len(slot_ranges) > 0:
                    span_commands.append(('SPAN', (2, row_idx), (1 + len(slot_ranges), row_idx)))
                table_data.append(row)
                continue  # Skip the rest of the loop for this date

            if date in special_event_labels:
                special_content = Paragraph(special_event_labels[date], ParagraphStyle(
                    'SpecialEvent',
                    fontName='Helvetica-Bold',
                    fontSize=10,
                    alignment=TA_CENTER,
                    textColor=colors.black,
                    leading=12,
                    spaceBefore=0,
                    spaceAfter=0,
                ))
                row.append(special_content)
                for _ in range(len(slot_ranges) - 1):
                    row.append(None)
                if len(slot_ranges) > 0:
                    span_commands.append(('SPAN', (2, row_idx), (1 + len(slot_ranges), row_idx)))
                table_data.append(row)
                continue
            # Build routines_for_row: all routines for this date, plus lunch break if present
            routines_for_row = []
            for r in routines:
                if r.class_date == date:
                    # Get teacher from SemesterCourse for the selected centre
                    teacher_name = 'N/A'
                    teacher_short_name = None
                    if r.course.code == 'CSE4246':
                        teacher_name = 'Supervisor'
                    else:
                        # Get SemesterCourse for this course, semester, and centre
                        semester_course = None
                        if centre:
                            semester_course = SemesterCourse.objects.filter(
                                semester=selected_semester,
                                course=r.course,
                                centre=centre
                            ).select_related('teacher').first()
                            # Skip this routine if it doesn't have a SemesterCourse for the selected centre
                            if not semester_course:
                                continue
                        else:
                            # Only use fallback if centre is not provided
                            semester_course = SemesterCourse.objects.filter(
                                semester=selected_semester,
                                course=r.course
                            ).select_related('teacher').first()
                        
                        if semester_course and semester_course.teacher:
                            teacher = semester_course.teacher
                            teacher_short_name = teacher.short_name
                            teacher_name = teacher.short_name if teacher.short_name else teacher.name
                    
                    routines_for_row.append({
                        'course_code': r.course.code,
                        'teacher': teacher_name,
                        'teacher_short_name': teacher_short_name,
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
                            if hide_teacher_name_in_pdf:
                                # Hide teacher name - only show course code
                                cell_content = Paragraph(course_code, ParagraphStyle(
                                    'CourseContent',
                                    fontName='Helvetica',
                                    fontSize=9,
                                    alignment=TA_CENTER,
                                    leading=10,
                                    spaceBefore=0,
                                    spaceAfter=0,
                                ))
                            elif teacher_short_name_newline:
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
                    # If this is a makeup date, show 'Review Class'
                    if date in makeup_dates:
                        cell_content = Paragraph("Review Class", ParagraphStyle(
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
            # Headers styling (no background fill)
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
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
            # Override with special colors for break, mid-term exam, and class cells
            for j, cell in enumerate(row[2:], 2):
                if isinstance(cell, Paragraph) and hasattr(cell, 'text'):
                    if "BREAK" in cell.text:
                        style.add('BACKGROUND', (j, i), (j, i), colors.lightgrey)
                    elif "Mid-Term Exam" in cell.text:
                        # Apply info/blue background for mid-term exam
                        style.add('BACKGROUND', (j, i), (j, i), colors.HexColor('#17a2b8'))  # Info blue color
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

        # Add the summary table of semester courses, filtered by centre if provided
        semester_courses = SemesterCourse.objects.filter(semester=selected_semester).select_related('course', 'teacher')
        
        # Filter by centre if provided
        if centre:
            semester_courses = semester_courses.filter(centre=centre)
        summary_data = [[
            'Course Code', 'Title', 'Number of Class', 'Course Teacher'
        ]]
        for sc in semester_courses:
            # Hide teacher name if option is enabled
            if hide_teacher_name_in_pdf:
                teacher_full_name = ""
            else:
                effective_teacher = sc.effective_teacher
                if effective_teacher:
                    teacher_full_name = effective_teacher.name + ' ('+effective_teacher.short_name+')' if effective_teacher.short_name else effective_teacher.name
                    if effective_teacher.name == "N/A":
                        teacher_full_name = ""
                else:
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
        response['Content-Disposition'] = f'attachment; filename="{_centre_filename_prefix(centre)}{selected_semester.name}_Routine.pdf"'
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
        # Get centre from request parameter
        centre_id = request.GET.get('centre')
        centre = None
        centre_name = ''
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
                centre_name = centre.name
            except Centre.DoesNotExist:
                pass
        buffer = io.BytesIO()
        
        # Use the same page size as the routine (landscape A4)
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=54,  # 0.75 inch - same as routine
            leftMargin=54,   # 0.75 inch - same as routine
            topMargin=34,    # 0.75 inch - same as routine
            # Leave room for per-page footer signatures + page number
            bottomMargin=70
        )
        page_width, page_height = landscape(A4)
        available_width = page_width - doc.leftMargin - doc.rightMargin
        elements = []

        # Calculate calendar width early for consistent alignment across all elements
        month_day_width = 0.12 * available_width  # Month/Day column
        day_width = 0.10 * available_width        # Each day column (only F,S)
        remarks_width = 0.38 * available_width    # Remarks column (increased from 0.30)
        exams_width = 0.28 * available_width      # Exams column (increased from 0.22)
        
        calendar_col_widths = [
            month_day_width,  # Month/Day
            day_width,        # F (Friday)
            day_width,        # S (Saturday)
            remarks_width,    # Remarks
            exams_width       # Exams
        ]
        
        # Calculate actual calendar width for consistent alignment
        calendar_width = sum(calendar_col_widths)

        # Define colors for different event types
        colors_dict = {
            'semester_begin': colors.HexColor('#90EE90'),  # Light Green
            'class_test': colors.HexColor('#00CED1'),  # Dark Turquoise
            'mid_term_exam': colors.HexColor('#17a2b8'),  # Info Blue (same as routine)
            'assignment': colors.HexColor('#FFA500'),  # Orange
            'semester_end': colors.HexColor('#FFB6C1'),  # Light Pink
            'final_exam': colors.HexColor('#D3D3D3'),  # Light Gray
            'holiday': colors.HexColor('#FF6B6B'),  # Red
            'makeup_class': colors.HexColor('#FFFF99'),  # Light Yellow
            'cse_tech_carnival': colors.HexColor('#D8BFD8'),  # Thistle
            'cultural_fest': colors.HexColor('#FFDAB9'),  # Peach
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
        # Fallback: if centre_name is not set, try to get it from SemesterCourse
        if not centre_name:
            first_sc = SemesterCourse.objects.filter(semester=selected_semester).select_related('centre').first()
            if first_sc and first_sc.centre:
                centre_name = first_sc.centre.name
                centre = first_sc.centre
        if commencement:
            left_content.append(Paragraph(f'<b>Date of Commencement:</b> {commencement}', header_style_normal))
        if centre_name:
            left_content.append(Paragraph(f'<b>Study Center:</b> {centre_name}', header_style_normal))

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
            colWidths=[190],
            hAlign='RIGHT',
            style=TableStyle([
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), -3),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ])
        )
        contact_info_lines = []
        # Get coordinator for this specific semester/centre combination
        coordinator = None
        if centre:
            semester_centre_coordinator = SemesterCentreCoordinator.objects.filter(
                semester=selected_semester,
                centre=centre
            ).select_related('program_coordinator', 'program_coordinator__teacher').first()
            if semester_centre_coordinator:
                coordinator = semester_centre_coordinator.program_coordinator
        
        # Fallback: try to get centre from centre_name if centre_id not available
        if not coordinator and centre_name:
            try:
                centre_obj = Centre.objects.get(name=centre_name)
                semester_centre_coordinator = SemesterCentreCoordinator.objects.filter(
                    semester=selected_semester,
                    centre=centre_obj
                ).select_related('program_coordinator', 'program_coordinator__teacher').first()
                if semester_centre_coordinator:
                    coordinator = semester_centre_coordinator.program_coordinator
            except Centre.DoesNotExist:
                pass
        
        if coordinator and coordinator.teacher:
            contact_info_lines.append(coordinator.teacher.name)
        if coordinator and coordinator.designation:
            contact_info_lines.append(coordinator.designation)
        if coordinator and coordinator.secondary_designation:
            contact_info_lines.append(coordinator.secondary_designation)
        contact_info_lines.append('Bangladesh Open University')
        if coordinator and coordinator.phone:
            contact_info_lines.append(f'Phone/Whatsapp: {coordinator.phone}')
        if coordinator and coordinator.email:
            contact_info_lines.append(f'email:{coordinator.email}')
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
            colWidths=[190],
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
            colWidths=[calendar_width-190],
            style=TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ])
        )
        two_col_table = Table(
            [[left_box_table, contact_table]],
            colWidths=[calendar_width-190, 190],
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
        # Changed to support multiple events per date (e.g., assignment and class test on same week)
        events_calendar = {}
        
        def get_friday_saturday_of_week(target_date):
            """Get Friday and Saturday dates for the week containing target_date"""
            # Find the Friday of the week containing target_date
            days_since_monday = target_date.weekday()
            friday_date = target_date + timedelta(days=(4 - days_since_monday))
            saturday_date = friday_date + timedelta(days=1)
            return friday_date, saturday_date
        
        def find_next_available_week(start_week, holiday_dates_set, semester_end, max_weeks_ahead=4):
            """Find the next available week where at least one of Friday or Saturday is not a holiday"""
            for week_offset in range(max_weeks_ahead + 1):
                check_week = start_week + timedelta(weeks=week_offset)
                if check_week > semester_end:
                    break
                friday, saturday = get_friday_saturday_of_week(check_week)
                # Check if at least one day is not a holiday
                if friday not in holiday_dates_set or saturday not in holiday_dates_set:
                    return check_week
            # If no available week found, return the original week
            return start_week
        
        def find_nth_valid_week(semester_start, semester_end, holiday_dates_set, n):
            """Find the Nth week counting only weeks where at least one day (Friday or Saturday) is not a holiday"""
            current_date = semester_start
            valid_week_count = 0
            
            while current_date <= semester_end and valid_week_count < n:
                friday, saturday = get_friday_saturday_of_week(current_date)
                # Count this week only if at least one day is not a holiday
                if friday not in holiday_dates_set or saturday not in holiday_dates_set:
                    valid_week_count += 1
                    if valid_week_count == n:
                        return current_date
                # Move to next week (Monday)
                current_date += timedelta(weeks=1)
            
            # If we couldn't find the Nth week, return the last valid week or semester_end
            return current_date if current_date <= semester_end else semester_end
        
        def add_event_to_calendar(date, event_type, description):
            """Add an event to the calendar, supporting multiple events per date"""
            if date not in events_calendar:
                events_calendar[date] = []
            # Check if this event type already exists for this date
            event_exists = any(et == event_type for et, _ in events_calendar[date])
            if not event_exists:
                events_calendar[date].append((event_type, description))
        
        try:
            if selected_semester.start_date and selected_semester.end_date:
                semester_start = selected_semester.start_date
                semester_end = selected_semester.end_date
                
                # Load holidays first to check against them
                holiday_dates_set = set()
                if selected_semester.holidays:
                    holiday_dates = [
                        datetime.strptime(date.strip(), "%Y-%m-%d").date()
                        for date in selected_semester.holidays.split(',')
                        if date.strip()
                    ]
                    holiday_dates_set = set(holiday_dates)
                    for holiday_date in holiday_dates:
                        if calendar_start <= holiday_date <= calendar_end:
                            add_event_to_calendar(holiday_date, 'holiday', 'Holiday')
                
                # Mark semester begin and end
                add_event_to_calendar(semester_start, 'semester_begin', 'First Day of Classes')
                add_event_to_calendar(semester_end, 'semester_end', 'Last Day of Classes')
                
                # Calculate key academic events based on weeks
                duration_days = (semester_end - semester_start).days
                
                # Check if this is new curriculum (not OLD)
                is_new_curriculum = selected_semester.curriculum and selected_semester.curriculum.code != 'OLD'
                
                if is_new_curriculum:
                    # For new curriculum: Add Mid-Term Exam dates instead of class tests
                    if selected_semester.mid_term_exam_dates:
                        mid_term_exam_dates = [
                            datetime.strptime(date.strip(), "%Y-%m-%d").date()
                            for date in selected_semester.mid_term_exam_dates.split(',')
                            if date.strip()
                        ]
                        for mid_term_date in mid_term_exam_dates:
                            if calendar_start <= mid_term_date <= calendar_end:
                                add_event_to_calendar(mid_term_date, 'mid_term_exam', 'Mid-Term Exam')
                else:
                    # For old curriculum: Add class tests using valid week counting (same as assignments)
                    # First Class Test (6th valid week) - mark both Friday and Saturday
                    first_test_week = find_nth_valid_week(semester_start, semester_end, holiday_dates_set, 6)
                    if first_test_week <= semester_end:
                        friday, saturday = get_friday_saturday_of_week(first_test_week)
                        # Set class test (even if date is a holiday, we'll show both markers in rendering)
                        add_event_to_calendar(friday, 'class_test', 'First Class Test')
                        add_event_to_calendar(saturday, 'class_test', 'First Class Test')
                    
                    # Second Class Test (10th valid week) - mark both Friday and Saturday
                    second_test_week = find_nth_valid_week(semester_start, semester_end, holiday_dates_set, 10)
                    if second_test_week <= semester_end:
                        friday, saturday = get_friday_saturday_of_week(second_test_week)
                        # Set class test (even if date is a holiday, we'll show both markers in rendering)
                        add_event_to_calendar(friday, 'class_test', 'Second Class Test')
                        add_event_to_calendar(saturday, 'class_test', 'Second Class Test')
                
                # Assignments: Use proper week counting (only count weeks with at least one non-holiday day)
                # For both new and old curriculum: 4th, 8th, 12th week
                # First Assignment (4th valid week) - mark both Friday and Saturday
                first_assignment_week = find_nth_valid_week(semester_start, semester_end, holiday_dates_set, 4)
                if first_assignment_week <= semester_end:
                    friday, saturday = get_friday_saturday_of_week(first_assignment_week)
                    # Set assignment (even if date is a holiday, we'll show both markers in rendering)
                    add_event_to_calendar(friday, 'assignment', 'First Assignment')
                    add_event_to_calendar(saturday, 'assignment', 'First Assignment')
                
                # Second Assignment (8th valid week) - mark both Friday and Saturday
                second_assignment_week = find_nth_valid_week(semester_start, semester_end, holiday_dates_set, 8)
                if second_assignment_week <= semester_end:
                    friday, saturday = get_friday_saturday_of_week(second_assignment_week)
                    # Set assignment (even if date is a holiday, we'll show both markers in rendering)
                    add_event_to_calendar(friday, 'assignment', 'Second Assignment')
                    add_event_to_calendar(saturday, 'assignment', 'Second Assignment')
                
                # Third Assignment (12th valid week) - mark both Friday and Saturday
                third_assignment_week = find_nth_valid_week(semester_start, semester_end, holiday_dates_set, 12)
                if third_assignment_week <= semester_end:
                    friday, saturday = get_friday_saturday_of_week(third_assignment_week)
                    # Set assignment (even if date is a holiday, we'll show both markers in rendering)
                    add_event_to_calendar(friday, 'assignment', 'Third Assignment')
                    add_event_to_calendar(saturday, 'assignment', 'Third Assignment')
                
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
                        add_event_to_calendar(makeup_date, 'makeup_class', 'Review Class')
                        if latest_makeup_date is None or makeup_date > latest_makeup_date:
                            latest_makeup_date = makeup_date

                # New curriculum: CSE Tech Carnival / Cultural Fest after makeup; push SEFE
                sefe_anchor_dates = []
                if latest_makeup_date:
                    sefe_anchor_dates.append(latest_makeup_date)
                if is_new_curriculum:
                    if selected_semester.cse_tech_carnival_date:
                        add_event_to_calendar(
                            selected_semester.cse_tech_carnival_date,
                            'cse_tech_carnival',
                            'CSE Tech Carnival',
                        )
                        sefe_anchor_dates.append(selected_semester.cse_tech_carnival_date)
                    if selected_semester.cultural_fest_date:
                        add_event_to_calendar(
                            selected_semester.cultural_fest_date,
                            'cultural_fest',
                            'Cultural Fest',
                        )
                        sefe_anchor_dates.append(selected_semester.cultural_fest_date)

                # Set Tentative Semester Final Exam date - mark 4 weeks starting from the first exam week
                if sefe_anchor_dates:
                    # 1 week after the latest of makeup / carnival / cultural fest
                    final_exam_week = max(sefe_anchor_dates) + timedelta(weeks=1)
                else:
                    # If no makeup/special events, final exam is 1 week after semester end
                    final_exam_week = semester_end + timedelta(weeks=1)
                
                # Calculate the end of the 4-week final exam period
                final_exam_end_week = final_exam_week + timedelta(weeks=3)  # 4 weeks total (0, 1, 2, 3)
                final_exam_end_saturday = get_friday_saturday_of_week(final_exam_end_week)[1]  # Get Saturday of the last week
                
                # Mark 4 weeks for final exam period (both Friday and Saturday for each week)
                for week_offset in range(4):
                    current_exam_week = final_exam_week + timedelta(weeks=week_offset)
                    friday, saturday = get_friday_saturday_of_week(current_exam_week)
                    add_event_to_calendar(friday, 'final_exam', 'Semester-end Final Examination (Tentative)')
                    add_event_to_calendar(saturday, 'final_exam', 'Semester-end Final Examination (Tentative)')
                
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
            final_exam_dates = []
            for date, events in events_calendar.items():
                # Ensure events is a list
                if not isinstance(events, list):
                    events = [events]
                # Check if any event is a final exam
                if any(et == 'final_exam' for et, _ in events):
                    final_exam_dates.append(date)
            if final_exam_dates:
                # Use the latest final exam date as our smart cutoff
                smart_calendar_end = max(final_exam_dates)
            else:
                # Fallback: extend calendar range to include all events (makeup dates, etc.)
                for event_date in events_calendar.keys():
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
                    header_row_1 = ['Month', 'Day & Date', '', 'Events', 'Exams']
                    header_row_2 = ['', 'Friday', 'Saturday', '', '']
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
                        # Check for holiday first - if it's a holiday, only show holiday marker
                        is_holiday = friday_date in holiday_dates_set
                        if is_holiday:
                            # If it's a holiday, only show holiday marker (no other events)
                            friday_str += ' (Holiday)'
                        elif friday_date in events_calendar:
                            # Handle multiple events per date (only if not a holiday)
                            events = events_calendar[friday_date]
                            # Ensure events is a list
                            if not isinstance(events, list):
                                events = [events]
                            # Show markers for all events (excluding holidays)
                            for event_type, description in events:
                                if event_type == 'semester_begin':
                                    friday_str += ' (FDC)'
                                elif event_type == 'semester_end':
                                    friday_str += ' (LDC)'
                                elif event_type == 'class_test':
                                    friday_str += ' (CT)'
                                elif event_type == 'mid_term_exam':
                                    friday_str += ' (MT)'
                                elif event_type == 'assignment':
                                    friday_str += ' (Assn.)'
                                elif event_type == 'final_exam':
                                    friday_str += ' (SEFE)'
                                elif event_type == 'makeup_class':
                                    friday_str += ' (RC)'
                                elif event_type == 'cse_tech_carnival':
                                    friday_str += ' (CTC)'
                                elif event_type == 'cultural_fest':
                                    friday_str += ' (CF)'
                                # Skip holiday type here since we already checked above
                    
                    if saturday_day:
                        saturday_str = str(saturday_day)
                        # Check for holiday first - if it's a holiday, only show holiday marker
                        is_holiday = saturday_date in holiday_dates_set
                        if is_holiday:
                            # If it's a holiday, only show holiday marker (no other events)
                            saturday_str += ' (Holiday)'
                        elif saturday_date in events_calendar:
                            # Handle multiple events per date (only if not a holiday)
                            events = events_calendar[saturday_date]
                            # Ensure events is a list
                            if not isinstance(events, list):
                                events = [events]
                            # Show markers for all events (excluding holidays)
                            for event_type, description in events:
                                if event_type == 'semester_begin':
                                    saturday_str += ' (FDC)'
                                elif event_type == 'semester_end':
                                    saturday_str += ' (LDC)'
                                elif event_type == 'class_test':
                                    saturday_str += ' (CT)'
                                elif event_type == 'mid_term_exam':
                                    saturday_str += ' (MT)'
                                elif event_type == 'assignment':
                                    saturday_str += ' (Assn.)'
                                elif event_type == 'final_exam':
                                    saturday_str += ' (SEFE)'
                                elif event_type == 'makeup_class':
                                    saturday_str += ' (RC)'
                                elif event_type == 'cse_tech_carnival':
                                    saturday_str += ' (CTC)'
                                elif event_type == 'cultural_fest':
                                    saturday_str += ' (CF)'
                                # Skip holiday type here since we already checked above
                    
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
                        if date_obj:
                            # Check if it's a holiday first
                            is_holiday = date_obj in holiday_dates_set
                            if is_holiday:
                                # If it's a holiday, only add holiday to remarks
                                remarks_set.add('Holiday')
                            elif date_obj in events_calendar:
                                # Only process non-holiday events
                                events = events_calendar[date_obj]
                                # Ensure events is a list
                                if not isinstance(events, list):
                                    events = [events]
                                # Process all events for this date (excluding holidays)
                                for event_type, description in events:
                                    if event_type == 'holiday':
                                        # Skip holidays here since we already handled them above
                                        continue
                                    elif event_type in ['class_test', 'mid_term_exam', 'final_exam']:
                                        # Add admit card note for final exam
                                        if event_type == 'final_exam':
                                            # Create styled text with bold and red color for "NO Admit, NO Exam"
                                            # Only make "Admit Card Required - NO Admit, NO Exam" bold, not the description
                                            description_with_note = f"{description}\n<b>Admit Card Required - <font color='red'>NO Admit, NO Exam</font></b>"
                                            exams_set.add(description_with_note)
                                        else:
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
                                'start_row': len(months_data),  # Current row index
                                'needs_spanning': False
                            }
                    
                    # Convert sets to comma-separated strings
                    remarks = ', '.join(sorted(remarks_set)) if remarks_set else ''
                    # For exams, check if any contain HTML formatting and create Paragraph objects
                    exams_list = sorted(exams_set) if exams_set else []
                    if exams_list:
                        # Check if any exam text contains HTML tags (from final exam with styled text)
                        has_html = any('<' in exam and '>' in exam for exam in exams_list)
                        if has_html:
                            # Create a Paragraph with HTML formatting
                            exams_text = ', '.join(exams_list)
                            styles = getSampleStyleSheet()
                            exams = Paragraph(exams_text, ParagraphStyle(
                                'ExamStyle',
                                parent=styles['Normal'],
                                fontSize=9,
                                leading=11,
                                alignment=TA_CENTER
                            ))
                        else:
                            # Plain text, join normally
                            exams = ', '.join(exams_list)
                    else:
                        exams = ''
                    
                    week_data.extend([remarks, exams])
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
            # If there's any error in calendar generation, log it and create a fallback
            import traceback
            print(f"Error in calendar generation: {e}")
            print(traceback.format_exc())
            months_data = []

        # Create the main calendar table - flatten the structure
        all_calendar_data = []
        for month_week_data in months_data:
            all_calendar_data.extend(month_week_data)

        # Use pre-calculated column widths for consistent alignment
        col_widths = calendar_col_widths
        
        # Track if we're using fallback data
        is_fallback = False
        # Ensure we have data to create the table
        if not all_calendar_data:
            # If no calendar data, create a simple message with proper column structure
            is_fallback = True
            all_calendar_data = [['Month', 'Day & Date', '', 'Events', 'Exams'],
                                ['', 'Friday', 'Saturday', '', ''],
                                ['No calendar data available for the selected semester date range.', '', '', '', '']]
            # Keep the same column widths for consistency
        
        calendar_table = Table(all_calendar_data, colWidths=col_widths)
        
        # Style the calendar table with event colors
        calendar_style = []
        
        # Only add styling if we have actual calendar data (not fallback)
        if all_calendar_data and not is_fallback:
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
                ('SPAN', (3, 0), (3, 1)),  # Remarks column spans both rows
                ('SPAN', (4, 0), (4, 1)),  # Exams column spans both rows
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
                if len(row_data) >= 5:  # Ensure we have all columns including exams (5 columns: Month, F, S, Events, Exams)
                    week_event_color = None
                    has_exam_event = False
                    
                    # Check if this row has exam events by looking at the exams column (index 4)
                    exams_column = row_data[4] if len(row_data) > 4 else ''
                    # Handle both string and Paragraph objects
                    if exams_column:
                        if isinstance(exams_column, str) and exams_column.strip():
                            has_exam_event = True
                        elif hasattr(exams_column, '__class__') and 'Paragraph' in str(type(exams_column)):
                            # It's a Paragraph object, which means there's exam content
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
                                        events = events_calendar[date_obj]
                                        # Ensure events is a list
                                        if not isinstance(events, list):
                                            events = [events]
                                        # Process all events for this date
                                        for event_type, _ in events:
                                            if event_type == 'holiday':
                                                # For holidays, apply red color only to the specific date cell
                                                calendar_style.append(
                                                    ('TEXTCOLOR', (day_col, row_idx), (day_col, row_idx), colors.HexColor('#FF0000'))
                                                )
                                            elif event_type in colors_dict:
                                                # For non-holiday events, store color for row highlighting
                                                # Priority: final_exam > class_test/mid_term_exam > assignment > other events
                                                if event_type == 'final_exam':
                                                    # Final exam has highest priority - always use final_exam color
                                                    non_holiday_event_color = colors_dict[event_type]
                                                    has_exam_event = True
                                                elif (event_type == 'class_test' or event_type == 'mid_term_exam') and non_holiday_event_color != colors_dict.get('final_exam'):
                                                    non_holiday_event_color = colors_dict[event_type]
                                                elif event_type == 'assignment' and non_holiday_event_color not in [colors_dict.get('class_test'), colors_dict.get('mid_term_exam'), colors_dict.get('final_exam')]:
                                                    non_holiday_event_color = colors_dict[event_type]
                                                elif non_holiday_event_color is None:
                                                    non_holiday_event_color = colors_dict[event_type]
                                except (ValueError, TypeError):
                                    continue
                    
                    # Apply background color for non-holiday events
                    if non_holiday_event_color:
                        if has_exam_event:
                            # For exam events: highlight entire row including Exams column (columns 1-4)
                            calendar_style.append(
                                ('BACKGROUND', (1, row_idx), (-1, row_idx), non_holiday_event_color)
                            )
                        else:
                            # For non-exam events: highlight only up to Remarks column (columns 1-3)
                            calendar_style.append(
                                ('BACKGROUND', (1, row_idx), (3, row_idx), non_holiday_event_color)
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
                    
                    # Span the remarks column (column 3) if both rows have the same remarks
                    start_row_data = all_calendar_data[start_row]
                    end_row_data = all_calendar_data[end_row]
                    if (len(start_row_data) > 3 and len(end_row_data) > 3 and 
                        start_row_data[3] == end_row_data[3]):
                        calendar_style.append(
                            ('SPAN', (3, start_row), (3, end_row))
                        )
                    
                    # Span the exams column (column 4) if both rows have the same exams
                    if (len(start_row_data) > 4 and len(end_row_data) > 4 and 
                        start_row_data[4] == end_row_data[4]):
                        calendar_style.append(
                            ('SPAN', (4, start_row), (4, end_row))
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
                            # For exam events: highlight entire row including Exams column (columns 1-4)
                            calendar_style.append(
                                ('BACKGROUND', (1, start_row), (-1, start_row), final_color)
                            )
                            calendar_style.append(
                                ('BACKGROUND', (1, end_row), (-1, end_row), final_color)
                            )
                        else:
                            # For non-exam events: highlight only up to Remarks column (columns 1-3)
                            calendar_style.append(
                                ('BACKGROUND', (1, start_row), (3, start_row), final_color)
                            )
                            calendar_style.append(
                                ('BACKGROUND', (1, end_row), (3, end_row), final_color)
                            )
            
            # Track and merge cells for 4-week final exam period in Exams column
            # Also ensure all columns in final exam rows have the same background color
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
                if len(row_data) >= 5:  # Ensure we have all columns including exams
                    exams_column = row_data[4] if len(row_data) > 4 else ''
                    if exams_column and 'Semester-end Final Examination (Tentative)' in str(exams_column):
                        final_exam_rows.append(row_idx)
                        # Apply final exam background color to ALL columns in this row (columns 1-4: Friday, Saturday, Events, Exams)
                        # This ensures all columns have the same grey color
                        calendar_style.append(
                            ('BACKGROUND', (1, row_idx), (-1, row_idx), colors_dict['final_exam'])
                        )
            
            # Apply cell spanning for final exam period in Exams column (column 4)
            if len(final_exam_rows) > 1:
                # Sort rows to ensure correct spanning
                final_exam_rows.sort()
                start_row = final_exam_rows[0]
                end_row = final_exam_rows[-1]
                calendar_style.append(
                    ('SPAN', (4, start_row), (4, end_row))  # Span column 4 (Exams) across all final exam rows
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
        
        # Check if this is new curriculum for legend
        is_new_curriculum_legend = selected_semester.curriculum and selected_semester.curriculum.code != 'OLD'
        # New curriculum has more legend items (CTC/CF) — use a smaller font so labels fit.
        # Old curriculum keeps the original size 9.
        legend_fs = 7.5 if is_new_curriculum_legend else 9

        def _legend_box(label, bg_color, font_size=legend_fs):
            return Table([[label]], style=TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), bg_color),
                ('FONTSIZE', (0, 0), (-1, -1), font_size),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOX', (0, 0), (-1, -1), 1, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 1 if is_new_curriculum_legend else 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 1 if is_new_curriculum_legend else 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))

        # Create single-row legend with all items
        legend_data = [[
            _legend_box('First Day of Classes (FDC)', colors_dict['semester_begin']),
        ]]

        # Add Class Test or Mid-Term Exam based on curriculum
        if is_new_curriculum_legend:
            legend_data[0].append(_legend_box('Mid-Term Exam (MT)', colors_dict['mid_term_exam']))
        else:
            legend_data[0].append(_legend_box('Class Test (CT)', colors_dict['class_test']))

        # Continue with the rest of the legend
        legend_data[0].extend([
            _legend_box('Assignment (Assn.)', colors_dict['assignment']),
            _legend_box('Last Day of Classes (LDC)', colors_dict['semester_end']),
            _legend_box('Semester-end Final Examination (SEFE)', colors_dict['final_exam']),
            _legend_box('Review Class (RC)', colors_dict['makeup_class']),
        ])

        if is_new_curriculum_legend:
            legend_data[0].extend([
                _legend_box('CSE Tech Carnival (CTC)', colors_dict['cse_tech_carnival']),
                _legend_box('Cultural Fest (CF)', colors_dict['cultural_fest']),
            ])
        
        # Calculate column widths to match calendar width
        # Widths: FDC, MT/CT, Assn., LDC, SEFE, RC [, CTC, CF for new]
        base_width = calendar_width / 10
        legend_col_widths = [
            base_width * 1.25,  # First Day of Classes (FDC)
            base_width * 1.0,  # Mid-Term Exam (MT) or Class Test (CT)
            base_width * 1.0,  # Assignment (Assn.)
            base_width * 1.2,  # Last Day of Classes (LDC)
            base_width * 1.8,  # Semester-end Final Examination (SEFE)
            base_width * 0.9,  # Review Class (RC)
        ]
        if is_new_curriculum_legend:
            legend_col_widths.extend([
                base_width * 1.1,  # CSE Tech Carnival (CTC)
                base_width * 0.9,  # Cultural Fest (CF)
            ])
        # Normalize to match calendar width
        total_width = sum(legend_col_widths)
        legend_col_widths = [w * calendar_width / total_width for w in legend_col_widths]
        
        legend_table = Table(legend_data, colWidths=legend_col_widths)
        legend_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),   # Reduced from 4 to 2
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),  # Reduced from 4 to 2
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
        response['Content-Disposition'] = f'attachment; filename="{_centre_filename_prefix(centre)}{selected_semester.name}_Academic_Calendar.pdf"'
        return response
    except Exception as e:
        return HttpResponse(f"Error generating Academic Calendar PDF: {str(e)}", status=500)

# Attendance Management Views

def check_teacher_permission(user, permission_codename):
    """Check if a user has a specific permission"""
    return user.has_perm(f'bou_routines_app.{permission_codename}')


def user_can_assign_course_teacher(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.is_staff and not get_teacher_from_user(user):
        return True
    return check_teacher_permission(user, 'can_assign_course_teacher')


def user_can_assign_examiners(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.is_staff and not get_teacher_from_user(user):
        return True
    return check_teacher_permission(user, 'can_assign_examiners')


def user_can_assign_chairman(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.is_staff and not get_teacher_from_user(user):
        return True
    return check_teacher_permission(user, 'can_assign_chairman')


def user_is_office_staff(user):
    """
    Office staff: assignment-only users (no teacher profile, not full admin).
    Identified by assign permissions without staff/superuser admin access.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    if get_teacher_from_user(user):
        return False
    if user.is_staff:
        return False
    return (
        check_teacher_permission(user, 'can_assign_course_teacher')
        or check_teacher_permission(user, 'can_assign_examiners')
        or check_teacher_permission(user, 'can_assign_chairman')
    )


def user_has_any_assign_permission(user):
    return (
        user_can_assign_course_teacher(user)
        or user_can_assign_examiners(user)
        or user_can_assign_chairman(user)
    )

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
    
    curricula = Curriculum.objects.filter(is_active=True).order_by('name')
    centres = Centre.objects.filter(is_active=True).order_by('name')

    # New curriculum only; do not keep ?curriculum= in the URL
    if request.method == 'GET' and 'curriculum' in request.GET:
        q = request.GET.copy()
        q.pop('curriculum', None)
        target = reverse('attendance-calendar')
        if q:
            target = f'{target}?{q.urlencode()}'
        return redirect(target)

    selected_curriculum_id = request.POST.get('curriculum') if request.method == 'POST' else None
    selected_curriculum = None
    if selected_curriculum_id:
        try:
            selected_curriculum_id = int(selected_curriculum_id)
            selected_curriculum = Curriculum.objects.get(id=selected_curriculum_id)
            if selected_curriculum.code == 'OLD':
                selected_curriculum = None
                selected_curriculum_id = None
        except (Curriculum.DoesNotExist, ValueError, TypeError):
            selected_curriculum = None
            selected_curriculum_id = None

    if not selected_curriculum and curricula.exists():
        selected_curriculum, selected_curriculum_id = _default_new_curriculum(curricula)

    # Get selected centre from request
    selected_centre_id = request.GET.get('centre') or request.POST.get('centre')
    selected_centre = None
    
    if selected_centre_id:
        try:
            selected_centre_id = int(selected_centre_id)
            selected_centre = Centre.objects.get(id=selected_centre_id)
        except (Centre.DoesNotExist, ValueError):
            selected_centre = None
            selected_centre_id = None
    
    # If no centre selected, default to teacher's centre (if teacher), otherwise DRC
    if not selected_centre:
        if teacher and teacher.centre:
            # Use teacher's associated centre
            selected_centre = teacher.centre
            selected_centre_id = selected_centre.id
        else:
            # Fallback to DRC for admin users or teachers without a centre
            try:
                selected_centre = Centre.objects.get(code='DRC')
                selected_centre_id = selected_centre.id
            except Centre.DoesNotExist:
                selected_centre = None
                selected_centre_id = None

    marks_default_semester_id = None
    if selected_curriculum:
        _y1_att = (
            Semester.objects.filter(curriculum=selected_curriculum, name='Y1S1')
            .order_by('order', 'id')
            .first()
        )
        if _y1_att:
            marks_default_semester_id = _y1_att.id
        if marks_default_semester_id is None:
            _first_any = (
                Semester.objects.filter(curriculum=selected_curriculum)
                .order_by('order', 'id')
                .first()
            )
            if _first_any:
                marks_default_semester_id = _first_any.id

    raw_semester_for_filter = request.GET.get('semester') or request.POST.get('semester')
    early_semester_id = None
    if raw_semester_for_filter:
        try:
            early_semester_id = int(raw_semester_for_filter)
        except (ValueError, TypeError):
            early_semester_id = None

    selected_term = (request.GET.get('term') or request.POST.get('term') or '').strip()
    selected_session = (request.GET.get('session') or request.POST.get('session') or '').strip()

    _term_session_source_id = early_semester_id
    if (
        _term_session_source_id is None
        and request.method == 'GET'
        and 'semester' not in request.GET
        and marks_default_semester_id
    ):
        _term_session_source_id = marks_default_semester_id

    if _term_session_source_id and selected_curriculum:
        try:
            _es = Semester.objects.get(id=_term_session_source_id, curriculum=selected_curriculum)
            if 'term' not in request.GET and 'term' not in request.POST:
                if 'semester' in request.GET or 'semester' in request.POST:
                    selected_term = (_es.term or '').strip()
                else:
                    selected_term = _pick_default_term_for_curriculum(
                        selected_curriculum
                    ) or (_es.term or '').strip()
        except Semester.DoesNotExist:
            pass

    if (
        selected_curriculum
        and not (selected_term or '').strip()
        and 'term' not in request.GET
        and 'term' not in request.POST
        and 'semester' not in request.GET
        and 'semester' not in request.POST
    ):
        picked = _pick_default_term_for_curriculum(selected_curriculum)
        if picked:
            selected_term = picked

    term_choices = []
    if selected_curriculum:
        _semester_base = Semester.objects.filter(curriculum=selected_curriculum)
        term_choices = sorted(
            {
                (t or '').strip()
                for t in _semester_base.exclude(term__isnull=True).exclude(term='').values_list('term', flat=True)
            },
            key=lambda x: (x.lower(), x),
        )
        semesters_qs = _semester_base.order_by('order', 'name')
        if selected_term:
            semesters_qs = semesters_qs.filter(term=selected_term)
        semester_list = list(semesters_qs)
        if (
            marks_default_semester_id
            and not any(s.id == marks_default_semester_id for s in semester_list)
        ):
            try:
                _orph_y1 = Semester.objects.get(
                    id=marks_default_semester_id, curriculum=selected_curriculum
                )
                semester_list.append(_orph_y1)
                semester_list.sort(key=lambda s: (s.order, s.name))
            except Semester.DoesNotExist:
                pass
        if early_semester_id:
            try:
                orphan = Semester.objects.get(id=early_semester_id, curriculum=selected_curriculum)
                if not any(s.id == orphan.id for s in semester_list):
                    semester_list.append(orphan)
                    semester_list.sort(key=lambda s: (s.order, s.name))
            except Semester.DoesNotExist:
                pass
        semesters = semester_list
    else:
        term_choices = []
        semesters = []

    default_semester_id_for_filter = marks_default_semester_id
    if selected_curriculum and semesters:
        if (
            request.method == 'GET'
            and 'semester' not in request.GET
            and selected_term
        ):
            sid = _first_semester_id_matching_term(semesters, selected_term)
            if sid is not None:
                default_semester_id_for_filter = sid

    # Get semester and course from request
    semester_id = request.GET.get('semester') or request.POST.get('semester')
    course_id = request.GET.get('course') or request.POST.get('course')
    selected_date = request.GET.get('date')

    if semester_id:
        try:
            semester_id = int(semester_id)
        except (ValueError, TypeError):
            semester_id = None
    else:
        semester_id = None

    if course_id:
        try:
            course_id = int(course_id)
        except (ValueError, TypeError):
            course_id = None

    if semester_id:
        try:
            _sem_chk_att = Semester.objects.select_related('curriculum').get(pk=semester_id)
            if _sem_chk_att.curriculum and _sem_chk_att.curriculum.code == 'OLD':
                semester_id = None
                course_id = None
                messages.warning(
                    request,
                    'Attendance uses new curriculum only; old-curriculum semesters are not available here.',
                )
        except Semester.DoesNotExist:
            pass

    if (
        semester_id is None
        and default_semester_id_for_filter is not None
        and request.method == 'GET'
        and 'semester' not in request.GET
    ):
        semester_id = default_semester_id_for_filter

    session_choices = _student_session_choices_for_semester(
        semester_id,
        selected_centre_id if selected_centre_id else None,
    )
    
    # Filter courses by semester and teacher
    courses_queryset = Course.objects.none()  # Default to empty queryset
    if semester_id:
        if teacher:
            # For teachers, show only their courses in the selected semester
            # Filter through SemesterCourse since Course doesn't have a direct teacher field
            semester_courses = SemesterCourse.objects.filter(
                semester_id=semester_id,
                teacher=teacher
            )
            if selected_centre_id:
                semester_courses = semester_courses.filter(centre_id=selected_centre_id)
            course_ids = semester_courses.values_list('course_id', flat=True).distinct()
            courses_queryset = Course.objects.filter(id__in=course_ids)
        else:
            # For admin users, show all courses in the selected semester
            courses_queryset = Course.objects.filter(
                semestercourse__semester_id=semester_id
            ).distinct()
            if selected_centre_id:
                courses_queryset = courses_queryset.filter(
                    semestercourse__centre_id=selected_centre_id
            ).distinct()
    
    # Initialize allowed_date_range in base context (will be updated when semester/course selected)
    allowed_date_range = None
    # Staff with a teacher profile are treated as teachers, not as administrators (align with ca_management)
    is_admin = request.user.is_superuser or (request.user.is_staff and not teacher)
    
    context = {
        'teacher': teacher,
        'is_admin': is_admin,
        'curricula': curricula,
        'selected_curriculum_id': selected_curriculum_id,
        'selected_curriculum': selected_curriculum,
        'centres': centres,
        'selected_centre': selected_centre,
        'selected_centre_id': selected_centre_id,
        'semesters': semesters,
        'term_choices': term_choices,
        'session_choices': session_choices,
        'selected_term': selected_term,
        'selected_session': selected_session,
        'allowed_date_range': allowed_date_range,  # Initialize in base context
        'courses': courses_queryset.order_by('code'),
        'selected_semester_id': semester_id,
        'selected_course_id': course_id,
        'selected_date': selected_date,
    }
    
    if semester_id and course_id:
        try:
            semester = Semester.objects.get(id=semester_id)
            # Verify course exists and is accessible to the teacher
            if teacher:
                # Verify through SemesterCourse that this teacher teaches this course in this semester
                semester_course = SemesterCourse.objects.filter(
                    semester_id=semester_id,
                    course_id=course_id,
                    teacher=teacher
                ).first()
                if not semester_course:
                    messages.error(request, "You don't have access to this course.")
                    return render(request, 'bou_routines_app/attendance_calendar.html', context)
                course = semester_course.course
            else:
                course = Course.objects.get(id=course_id)
            
            # Get students for this semester and selected centre with custom sorting
            # Sort by first two digits (descending), then last three digits (ascending)
            from django.db.models import Case, When, IntegerField
            from django.db.models.functions import Cast, Substr
            
            students = Student.objects.filter(semesters=semester)
            # Filter by selected centre if one is selected
            if selected_centre:
                students = students.filter(centre=selected_centre)
            if (selected_session or '').strip():
                students = students.filter(session=(selected_session or '').strip())
            
            students = students.extra(
                select={
                    'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                    'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
                }
            ).order_by('-first_two_digits', 'last_three_digits')
            
            # Get actual course schedule dates from NewRoutine table for this specific course
            from datetime import datetime, timedelta
            from bou_routines_app.models import NewRoutine
            
            # Get the course's scheduled days from NewRoutine table
            course_routines = NewRoutine.objects.filter(
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
            
            # Get actual routine dates from NewRoutine table (same logic as PDF export)
            routine_dates = set(NewRoutine.objects.filter(
                course=course,
                semester=semester
            ).values_list('class_date', flat=True).distinct())
            
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
            makeup_dates = []
            if semester.makeup_dates:
                for date_str in semester.makeup_dates.split(','):
                    if date_str.strip():
                        try:
                            makeup_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
                            makeup_dates.append(makeup_date)
                        except ValueError:
                            pass  # Skip invalid date formats
            
            # Determine which days to show based on course routine (for filtering makeup dates)
            days_to_show = []
            if 'Friday' in course_routines and 'Saturday' in course_routines:
                days_to_show = ['Friday', 'Saturday']
                print(f"DEBUG: Course has both Friday and Saturday classes - showing all dates")
            elif 'Friday' in course_routines:
                days_to_show = ['Friday']
                print(f"DEBUG: Course has only Friday classes - showing Friday dates only")
            elif 'Saturday' in course_routines:
                days_to_show = ['Saturday']
                print(f"DEBUG: Course has only Saturday classes - showing Saturday dates only")
            else:
                # Fallback: show Friday and Saturday if no specific schedule found
                days_to_show = ['Friday', 'Saturday']
                print(f"DEBUG: No specific schedule found - showing both Friday and Saturday dates")
            
            # Filter makeup dates based on course's scheduled day
            # If course is on Friday only, keep only Friday makeup dates
            # If course is on Saturday only, keep only Saturday makeup dates
            filtered_makeup_dates = []
            for makeup_date in makeup_dates:
                makeup_day = makeup_date.strftime('%A')
                # Only include makeup dates that match the course's scheduled day
                if makeup_day in days_to_show:
                    filtered_makeup_dates.append(makeup_date)
            
            # Attendance-only: allow per SemesterCourse override for mid-term exam dates exclusion.
            # If set, it replaces Semester.mid_term_exam_dates for the Attendance table only.
            def _parse_date_list_csv(value):
                dates = []
                if not value:
                    return dates
                for part in str(value).split(','):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        dates.append(datetime.strptime(part, "%Y-%m-%d").date())
                    except ValueError:
                        continue
                return dates

            semester_course_scope = None
            attendance_override_scope = None
            if selected_centre:
                # Course-specific SemesterCourse (still used for number_of_classes etc.)
                semester_course_scope = SemesterCourse.objects.filter(
                    semester=semester,
                    course=course,
                    centre=selected_centre,
                ).first()

                # Attendance override is applied per Semester + Centre (all courses) to avoid
                # per-course mismatches between Friday/Saturday offerings.
                attendance_override_scope = SemesterCourse.objects.filter(
                    semester=semester,
                    centre=selected_centre,
                    attendance_midterm_override_dates__isnull=False,
                ).first()

            mid_term_source = None
            if attendance_override_scope and attendance_override_scope.attendance_midterm_override_dates is not None:
                mid_term_source = attendance_override_scope.attendance_midterm_override_dates
            else:
                mid_term_source = semester.mid_term_exam_dates

            mid_term_exam_dates = set()
            if mid_term_source and semester.curriculum and semester.curriculum.code != 'OLD':
                mid_term_exam_dates = set(_parse_date_list_csv(mid_term_source))
            
            # Attendance table dates:
            # - Routine generator excludes semester mid-term dates from NewRoutine entries, but in reality
            #   classes may happen if mid-terms are shifted. For Attendance only, we therefore add the
            #   semester mid-term dates back as potential class dates, then exclude the *effective* mid-term
            #   dates (override if set; otherwise semester default).
            semester_mid_term_dates = set()
            if semester.mid_term_exam_dates and semester.curriculum and semester.curriculum.code != 'OLD':
                semester_mid_term_dates = set(_parse_date_list_csv(semester.mid_term_exam_dates))

            # Keep only dates that match the course's scheduled day(s) for consistency with attendance columns.
            semester_mid_term_dates = {
                d for d in semester_mid_term_dates if d.strftime('%A') in days_to_show
            }

            # Combine routine dates, filtered makeup dates, and semester mid-term dates
            all_dates = set(routine_dates) | set(filtered_makeup_dates) | set(semester_mid_term_dates)
            # Exclude effective mid-term exam dates for attendance
            all_dates = all_dates - mid_term_exam_dates
            semester_dates = sorted(all_dates)
            
            # Show all dates (including past dates) so teachers can view and manage attendance
            # for classes that have already occurred
            today = datetime.now().date()
            
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
                # Use filter().first() instead of get() since there may be multiple SemesterCourse
                # objects for the same semester/course but different centres
                semester_course = SemesterCourse.objects.filter(
                    semester=semester,
                    course=course
                ).first()
                if semester_course:
                    number_of_classes = semester_course.number_of_classes
                    print(f"DEBUG: Found SemesterCourse with number_of_classes: {number_of_classes}")
                else:
                    number_of_classes = len(semester_dates)  # Fallback to number of dates
                print(f"DEBUG: No SemesterCourse found, using fallback: {number_of_classes}")
            except Exception as e:
                number_of_classes = len(semester_dates)  # Fallback to number of dates
                print(f"DEBUG: Error getting SemesterCourse: {e}, using fallback: {number_of_classes}")
            
            for student in students:
                # Simple count of present days (for reference)
                attendance_days = sum(1 for date in semester_dates 
                                     if student.id in attendance_matrix and 
                                     date in attendance_matrix[student.id] and 
                                     attendance_matrix[student.id][date])
                
                # Calculate duration-based classes attended (same as CA calculation)
                if class_ratio != 1.0:
                    classes_attended = round(attendance_days * class_ratio, 1)
                else:
                    classes_attended = attendance_days
                # Cap display at max classes (makeup/review columns can exceed SemesterCourse total)
                display_classes_attended = min(classes_attended, number_of_classes)
                
                attendance_totals[student.id] = {
                    'attendance_days': attendance_days,
                    'classes_attended': display_classes_attended,
                    'number_of_classes': number_of_classes
                }
                
                print(f"DEBUG: Student {student.id} - Attendance days: {attendance_days}, Classes attended: {classes_attended} (display: {display_classes_attended}), Total classes: {number_of_classes}")
            
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

            # Allowed marking dates: full semester class schedule (same for teachers and admins).
            # Teacher-only "current week ± 1 week" restriction is disabled.
            allowed_start_date = None
            allowed_end_date = None
            from datetime import timedelta
            if semester_dates:
                allowed_date_range = (semester_dates[0], semester_dates[-1])
            else:
                allowed_date_range = (today - timedelta(days=3650), today + timedelta(days=3650))

            context.update({
                'semester': semester,
                'course': course,
                'students': students,
                'semester_dates': semester_dates,
                'semester_course_scope': semester_course_scope,
                'attendance_midterm_override_dates': (attendance_override_scope.attendance_midterm_override_dates if attendance_override_scope else None),
                'default_midterm_exam_dates': semester.mid_term_exam_dates,
                'attendance_midterm_override_is_set': bool(attendance_override_scope and attendance_override_scope.attendance_midterm_override_dates is not None),
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
                'allowed_start_date': allowed_start_date,
                'allowed_end_date': allowed_end_date,
                'allowed_date_range': allowed_date_range,
            })
            
            print("=" * 80)
            print("FINAL CONTEXT CHECK:")
            print(f"attendance_totals: {attendance_totals}")
            print(f"len(semester_dates): {len(semester_dates)}")
            print("=" * 80)
            
        except (Semester.DoesNotExist, Course.DoesNotExist):
            messages.error(request, "Invalid semester or course selected.")
    
    # Add selected_centre_id to context if not already present
    if 'selected_centre_id' not in context:
        context['selected_centre_id'] = selected_centre_id
    
    return render(request, 'bou_routines_app/attendance_calendar.html', context)


@login_required
@require_POST
def set_attendance_midterm_override_dates(request):
    """Admin-only: set attendance-only midterm exam dates override per SemesterCourse.
    Staff users with a teacher profile (same rule as ca_management is_admin) cannot set this.
    """
    t = get_teacher_from_user(request.user)
    is_admin = request.user.is_superuser or (request.user.is_staff and not t)
    if not is_admin:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    semester_id = request.POST.get('semester_id')
    course_id = request.POST.get('course_id')
    centre_id = request.POST.get('centre_id')
    override_csv = request.POST.get('attendance_midterm_override_dates', '')

    if not (semester_id and course_id and centre_id):
        return JsonResponse({'success': False, 'error': 'semester_id, course_id and centre_id are required'}, status=400)

    try:
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        centre = Centre.objects.get(id=centre_id)
    except (Semester.DoesNotExist, Course.DoesNotExist, Centre.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Invalid semester/course/centre'}, status=400)

    # Normalize: keep comma-separated YYYY-MM-DD, sorted, unique, allow clearing.
    from datetime import datetime
    cleaned_dates = []
    if override_csv is None:
        override_csv = ''
    for part in str(override_csv).split(','):
        part = part.strip()
        if not part:
            continue
        try:
            cleaned_dates.append(datetime.strptime(part, "%Y-%m-%d").date())
        except ValueError:
            continue

    cleaned_dates = sorted(set(cleaned_dates))
    normalized_csv = ",".join(d.strftime("%Y-%m-%d") for d in cleaned_dates)

    # Ensure there's at least one SemesterCourse row for this course scope (existing behavior),
    # but apply the override consistently to all courses in this semester+centre.
    semester_course, _ = SemesterCourse.objects.get_or_create(
        semester=semester,
        course=course,
        centre=centre,
        defaults={},
    )
    # Important:
    # - NULL means "not set" (use semester default)
    # - '' means "explicitly no midterm exclusions for attendance"
    SemesterCourse.objects.filter(
        semester=semester,
        centre=centre,
    ).update(attendance_midterm_override_dates=normalized_csv)

    return JsonResponse({'success': True, 'attendance_midterm_override_dates': normalized_csv})

@login_required
def get_student_sessions_for_semester(request):
    """Distinct Student.session values for students enrolled in the semester (optional centre)."""
    if not (
        request.user.is_superuser
        or request.user.is_staff
        or check_teacher_permission(request.user, 'can_mark_attendance')
        or check_teacher_permission(request.user, 'can_manage_ca')
    ):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    raw_sid = (request.GET.get('semester_id') or '').strip()
    if not raw_sid:
        return JsonResponse({'sessions': []})
    try:
        semester_pk = int(raw_sid)
    except (ValueError, TypeError):
        return JsonResponse({'sessions': []})
    if not Semester.objects.filter(pk=semester_pk).exists():
        return JsonResponse({'sessions': []})
    centre_raw = (request.GET.get('centre_id') or '').strip()
    centre_id = None
    if centre_raw:
        try:
            centre_id = int(centre_raw)
        except (ValueError, TypeError):
            centre_id = None
    sessions = _student_session_choices_for_semester(semester_pk, centre_id)
    return JsonResponse({'sessions': sessions})


@login_required
def get_semesters_for_curriculum(request):
    """AJAX endpoint to get semesters for a specific curriculum"""
    if not (
        request.user.is_superuser
        or request.user.is_staff
        or check_teacher_permission(request.user, 'can_mark_attendance')
        or check_teacher_permission(request.user, 'can_manage_ca')
    ):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    curriculum_id = request.GET.get('curriculum_id')
    centre_id = request.GET.get('centre_id')
    term = (request.GET.get('term') or '').strip()
    for_marks = (
        request.GET.get('for_marks') == '1'
        and (
            request.user.is_superuser
            or request.user.is_staff
            or check_teacher_permission(request.user, 'can_manage_ca')
        )
    )
    
    if not curriculum_id:
        return JsonResponse({'error': 'Curriculum ID required'}, status=400)
    
    try:
        curriculum = Curriculum.objects.get(id=curriculum_id)
        if for_marks and curriculum.code == 'OLD':
            return JsonResponse(
                {'error': 'Marks page uses new curriculum only.'},
                status=400,
            )
        semesters = Semester.objects.filter(curriculum=curriculum)
        
        # Note: Semesters are now shared across centres. Centre-specific filtering happens at SemesterCourse level.
        if term:
            semesters = semesters.filter(term=term)
        
        semesters = semesters.order_by('order', 'name')
        
        semesters_data = []
        for semester in semesters:
            semesters_data.append({
                'id': semester.id,
                'name': semester.name,
                'semester_full_name': semester.semester_full_name,
                'term': semester.term or '',
                'session': semester.session or '',
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
    centre_id = request.GET.get('centre_id')
    for_marks = (
        request.GET.get('for_marks') == '1'
        and (
            request.user.is_superuser
            or request.user.is_staff
            or check_teacher_permission(request.user, 'can_manage_ca')
        )
    )
    if not semester_id:
        return JsonResponse({'error': 'Semester ID required'}, status=400)
    
    if for_marks:
        try:
            _sem = Semester.objects.select_related('curriculum').get(pk=int(semester_id))
            if _sem.curriculum and _sem.curriculum.code == 'OLD':
                return JsonResponse({'courses': []})
        except (Semester.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'courses': []})
    
    # Get teacher from logged-in user (optional for admin users)
    teacher = get_teacher_from_user(request.user)
    
    # Filter courses by semester, teacher, and centre
    semester_courses = SemesterCourse.objects.filter(semester_id=semester_id)
    
    # Filter by centre if provided
    if centre_id:
        try:
            centre = Centre.objects.get(id=centre_id)
            semester_courses = semester_courses.filter(centre=centre)
        except Centre.DoesNotExist:
            pass
    
    # Filter by teacher if provided
    if teacher:
        if for_marks:
            # Marks: teacher/examiner at any centre of this semester (then centre filter above)
            semester_courses = semester_courses.filter(
                course_id__in=_teacher_marks_accessible_course_ids(teacher, semester_id)
            )
        else:
            semester_courses = semester_courses.filter(teacher=teacher)
    
    # Get unique courses from semester courses
    course_ids = semester_courses.values_list('course_id', flat=True).distinct()
    courses = Course.objects.filter(id__in=course_ids).order_by('code')
    
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
        
        # Verify course access through SemesterCourse
        teacher_user = get_teacher_from_user(request.user)
        if teacher_user:
            # Verify through SemesterCourse that this teacher teaches this course
            semester_course = SemesterCourse.objects.filter(
                semester_id=semester_id,
                course_id=course_id,
                teacher=teacher_user
            ).first()
            if not semester_course:
                return JsonResponse({'error': 'You don\'t have access to this course.'}, status=403)
            course = semester_course.course
        else:
            course = Course.objects.get(id=course_id)
        
        # Validate date format (teacher ±1 week window disabled — same as admins)
        from datetime import datetime as dt_module
        try:
            dt_module.strptime(attendance_date, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({'error': 'Invalid date format'}, status=400)
        
        # Create or update attendance record
        # Use teacher_user if available, otherwise use teacher (for admin fallback)
        marking_teacher = teacher_user if teacher_user else teacher
        attendance, created = Attendance.objects.update_or_create(
            student=student,
            course=course,
            semester=semester,
            attendance_date=attendance_date,
            defaults={
                'is_present': is_present,
                'marked_by': marking_teacher,
                'marked_at': timezone.now()
            }
        )
        
        # Update CA mark to recalculate attendance mark
        try:
            ca_mark = CAMark.objects.filter(
                student=student,
                course=course,
                semester=semester
            ).first()
            if ca_mark:
                # Save will trigger auto-calculation of attendance_mark
                ca_mark.save()
        except Exception as e:
            # Log error but don't fail the attendance marking
            print(f"Error updating CA mark after attendance change: {e}")
        
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
        # Verify course access through SemesterCourse
        teacher_user = get_teacher_from_user(request.user)
        selected_centre = None
        if teacher_user:
            semester_course = SemesterCourse.objects.filter(
                semester_id=semester_id,
                course_id=course_id,
                teacher=teacher_user
            ).first()
            if not semester_course:
                return JsonResponse({'success': False, 'message': 'You don\'t have access to this course.'})
            course = semester_course.course
            selected_centre = semester_course.centre
        else:
            course = Course.objects.get(id=course_id)
            # For admin users, get centre from request or from semester_course
            centre_id = request.POST.get('centre_id') or request.GET.get('centre')
            if centre_id:
                try:
                    selected_centre = Centre.objects.get(id=centre_id)
                except Centre.DoesNotExist:
                    pass
            # If no centre from request, try to get from semester_course
            if not selected_centre:
                semester_course = SemesterCourse.objects.filter(
                    semester_id=semester_id,
                    course_id=course_id
                ).first()
                if semester_course:
                    selected_centre = semester_course.centre
        
        # Validate date format only (teacher ±1 week restriction disabled)
        from datetime import datetime as dt_module
        try:
            dt_module.strptime(attendance_date, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({'success': False, 'message': 'Invalid date format'})
        
        # Get all students for this semester and selected centre with custom sorting
        # Sort by first two digits (descending), then last three digits (ascending)
        students = Student.objects.filter(semesters=semester)
        # Filter by selected centre if one is selected
        if selected_centre:
            students = students.filter(centre=selected_centre)
        
        students = students.extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        
        attendance_count = 0
        students_to_update_ca = set()  # Track students whose CA marks need updating
        
        for student in students:
            is_present = request.POST.get(f'student_{student.id}') == 'on'
            
            # Create or update attendance record
            # Use teacher_user if available, otherwise use teacher (for admin fallback)
            marking_teacher = teacher_user if teacher_user else teacher
            attendance, created = Attendance.objects.update_or_create(
                student=student,
                course=course,
                semester=semester,
                attendance_date=attendance_date,
                defaults={
                    'is_present': is_present,
                    'marked_by': marking_teacher,
                }
            )
            attendance_count += 1
            students_to_update_ca.add(student)
        
        # Update CA marks for all affected students to recalculate attendance marks
        for student in students_to_update_ca:
            try:
                ca_mark = CAMark.objects.filter(
                    student=student,
                    course=course,
                    semester=semester
                ).first()
                if ca_mark:
                    # Save will trigger auto-calculation of attendance_mark
                    ca_mark.save()
            except Exception as e:
                # Log error but don't fail the attendance marking
                print(f"Error updating CA mark for student {student.id} after attendance change: {e}")
        
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
        # Verify course access through SemesterCourse
        selected_centre = None
        if teacher:
            semester_course = SemesterCourse.objects.filter(
                semester_id=semester_id,
                course_id=course_id,
                teacher=teacher
            ).first()
            if not semester_course:
                messages.error(request, "You don't have access to this course.")
                return redirect('attendance-calendar')
            course = semester_course.course
            selected_centre = semester_course.centre
        else:
            course = Course.objects.get(id=course_id)
            # For admin users, get centre from request
            centre_id = request.GET.get('centre')
            if centre_id:
                try:
                    selected_centre = Centre.objects.get(id=centre_id)
                except Centre.DoesNotExist:
                    pass
            # If no centre from request, try to get from semester_course
            if not selected_centre:
                semester_course = SemesterCourse.objects.filter(
                    semester_id=semester_id,
                    course_id=course_id
                ).first()
                if semester_course:
                    selected_centre = semester_course.centre
        
        # Get all students and their attendance records with custom sorting
        # Sort by first two digits (descending), then last three digits (ascending)
        students = Student.objects.filter(semesters=semester)
        # Filter by selected centre if one is selected
        if selected_centre:
            students = students.filter(centre=selected_centre)
        
        students = students.extra(
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

@login_required
def export_attendance_pdf(request):
    """Export attendance report to PDF"""
    try:
        # Check permissions
        if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_mark_attendance')):
            messages.error(request, "You don't have permission to export attendance reports.")
            return redirect('attendance-calendar')
        
        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        centre_id = request.GET.get('centre')
        
        if not semester_id or not course_id:
            messages.error(request, "Please select a semester and course.")
            return redirect('attendance-calendar')
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        
        # Get selected centre
        selected_centre = None
        teacher = get_teacher_from_user(request.user)
        # Only non-teacher staff/superuser may use hide_faculty on PDF (teachers may not hide names on export)
        can_apply_hide_faculty = request.user.is_superuser or (request.user.is_staff and not teacher)
        if teacher:
            # For teachers, get centre from semester_course
            semester_course = SemesterCourse.objects.filter(
                semester_id=semester_id,
                course_id=course_id,
                teacher=teacher
            ).first()
            if semester_course:
                selected_centre = semester_course.centre
        else:
            # For admin users, get centre from request or from semester_course
            if centre_id:
                try:
                    selected_centre = Centre.objects.get(id=centre_id)
                except Centre.DoesNotExist:
                    pass
            # If no centre from request, try to get from semester_course
            if not selected_centre:
                semester_course = SemesterCourse.objects.filter(
                    semester_id=semester_id,
                    course_id=course_id
                ).first()
                if semester_course:
                    selected_centre = semester_course.centre
        
        # Get all students and their attendance records with custom sorting
        students = Student.objects.filter(semesters=semester)
        # Filter by selected centre if one is selected
        if selected_centre:
            students = students.filter(centre=selected_centre)
        
        students = students.extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')

        attendance_dates = _attendance_calendar_class_dates(semester, course, selected_centre)
        if not attendance_dates:
            attendance_dates = list(
                Attendance.objects.filter(course=course, semester=semester)
                .values_list('attendance_date', flat=True)
                .distinct()
                .order_by('attendance_date')
            )

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
        
        # Margins (used for layout before SimpleDocTemplate exists; footer matches these)
        _att_pdf_lm = 54
        _att_pdf_rm = 54
        _att_pdf_tm = 34
        _att_pdf_bm = 70

        # Get page width and calculate available width
        page_width, page_height = landscape(A4)
        available_width = page_width - _att_pdf_lm - _att_pdf_rm

        elements = []
        
        # --- HEADER IMAGE SECTION ---
        header_img_path = 'bou_routines_app/static/pdf_routine_top.png'
        try:
            padding_for_image = 2
            img_obj = Image(header_img_path, width=available_width - (2 * padding_for_image), height=45)
            header_img_table = Table([[img_obj]], colWidths=[available_width])
            header_img_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1, -1), padding_for_image),
                ('RIGHTPADDING', (0,0), (-1, -1), padding_for_image),
                ('TOPPADDING', (0,0), (-1, -1), 0),
                ('BOTTOMPADDING', (0,0), (-1, -1), 0),
            ]))
            elements.append(header_img_table)
        except Exception as e:
            print(f"Error loading header image: {e}")
            pass
        elements.append(Spacer(1, -4))
        
        # Initialize centre_name
        centre_name = ''
        centre_id = request.GET.get('centre')
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
                centre_name = centre.name
            except Centre.DoesNotExist:
                pass
        if not centre_name:
            first_sc = SemesterCourse.objects.filter(semester=semester).select_related('centre').first()
            if first_sc and first_sc.centre:
                centre_name = first_sc.centre.name
        
        # Build left column (program/session/term/commencement/study center)
        header_style = ParagraphStyle(
            'HeaderStyle',
            fontName='Helvetica-Bold',
            fontSize=15,
            alignment=1,
            leading=18,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_small = ParagraphStyle(
            'HeaderStyleSmall',
            fontName='Helvetica-Bold',
            fontSize=11,
            alignment=1,
            leading=14,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_normal = ParagraphStyle(
            'HeaderStyleNormal',
            fontName='Helvetica',
            fontSize=10,
            alignment=1,
            leading=11,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_bold = ParagraphStyle(
            'HeaderStyleBold',
            fontName='Helvetica-Bold',
            fontSize=12,
            alignment=1,
            leading=15,
            spaceAfter=0,
            spaceBefore=0,
        )
        
        left_content = []
        program_name = 'B. Sc in Computer Science and Engineering Program'
        left_content.append(Paragraph(program_name, header_style))
        session = semester.session or ''
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            combined = f'{term} Term {semester_full_name}'.strip()
            if session:
                combined = f'{combined} ({session} Session)'
            left_content.append(Paragraph(combined, header_style_small))
        left_content.append(Spacer(1, 2))
        course_name_display = f"{course.code} - {course.name}" if course else "Course"
        left_content.append(Paragraph('Attendance Report', header_style_bold))
        left_content.append(Paragraph(f'Course Code & Title: {course_name_display}', header_style_small))
        # Get teacher name from SemesterCourse
        teacher_name = None
        # Try to get centre_id from request first
        centre_id = request.GET.get('centre')
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
                semester_course = SemesterCourse.objects.filter(
                    semester=semester,
                    course=course,
                    centre=centre
                ).select_related('teacher').first()
                if semester_course and semester_course.teacher:
                    teacher_name = semester_course.teacher.name
            except Centre.DoesNotExist:
                pass
        # Fallback: Get centre from students if not already set
        if not teacher_name and not centre_name and students.exists():
            first_student = students.first()
            if first_student.centre:
                centre = first_student.centre
                semester_course = SemesterCourse.objects.filter(
                    semester=semester,
                    course=course,
                    centre=centre
                ).select_related('teacher').first()
                if semester_course and semester_course.teacher:
                    teacher_name = semester_course.teacher.name
        # Check if hide_faculty parameter is set (ignored unless caller may apply it)
        hide_faculty = (request.GET.get('hide_faculty') == '1') and can_apply_hide_faculty
        
        # Only show teacher if found and hide_faculty is not set
        if teacher_name and not hide_faculty:
            left_content.append(Paragraph(f'<b>Faculty:</b> {teacher_name}', header_style_normal))
        if centre_name:
            left_content.append(Paragraph(f'<b>Study Center:</b> {centre_name}', header_style_normal))
        
        # Header block (no Contact Person box)
        left_box_table = Table(
            [[left_content]],
            colWidths=[available_width],
            hAlign='CENTER',
            style=TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ])
        )
        elements.append(Spacer(1, 4))
        elements.append(left_box_table)
        elements.append(Spacer(1, 4))
        
        # Build table data
        table_data = []
        
        # Header row - make date columns vertical to save space
        # Format: Day of week (abbrev), Day number, Month (abbrev) - e.g., "Sat\n14\nFeb"
        styles = getSampleStyleSheet()
        vertical_header_style = ParagraphStyle(
            'VerticalHeader',
            parent=styles['Normal'],
            fontSize=6,  # Small font
            textColor=colors.black,
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
            leading=6,
            spaceBefore=0,
            spaceAfter=0,
            wordWrap='CJK',  # Prevent word wrapping that might cause horizontal rendering
        )
        
        def make_date_header(date):
            """Create vertical date header: Day of week, Day, Month"""
            day_abbrev = date.strftime('%a')  # Mon, Tue, Wed, etc.
            day_num = date.strftime('%d')      # 01, 02, etc.
            month_abbrev = date.strftime('%b') # Jan, Feb, Mar, etc.
            # Use explicit line breaks and ensure consistent formatting
            date_text = f"{day_abbrev}<br/>{day_num}<br/>{month_abbrev}"
            para = Paragraph(date_text, vertical_header_style)
            return para
        
        # Create styles for student ID and name (bold)
        student_id_style = ParagraphStyle(
            'StudentIDStyle',
            parent=styles['Normal'],
            fontSize=9,  # Increased font size for Student ID
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
            leading=9,  # Tight leading to minimize gaps
            spaceBefore=0,  # No space before
            spaceAfter=0,  # No space after
        )
        student_name_style = ParagraphStyle(
            'StudentNameStyle',
            parent=styles['Normal'],
            fontSize=7,
            fontName='Helvetica-Bold',
            alignment=0,  # Left align
            leading=7,  # Tight leading to minimize gaps
            spaceBefore=0,  # No space before
            spaceAfter=0,  # No space after
        )
        
        header = ['Student ID', 'Name']
        # Add date columns with vertical format (Day, Date, Month)
        for date in attendance_dates:
            header.append(make_date_header(date))
        # Add Present and % columns (horizontal) - removed Absent
        header.extend(['Total\nPresent', '%'])
        table_data.append(header)
        
        # Data rows
        for student in students:
            # Use plain strings - bold styling will be applied via table style
            # This eliminates paragraph spacing that causes gaps
            row = [student.id, student.name.upper()]
            for date in attendance_dates:
                if date in attendance_matrix[student.id]['attendance']:
                    status = 'P' if attendance_matrix[student.id]['attendance'][date] else 'A'
                else:
                    status = 'A'
                row.append(status)
            row.append(str(attendance_matrix[student.id]['present_count']))
            # Removed absent_count
            row.append(f"{attendance_matrix[student.id]['percentage']:.1f}%")
            table_data.append(row)
        
        # Calculate column widths dynamically for landscape orientation
        # Landscape A4: ~792pt width, minus margins (40pt total) = ~752pt available
        # Student ID: 70, Name: 120, each date: 25, Present/%: 40 each (reduced)
        # Adjust date column width based on available space
        # Minimum width of 25pt for compact layout (using <br/> ensures vertical rendering works)
        # Use the same available_width as header and footer for consistency
        # Column widths: Student ID (70), Name (153), date columns (variable), Present (32), % (32)
        fixed_cols_width = 70 + 153 + 32 + 32  # Student ID + Name + Present + % (removed Absent)
        num_date_cols = len(attendance_dates)
        date_col_width = max(22, (available_width - fixed_cols_width) / num_date_cols) if num_date_cols > 0 else 25
        
        col_widths = [70, 153] + [date_col_width] * len(attendance_dates) + [32, 32]
        
        # Ensure total width equals available_width exactly
        total_width = sum(col_widths)
        if total_width != available_width:
            # Adjust date columns proportionally to match available_width
            adjustment = available_width - total_width
            if num_date_cols > 0:
                per_date_adjustment = adjustment / num_date_cols
                col_widths = [70, 128] + [date_col_width + per_date_adjustment] * len(attendance_dates) + [32, 32]
        
        # Create table with adjusted column widths
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            # Header row: no background fill
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),  # Slightly larger header font for landscape
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            # Increase row height for header to accommodate vertical date text
            ('ROWHEIGHT', (0, 0), (-1, 0), 40),  # Reduced height for header row
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTSIZE', (0, 1), (0, -1), 9),  # Larger font for Student ID column (bold)
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),  # Bold for Student ID
            ('FONTSIZE', (1, 1), (1, -1), 7),  # Font for Name column (bold)
            ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),  # Bold for Name
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),  # Left align Name column
            ('VALIGN', (1, 1), (1, -1), 'MIDDLE'),  # Explicitly set vertical center for Name column
            ('FONTSIZE', (2, 1), (-1, -1), 7),  # Regular font size for other columns
            ('FONTNAME', (2, 1), (-1, -1), 'Helvetica-Bold'),  # Bold for all other columns (attendance marks, Present, %)
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            # Reduce padding for Student ID and Name columns to make them compact
            ('TOPPADDING', (0, 1), (0, -1), 0),  # No top padding for Student ID
            ('BOTTOMPADDING', (0, 1), (0, -1), 0),  # No bottom padding for Student ID
            ('TOPPADDING', (1, 1), (1, -1), 0),  # No top padding for Name
            ('BOTTOMPADDING', (1, 1), (1, -1), -2),  # More negative bottom padding to compensate for extra space
            # Keep padding for other columns - reduced to fit signature
            ('TOPPADDING', (2, 1), (-1, -1), 2),
            ('BOTTOMPADDING', (2, 1), (-1, -1), 2),
            # Set compact row height for data rows - reduced to fit signature
            ('ROWHEIGHT', (0, 1), (-1, -1), 8.5),  # Reduced row height
        ]))
        
        elements.append(table)

        hide_faculty_pdf = (request.GET.get('hide_faculty') == '1') and can_apply_hide_faculty
        teacher_name_for_signature = teacher_name if teacher_name else 'Teacher Name'

        def _draw_attendance_pdf_footer(cnv, page_num, total_pages):
            pw, _ph = landscape(A4)
            footer_left_x = _att_pdf_lm
            footer_right_x = pw - _att_pdf_rm
            footer_line_y = 48
            footer_text_y = 34
            cnv.saveState()
            cnv.setLineWidth(1)
            cnv.setStrokeColor(colors.black)
            cnv.line(footer_left_x, footer_line_y, footer_left_x + 200, footer_line_y)
            cnv.setFont('Helvetica', 10)
            faculty_text = 'Faculty:' if hide_faculty_pdf else f'Faculty: {teacher_name_for_signature}'
            cnv.drawString(footer_left_x, footer_text_y, faculty_text)
            cnv.setFont('Helvetica', 9)
            cnv.drawRightString(
                footer_right_x, footer_text_y, _pdf_page_number_label(page_num, total_pages)
            )
            cnv.restoreState()

        _AttFooterCanvas = _make_deferred_footer_canvas_class(_draw_attendance_pdf_footer)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=_att_pdf_rm,
            leftMargin=_att_pdf_lm,
            topMargin=_att_pdf_tm,
            bottomMargin=_att_pdf_bm,
        )
        doc.build(elements, canvasmaker=_AttFooterCanvas)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        filename = f"Attendance_{course.code}_{semester.name}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        return HttpResponse(f"Error generating PDF: {str(e)}", status=500)

@login_required
def export_blank_attendance_pdf(request):
    """Export blank attendance sheet to PDF (only Student ID and Name filled, all other columns blank)"""
    try:
        # Check permissions - only admin/superuser can download blank sheets
        if not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, "You don't have permission to export blank attendance sheets.")
            return redirect('attendance-calendar')
        
        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        centre_id = request.GET.get('centre')
        
        if not semester_id or not course_id:
            messages.error(request, "Please select a semester and course.")
            return redirect('attendance-calendar')
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        
        teacher = get_teacher_from_user(request.user)
        can_apply_hide_faculty = request.user.is_superuser or (request.user.is_staff and not teacher)
        
        # Get selected centre
        selected_centre = None
        if centre_id:
            try:
                selected_centre = Centre.objects.get(id=centre_id)
            except Centre.DoesNotExist:
                pass
        # If no centre from request, try to get from semester_course
        if not selected_centre:
            semester_course = SemesterCourse.objects.filter(
                semester_id=semester_id,
                course_id=course_id
            ).first()
            if semester_course:
                selected_centre = semester_course.centre
        
        # Get all students with custom sorting
        students = Student.objects.filter(semesters=semester)
        # Filter by selected centre if one is selected
        if selected_centre:
            students = students.filter(centre=selected_centre)
        
        students = students.extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')

        attendance_dates = _attendance_calendar_class_dates(semester, course, selected_centre)
        if not attendance_dates:
            attendance_dates = list(
                Attendance.objects.filter(course=course, semester=semester)
                .values_list('attendance_date', flat=True)
                .distinct()
                .order_by('attendance_date')
            )

        # Get centre name for header
        centre_name = None
        if students.exists():
            first_student = students.first()
            if first_student.centre:
                centre_name = first_student.centre.name
        
        _blank_att_lm = 54
        _blank_att_rm = 54
        _blank_att_tm = 34
        _blank_att_bm = 70

        # Get page width and calculate available width
        page_width, page_height = landscape(A4)
        available_width = page_width - _blank_att_lm - _blank_att_rm

        elements = []
        
        # --- HEADER IMAGE SECTION ---
        header_img_path = 'bou_routines_app/static/pdf_routine_top.png'
        try:
            padding_for_image = 2
            img_obj = Image(header_img_path, width=available_width - (2 * padding_for_image), height=45)
            header_img_table = Table([[img_obj]], colWidths=[available_width])
            header_img_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1, -1), padding_for_image),
                ('RIGHTPADDING', (0,0), (-1, -1), padding_for_image),
                ('TOPPADDING', (0,0), (-1, -1), 0),
                ('BOTTOMPADDING', (0,0), (-1, -1), 0),
            ]))
            elements.append(header_img_table)
        except Exception as e:
            print(f"Error loading header image: {e}")
            pass
        elements.append(Spacer(1, -4))
        
        # Initialize centre_name if not set
        if not centre_name:
            first_sc = SemesterCourse.objects.filter(semester=semester).select_related('centre').first()
            if first_sc and first_sc.centre:
                centre_name = first_sc.centre.name
        
        # Build left column (program/session/term/commencement/study center)
        header_style = ParagraphStyle(
            'HeaderStyle',
            fontName='Helvetica-Bold',
            fontSize=15,
            alignment=1,
            leading=18,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_small = ParagraphStyle(
            'HeaderStyleSmall',
            fontName='Helvetica-Bold',
            fontSize=11,
            alignment=1,
            leading=14,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_normal = ParagraphStyle(
            'HeaderStyleNormal',
            fontName='Helvetica',
            fontSize=10,
            alignment=1,
            leading=11,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_bold = ParagraphStyle(
            'HeaderStyleBold',
            fontName='Helvetica-Bold',
            fontSize=12,
            alignment=1,
            leading=15,
            spaceAfter=0,
            spaceBefore=0,
        )
        
        left_content = []
        program_name = 'B. Sc in Computer Science and Engineering Program'
        left_content.append(Paragraph(program_name, header_style))
        session = semester.session or ''
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            combined = f'{term} Term {semester_full_name}'.strip()
            if session:
                combined = f'{combined} ({session} Session)'
            left_content.append(Paragraph(combined, header_style_small))
        left_content.append(Spacer(1, 2))
        course_name_display = f"{course.code} - {course.name}" if course else "Course"
        left_content.append(Paragraph('Attendance Sheet', header_style_bold))
        left_content.append(Paragraph(f'Course Code & Title: {course_name_display}', header_style_small))
        # Get teacher name from SemesterCourse
        teacher_name = None
        # Try to get centre_id from request first
        centre_id = request.GET.get('centre')
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
                semester_course = SemesterCourse.objects.filter(
                    semester=semester,
                    course=course,
                    centre=centre
                ).select_related('teacher').first()
                if semester_course and semester_course.teacher:
                    teacher_name = semester_course.teacher.name
            except Centre.DoesNotExist:
                pass
        # Fallback: Get centre from students if not already set
        if not teacher_name and not centre_name and students.exists():
            first_student = students.first()
            if first_student.centre:
                centre = first_student.centre
                semester_course = SemesterCourse.objects.filter(
                    semester=semester,
                    course=course,
                    centre=centre
                ).select_related('teacher').first()
                if semester_course and semester_course.teacher:
                    teacher_name = semester_course.teacher.name
        # Check if hide_faculty parameter is set (ignored unless caller may apply it)
        hide_faculty = (request.GET.get('hide_faculty') == '1') and can_apply_hide_faculty
        
        # Only show teacher if found and hide_faculty is not set
        if teacher_name and not hide_faculty:
            left_content.append(Paragraph(f'<b>Faculty:</b> {teacher_name}', header_style_normal))
        if centre_name:
            left_content.append(Paragraph(f'<b>Study Center:</b> {centre_name}', header_style_normal))
        
        # Header block (no Contact Person box)
        left_box_table = Table(
            [[left_content]],
            colWidths=[available_width],
            hAlign='CENTER',
            style=TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ])
        )
        elements.append(Spacer(1, 4))
        elements.append(left_box_table)
        elements.append(Spacer(1, 4))
        
        # Build table data
        table_data = []
        
        # Header row - make date columns vertical to save space
        styles = getSampleStyleSheet()
        vertical_header_style = ParagraphStyle(
            'VerticalHeader',
            parent=styles['Normal'],
            fontSize=6,
            textColor=colors.black,
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
            leading=6,
            spaceBefore=0,
            spaceAfter=0,
            wordWrap='CJK',
        )
        
        def make_date_header(date):
            """Create vertical date header: Day of week, Day, Month"""
            day_abbrev = date.strftime('%a')
            day_num = date.strftime('%d')
            month_abbrev = date.strftime('%b')
            date_text = f"{day_abbrev}<br/>{day_num}<br/>{month_abbrev}"
            para = Paragraph(date_text, vertical_header_style)
            return para
        
        # Create styles for student ID and name (bold)
        student_id_style = ParagraphStyle(
            'StudentIDStyle',
            parent=styles['Normal'],
            fontSize=9,  # Increased font size for Student ID
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
            leading=9,  # Tight leading to minimize gaps
            spaceBefore=0,  # No space before
            spaceAfter=0,  # No space after
        )
        student_name_style = ParagraphStyle(
            'StudentNameStyle',
            parent=styles['Normal'],
            fontSize=7,
            fontName='Helvetica-Bold',
            alignment=0,  # Left align
            leading=7,  # Tight leading to minimize gaps
            spaceBefore=0,  # No space before
            spaceAfter=0,  # No space after
        )
        
        header = ['Student ID', 'Name']
        # Add date columns with vertical format
        for date in attendance_dates:
            header.append(make_date_header(date))
        # Add Present and % columns (horizontal) - removed Absent
        header.extend(['Total\nPresent', '%'])
        table_data.append(header)
        
        # Data rows - only Student ID and Name filled, all other cells blank
        for student in students:
            # Use plain strings - bold styling will be applied via table style
            # This eliminates paragraph spacing that causes gaps
            row = [student.id, student.name.upper()]
            # Add blank cells for all dates
            for date in attendance_dates:
                row.append('')  # Blank cell
            # Add blank cells for Present and % (removed Absent)
            row.extend(['', ''])
            table_data.append(row)
        
        # Calculate column widths dynamically for landscape orientation
        # Use the same available_width as header and footer for consistency
        # Column widths: Student ID (70), Name (153), date columns (variable), Present (32), % (32)
        fixed_cols_width = 70 + 153 + 32 + 32  # Student ID + Name + Present + % (removed Absent)
        num_date_cols = len(attendance_dates)
        date_col_width = max(22, (available_width - fixed_cols_width) / num_date_cols) if num_date_cols > 0 else 25
        
        col_widths = [70, 153] + [date_col_width] * len(attendance_dates) + [32, 32]
        
        # Ensure total width equals available_width exactly
        total_width = sum(col_widths)
        if total_width != available_width:
            # Adjust date columns proportionally to match available_width
            adjustment = available_width - total_width
            if num_date_cols > 0:
                per_date_adjustment = adjustment / num_date_cols
                col_widths = [70, 128] + [date_col_width + per_date_adjustment] * len(attendance_dates) + [32, 32]
        
        # Create table with adjusted column widths
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            # Header row: no background fill
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('ROWHEIGHT', (0, 0), (-1, 0), 40),  # Reduced height for header row
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTSIZE', (0, 1), (0, -1), 9),  # Larger font for Student ID column (bold)
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),  # Bold for Student ID
            ('FONTSIZE', (1, 1), (1, -1), 7),  # Font for Name column (bold)
            ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),  # Bold for Name
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),  # Left align Name column
            ('VALIGN', (1, 1), (1, -1), 'MIDDLE'),  # Explicitly set vertical center for Name column
            ('FONTSIZE', (2, 1), (-1, -1), 7),  # Regular font size for other columns
            ('FONTNAME', (2, 1), (-1, -1), 'Helvetica-Bold'),  # Bold for all other columns (attendance marks, Present, %)
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            # Reduce padding for Student ID and Name columns to make them compact
            ('TOPPADDING', (0, 1), (0, -1), 0),  # No top padding for Student ID
            ('BOTTOMPADDING', (0, 1), (0, -1), 0),  # No bottom padding for Student ID
            ('TOPPADDING', (1, 1), (1, -1), 0),  # No top padding for Name
            ('BOTTOMPADDING', (1, 1), (1, -1), -2),  # More negative bottom padding to compensate for extra space
            # Keep padding for other columns - reduced to fit signature
            ('TOPPADDING', (2, 1), (-1, -1), 2),
            ('BOTTOMPADDING', (2, 1), (-1, -1), 2),
            # Set compact row height for data rows - reduced to fit signature
            ('ROWHEIGHT', (0, 1), (-1, -1), 8.5),  # Reduced row height
        ]))
        
        elements.append(table)

        hide_faculty_pdf = (request.GET.get('hide_faculty') == '1') and can_apply_hide_faculty
        teacher_name_for_signature = teacher_name if teacher_name else 'Teacher Name'

        def _draw_blank_attendance_pdf_footer(cnv, page_num, total_pages):
            pw, _ph = landscape(A4)
            footer_left_x = _blank_att_lm
            footer_right_x = pw - _blank_att_rm
            footer_line_y = 48
            footer_text_y = 34
            cnv.saveState()
            cnv.setLineWidth(1)
            cnv.setStrokeColor(colors.black)
            cnv.line(footer_left_x, footer_line_y, footer_left_x + 200, footer_line_y)
            cnv.setFont('Helvetica', 10)
            faculty_text = 'Faculty:' if hide_faculty_pdf else f'Faculty: {teacher_name_for_signature}'
            cnv.drawString(footer_left_x, footer_text_y, faculty_text)
            cnv.setFont('Helvetica', 9)
            cnv.drawRightString(
                footer_right_x, footer_text_y, _pdf_page_number_label(page_num, total_pages)
            )
            cnv.restoreState()

        _BlankAttFooterCanvas = _make_deferred_footer_canvas_class(_draw_blank_attendance_pdf_footer)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=_blank_att_rm,
            leftMargin=_blank_att_lm,
            topMargin=_blank_att_tm,
            bottomMargin=_blank_att_bm,
        )
        doc.build(elements, canvasmaker=_BlankAttFooterCanvas)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        filename = f"Blank_Attendance_{course.code}_{semester.name}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        return HttpResponse(f"Error generating PDF: {str(e)}", status=500)

@login_required
def export_attendance_excel(request):
    """Export attendance report to Excel"""
    try:
        # Check permissions
        if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_mark_attendance')):
            messages.error(request, "You don't have permission to export attendance reports.")
            return redirect('attendance-calendar')
        
        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        centre_id = request.GET.get('centre')
        
        if not semester_id or not course_id:
            messages.error(request, "Please select a semester and course.")
            return redirect('attendance-calendar')
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)

        selected_centre = None
        teacher = get_teacher_from_user(request.user)
        if teacher:
            semester_course = SemesterCourse.objects.filter(
                semester_id=semester_id,
                course_id=course_id,
                teacher=teacher,
            ).first()
            if semester_course:
                selected_centre = semester_course.centre
        else:
            if centre_id:
                try:
                    selected_centre = Centre.objects.get(id=centre_id)
                except Centre.DoesNotExist:
                    pass
            if not selected_centre:
                semester_course = SemesterCourse.objects.filter(
                    semester_id=semester_id,
                    course_id=course_id,
                ).first()
                if semester_course:
                    selected_centre = semester_course.centre
        
        # Get students for the selected centre (same as PDF export)
        students = Student.objects.filter(semesters=semester)
        if selected_centre:
            students = students.filter(centre=selected_centre)

        students = students.extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        
        attendance_dates = _attendance_calendar_class_dates(semester, course, selected_centre)
        if not attendance_dates:
            attendance_dates = list(
                Attendance.objects.filter(course=course, semester=semester)
                .values_list('attendance_date', flat=True)
                .distinct()
                .order_by('attendance_date')
            )
        
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
        
        # Calculate statistics (present count only for displayed date columns, same as PDF table)
        total_classes = len(attendance_dates)
        for student_id in attendance_matrix:
            present_count = sum(
                1 for date in attendance_dates
                if attendance_matrix[student_id]['attendance'].get(date)
            )
            attendance_matrix[student_id]['present_count'] = present_count
            attendance_matrix[student_id]['percentage'] = (
                (present_count / total_classes * 100) if total_classes > 0 else 0
            )

        teacher_name, centre_name = _ca_marks_export_teacher_and_centre(
            semester,
            course,
            selected_centre.id if selected_centre else centre_id,
        )

        num_cols = 2 + len(attendance_dates) + 2  # ID, Name, dates, Total Present, %

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Attendance')

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 15,
            'align': 'center',
            'valign': 'vcenter',
        })
        subtitle_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'align': 'center',
            'valign': 'vcenter',
        })
        normal_format = workbook.add_format({
            'font_size': 10,
            'align': 'center',
            'valign': 'vcenter',
        })
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 8,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'text_wrap': True,
        })
        cell_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 8,
            'bold': True,
        })
        cell_stripe_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 8,
            'bold': True,
            'bg_color': '#D3D3D3',
        })
        id_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 9,
            'bold': True,
        })
        id_stripe_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 9,
            'bold': True,
            'bg_color': '#D3D3D3',
        })
        name_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 7,
            'bold': True,
        })
        name_stripe_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 7,
            'bold': True,
            'bg_color': '#D3D3D3',
        })

        row = 0
        last_col = max(num_cols - 1, 0)
        worksheet.merge_range(
            row, 0, row, last_col,
            'B. Sc in Computer Science and Engineering Program',
            title_format,
        )
        row += 1
        session = semester.session or ''
        if session:
            worksheet.merge_range(row, 0, row, last_col, f'{session} Session', subtitle_format)
            row += 1
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            worksheet.merge_range(
                row, 0, row, last_col,
                f'{term} Term {semester_full_name}'.strip(),
                subtitle_format,
            )
            row += 1
        worksheet.merge_range(row, 0, row, last_col, 'Attendance Report', subtitle_format)
        row += 1
        course_name_display = f'{course.code} - {course.name}'
        worksheet.merge_range(
            row, 0, row, last_col,
            f'Course Code & Title: {course_name_display}',
            normal_format,
        )
        row += 1
        if teacher_name:
            worksheet.merge_range(
                row, 0, row, last_col, f'Faculty: {teacher_name}', normal_format,
            )
            row += 1
        if centre_name:
            worksheet.merge_range(
                row, 0, row, last_col, f'Study Center: {centre_name}', normal_format,
            )
            row += 1

        header_row = row
        col = 0
        worksheet.write(header_row, col, 'Student ID', header_format)
        col += 1
        worksheet.write(header_row, col, 'Name', header_format)
        col += 1
        for date in attendance_dates:
            date_header = f"{date.strftime('%a')}\n{date.strftime('%d')}\n{date.strftime('%b')}"
            worksheet.write(header_row, col, date_header, header_format)
            col += 1
        worksheet.write(header_row, col, 'Total\nPresent', header_format)
        col += 1
        worksheet.write(header_row, col, '%', header_format)
        row += 1

        for student in students:
            stripe = (row - header_row) % 2 == 0
            col = 0
            worksheet.write(row, col, student.id, id_stripe_format if stripe else id_format)
            col += 1
            worksheet.write(
                row, col, student.name.upper(), name_stripe_format if stripe else name_format,
            )
            col += 1
            for date in attendance_dates:
                if date in attendance_matrix[student.id]['attendance']:
                    status = 'P' if attendance_matrix[student.id]['attendance'][date] else 'A'
                else:
                    status = 'A'
                worksheet.write(row, col, status, cell_stripe_format if stripe else cell_format)
                col += 1
            worksheet.write(
                row, col,
                attendance_matrix[student.id]['present_count'],
                cell_stripe_format if stripe else cell_format,
            )
            col += 1
            worksheet.write(
                row, col,
                f"{attendance_matrix[student.id]['percentage']:.1f}%",
                cell_stripe_format if stripe else cell_format,
            )
            row += 1

        worksheet.set_column(0, 0, 12)
        worksheet.set_column(1, 1, 22)
        if len(attendance_dates) > 0:
            worksheet.set_column(2, 1 + len(attendance_dates), 5)
        worksheet.set_column(num_cols - 2, num_cols - 1, 8)
        worksheet.set_row(header_row, 36)

        _excel_apply_landscape_a4_print_setup(worksheet, row - 1, last_col)

        workbook.close()
        output.seek(0)
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"Attendance_{course.code}_{semester.name}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        return HttpResponse(f"Error generating Excel: {str(e)}", status=500)

@login_required
def export_ca_marks_pdf(request):
    """Export CA marks to PDF"""
    try:
        import math
        # Check permissions
        if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_manage_ca')):
            messages.error(request, "You don't have permission to export CA marks.")
            return redirect('ca-management')
        
        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        centre_id = request.GET.get('centre')
        
        if not semester_id or not course_id:
            messages.error(request, "Please select a semester and course.")
            return redirect('ca-management')
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        if not _user_can_edit_ca_and_midterm(request, semester, course, centre_id):
            messages.error(request, "Only the course teacher can export CA marks for this course.")
            return redirect('ca-management')
        
        # Get students with custom sorting
        students = Student.objects.filter(semesters=semester).extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        students = filter_students_queryset_by_centre(students, centre_id)
        
        # Get existing CA marks
        existing_marks = CAMark.objects.filter(
            student__in=students,
            course=course,
            semester=semester
        )
        
        ca_marks = {}
        for mark in existing_marks:
            mark.attendance_mark = mark.calculate_attendance_mark()
            ca_marks[mark.student.id] = mark
        
        # Create temporary marks for students without existing marks
        for student in students:
            if student.id not in ca_marks:
                temp_mark = CAMark(
                    student=student,
                    course=course,
                    semester=semester
                )
                temp_mark.attendance_mark = temp_mark.calculate_attendance_mark()
                ca_marks[student.id] = temp_mark
        
        _ca_lm = 54
        _ca_rm = 54
        _ca_tm = 34
        _ca_bm = 70

        # Get page width and calculate available width
        page_width, page_height = landscape(A4)
        available_width = page_width - _ca_lm - _ca_rm

        elements = []
        
        # --- HEADER IMAGE SECTION ---
        header_img_path = 'bou_routines_app/static/pdf_routine_top.png'
        try:
            padding_for_image = 2
            img_obj = Image(header_img_path, width=available_width - (2 * padding_for_image), height=45)
            header_img_table = Table([[img_obj]], colWidths=[available_width])
            header_img_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1, -1), padding_for_image),
                ('RIGHTPADDING', (0,0), (-1, -1), padding_for_image),
                ('TOPPADDING', (0,0), (-1, -1), 0),
                ('BOTTOMPADDING', (0,0), (-1, -1), 0),
            ]))
            elements.append(header_img_table)
        except Exception as e:
            print(f"Error loading header image: {e}")
            pass
        elements.append(Spacer(1, -4))
        
        # Initialize centre_name if not already set
        centre_name = ''
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
                centre_name = centre.name
            except Centre.DoesNotExist:
                pass
        
        # Build left column (program/session/term/commencement/study center)
        header_style = ParagraphStyle(
            'HeaderStyle',
            fontName='Helvetica-Bold',
            fontSize=15,
            alignment=1,  # Center
            leading=18,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_small = ParagraphStyle(
            'HeaderStyleSmall',
            fontName='Helvetica-Bold',
            fontSize=11,
            alignment=1,
            leading=14,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_normal = ParagraphStyle(
            'HeaderStyleNormal',
            fontName='Helvetica',
            fontSize=10,
            alignment=1,
            leading=11,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_bold = ParagraphStyle(
            'HeaderStyleBold',
            fontName='Helvetica-Bold',
            fontSize=12,
            alignment=1,
            leading=15,
            spaceAfter=0,
            spaceBefore=0,
        )
        
        left_content = []
        program_name = 'B. Sc in Computer Science and Engineering Program'
        left_content.append(Paragraph(program_name, header_style))
        session = semester.session or ''
        if session:
            left_content.append(Paragraph(f'{session} Session', header_style_small))
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            combined = f'{term} Term {semester_full_name}'.strip()
            left_content.append(Paragraph(combined, header_style_small))
        left_content.append(Spacer(1, 2))
        left_content.append(Paragraph('Continuous Assessment (CA) Marks', header_style_bold))
        # Get teacher name from SemesterCourse
        teacher_name = None
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
                semester_course = SemesterCourse.objects.filter(
                    semester=semester,
                    course=course,
                    centre=centre
                ).select_related('teacher').first()
                if semester_course and semester_course.teacher:
                    teacher_name = semester_course.teacher.name
            except Centre.DoesNotExist:
                pass
        # Only show teacher if found
        if teacher_name:
            left_content.append(Paragraph(f'<b>Faculty:</b> {teacher_name}', header_style_normal))
        if not centre_name:
            first_sc = SemesterCourse.objects.filter(semester=semester).select_related('centre').first()
            if first_sc and first_sc.centre:
                centre_name = first_sc.centre.name
        if centre_name:
            left_content.append(Paragraph(f'<b>Study Center:</b> {centre_name}', header_style_normal))
        
        # Header block (no Contact Person box)
        left_box_table = Table(
            [[left_content]],
            colWidths=[available_width],
            hAlign='CENTER',
            style=TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ])
        )
        elements.append(Spacer(1, 4))
        elements.append(left_box_table)
        elements.append(Spacer(1, 4))
        
        # Build table data with multi-row headers matching the marks page
        table_data = []
        
        # Get effective weights for display
        if course.course_type == 'PROJECT':
            # Project course headers (2 rows)
            total_ca = course.effective_project_supervisor_weight + course.effective_project_evaluation_weight + course.effective_project_presentation_weight
            header_row_1 = [
                'SL. No', 'Student ID', 'Name',
                f'Project Work CA (Total: {total_ca})', '', '',
                'Total'
            ]
            header_row_2 = [
                '', '', '',
                f'Supervisor\n({course.effective_project_supervisor_weight})',
                f'Evaluation\n({course.effective_project_evaluation_weight})',
                f'Presentation\n({course.effective_project_presentation_weight})',
                ''
            ]
            table_data.append(header_row_1)
            table_data.append(header_row_2)
        elif course.is_lab:
            # Lab course headers (3 rows)
            total_ca = course.effective_lab_ca_total_marks
            p2w = course.effective_lab_ca_practical2_weight
            if p2w:
                header_row_1 = [
                    'SL. No', 'Student ID', 'Name',
                    f'Lab Course CA (Total: {total_ca})', '', '', '', '', '', '',
                    'Total'
                ]
                header_row_2 = [
                    '', '', '',
                    f'Attendance\n({course.effective_lab_ca_attendance_weight})',
                    f'Assignment/Lab Report\n({course.effective_lab_ca_assignment_weight})', '', '', '',
                    f'Experiment/\nLab Project\n({course.effective_lab_ca_practical_weight})',
                    f'Experiment/\nLab Project\n({p2w})',
                    ''
                ]
                header_row_3 = [
                    '', '', '', '',
                    'First', 'Second', 'Third', 'Average', '', '', ''
                ]
            else:
                total_ca = (
                    course.effective_lab_ca_attendance_weight
                    + course.effective_lab_ca_assignment_weight
                    + course.effective_lab_ca_practical_weight
                )
                header_row_1 = [
                    'SL. No', 'Student ID', 'Name',
                    f'Lab Course CA (Total: {total_ca})', '', '', '', '',
                    '', 'Total'
                ]
                header_row_2 = [
                    '', '', '',
                    f'Attendance\n({course.effective_lab_ca_attendance_weight})',
                    f'Assignment/Lab Report\n({course.effective_lab_ca_assignment_weight})', '', '', '',
                    f'Experiment/\nLab Project\n({course.effective_lab_ca_practical_weight})',
                    ''
                ]
                header_row_3 = [
                    '', '', '',
                    '',
                    'First', 'Second', 'Third', 'Average',
                    '', ''
                ]
            table_data.append(header_row_1)
            table_data.append(header_row_2)
            table_data.append(header_row_3)
        else:
            # Theory course headers (3 rows)
            # Check curriculum to determine if we use class tests (old) or mid-term (new)
            is_old_curriculum = semester.curriculum and semester.curriculum.code == 'OLD'
            if is_old_curriculum:
                # Old curriculum: use class tests
                exam_weight = course.effective_ca_quiz_weight
                total_ca = course.effective_ca_attendance_weight + course.effective_ca_assignment_weight + exam_weight
                header_row_1 = [
                    'SL. No', 'Student ID', 'Name',
                    f'Theory Course CA (Total: {total_ca})', '', '', '', '', '', '',
                    '', 'Total'
                ]
                header_row_2 = [
                    '', '', '',
                    f'Attendance\n({course.effective_ca_attendance_weight})',
                    f'Assignment/Presentation\n({course.effective_ca_assignment_weight})', '', '', '',
                    f'Class Test\n({exam_weight})', '', '',
                    'Total'
                ]
                header_row_3 = [
                    '', '', '',
                    '',
                    'First', 'Second', 'Third', 'Average',
                    'First', 'Second', 'Best',
                    'Total'
                ]
            else:
                # New curriculum: use mid-term
                exam_weight = course.effective_ca_midterm_weight
                total_ca = course.effective_ca_attendance_weight + course.effective_ca_assignment_weight + exam_weight
                header_row_1 = [
                    'SL. No', 'Student ID', 'Name',
                    f'Theory Course CA (Total: {total_ca})', '', '', '', '',
                    '', 'Total'
                ]
                header_row_2 = [
                    '', '', '',
                    f'Attendance\n({course.effective_ca_attendance_weight})',
                    f'Assignment/Presentation\n({course.effective_ca_assignment_weight})', '', '', '',
                    f'Mid-Term\nExam\n({exam_weight})',
                    'Total'
                ]
                header_row_3 = [
                    '', '', '',
                    '',
                    'First', 'Second', 'Third', 'Average',
                    '', 'Total'
                ]
            table_data.append(header_row_1)
            table_data.append(header_row_2)
            table_data.append(header_row_3)
        
        # Data rows
        for sl_no, student in enumerate(students, start=1):
            mark = ca_marks.get(student.id)
            if mark:
                if course.course_type == 'PROJECT':
                    row = [
                        str(sl_no),
                        student.id,
                        student.name.upper(),
                        _fmt_export_mark(mark.project_supervisor_mark),
                        _fmt_export_mark(mark.project_evaluation_mark),
                        _fmt_export_mark(mark.project_presentation_mark),
                        str(int(math.ceil(float(mark.calculate_total_ca_mark() or 0))))
                    ]
                elif course.is_lab:
                    if course.effective_lab_ca_practical2_weight:
                        row = [
                            str(sl_no),
                            student.id,
                            student.name.upper(),
                            _fmt_export_mark(mark.attendance_mark),
                            _fmt_export_mark(mark.first_lab_assignment_mark),
                            _fmt_export_mark(mark.second_lab_assignment_mark),
                            _fmt_export_mark(mark.third_lab_assignment_mark),
                            _fmt_export_mark(mark.lab_assignment_mark),
                            _fmt_export_mark(mark.lab_practical_mark),
                            _fmt_export_mark(mark.second_lab_practical_mark),
                            str(int(math.ceil(float(mark.calculate_total_ca_mark() or 0))))
                        ]
                    else:
                        row = [
                            str(sl_no),
                            student.id,
                            student.name.upper(),
                            _fmt_export_mark(mark.attendance_mark),
                            _fmt_export_mark(mark.first_lab_assignment_mark),
                            _fmt_export_mark(mark.second_lab_assignment_mark),
                            _fmt_export_mark(mark.third_lab_assignment_mark),
                            _fmt_export_mark(mark.lab_assignment_mark),
                            _fmt_export_mark(mark.lab_practical_mark),
                            str(int(math.ceil(float(mark.calculate_total_ca_mark() or 0))))
                        ]
                else:
                    # Theory course - check curriculum
                    is_old_curriculum = semester.curriculum and semester.curriculum.code == 'OLD'
                    if is_old_curriculum:
                        # Old curriculum: use class tests
                        row = [
                            str(sl_no),
                            student.id,
                            student.name.upper(),
                            _fmt_export_mark(mark.attendance_mark),
                            _fmt_export_mark(mark.first_assignment_mark),
                            _fmt_export_mark(mark.second_assignment_mark),
                            _fmt_export_mark(mark.third_assignment_mark),
                            _fmt_export_mark(mark.assignment_mark),
                            _fmt_export_mark(mark.first_class_test_mark),
                            _fmt_export_mark(mark.second_class_test_mark),
                            _fmt_export_mark(mark.class_test_mark),
                            str(int(math.ceil(float(mark.calculate_total_ca_mark() or 0))))
                        ]
                    else:
                        # New curriculum: use mid-term
                        row = [
                            str(sl_no),
                            student.id,
                            student.name.upper(),
                            _fmt_export_mark(mark.attendance_mark),
                            _fmt_export_mark(mark.first_assignment_mark),
                            _fmt_export_mark(mark.second_assignment_mark),
                            _fmt_export_mark(mark.third_assignment_mark),
                            _fmt_export_mark(mark.assignment_mark),
                            _fmt_export_mark(mark.midterm_mark),
                            str(int(math.ceil(float(mark.calculate_total_ca_mark() or 0))))
                        ]
            else:
                if course.course_type == 'PROJECT':
                    row = [str(sl_no), student.id, student.name.upper(), '0.00', '0.00', '0.00', '0.00']
                elif course.is_lab:
                    if course.effective_lab_ca_practical2_weight:
                        row = [str(sl_no), student.id, student.name.upper(), '0.00', '0.00', '0.00', '0.00', '0.00', '0.00', '0.00', '0.00']
                    else:
                        row = [str(sl_no), student.id, student.name.upper(), '0.00', '0.00', '0.00', '0.00', '0.00', '0.00', '0.00']
                else:
                    # Theory course - check curriculum
                    is_old_curriculum = semester.curriculum and semester.curriculum.code == 'OLD'
                    if is_old_curriculum:
                        # Old curriculum: 11 columns (Student ID, Name, Attendance, First, Second, Third, Average, First Class Test, Second Class Test, Best, Total)
                        row = [str(sl_no), student.id, student.name.upper(), '0.00', '0.00', '0.00', '0.00', '0.00', '0.00', '0.00', '0.00', '0.00']
                    else:
                        # New curriculum: 9 columns (Student ID, Name, Attendance, First, Second, Third, Average, Mid-Term, Total)
                        row = [str(sl_no), student.id, student.name.upper(), '0.00', '0.00', '0.00', '0.00', '0.00', '0.00', '0.00']
            table_data.append(row)
        
        # Create table with full width to align with header and footer
        # Calculate column widths based on available width
        num_cols = len(table_data[0]) if table_data else 0
        if num_cols > 0:
            # Allocate more width to SL, Student ID and Name columns
            sl_width = 40  # SL. No
            student_id_width = 80  # Student ID
            name_width = 150  # Name
            # Remaining width for mark columns
            remaining_width = available_width - sl_width - student_id_width - name_width
            mark_cols = num_cols - 3  # Exclude SL, Student ID and Name
            mark_col_width = remaining_width / mark_cols if mark_cols > 0 else 0
            # Build column widths array
            col_widths = [sl_width, student_id_width, name_width] + [mark_col_width] * mark_cols
            table = Table(table_data, colWidths=col_widths)
        else:
            table = Table(table_data)
        
        # Determine header row count
        if course.course_type == 'PROJECT':
            header_rows = 2
        else:
            header_rows = 3
        
        # Build style with merged cells for headers
        style_commands = [
            # Header styling (borders only; no background fill)
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'LEFT'),  # Name column (SL., Student ID, Name)
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, header_rows - 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, header_rows - 1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, header_rows - 1), 8),
            ('TOPPADDING', (0, 0), (-1, header_rows - 1), 8),
            # Grid
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            # Data rows styling
            ('FONTSIZE', (0, header_rows), (-1, -1), 8),
            # Student ID: bold + slightly larger (match Attendance export)
            ('FONTSIZE', (1, header_rows), (1, -1), 9),
            ('FONTNAME', (1, header_rows), (1, -1), 'Helvetica-Bold'),
            # Name: bold, compact
            ('FONTSIZE', (2, header_rows), (2, -1), 7),
            ('FONTNAME', (2, header_rows), (2, -1), 'Helvetica-Bold'),
        ]
        
        # Add cell spans for headers
        if course.course_type == 'PROJECT':
            # SL, Student ID and Name span 2 rows
            style_commands.append(('SPAN', (0, 0), (0, 1)))  # SL
            style_commands.append(('SPAN', (1, 0), (1, 1)))  # Student ID
            style_commands.append(('SPAN', (2, 0), (2, 1)))  # Name
            style_commands.append(('SPAN', (3, 0), (5, 0)))  # Project Work CA header
            style_commands.append(('SPAN', (6, 0), (6, 1)))  # Total
        elif course.is_lab:
            # SL, Student ID and Name span 3 rows
            style_commands.append(('SPAN', (0, 0), (0, 2)))  # SL
            style_commands.append(('SPAN', (1, 0), (1, 2)))  # Student ID
            style_commands.append(('SPAN', (2, 0), (2, 2)))  # Name
            if course.effective_lab_ca_practical2_weight:
                style_commands.append(('SPAN', (3, 0), (9, 0)))
                style_commands.append(('SPAN', (3, 1), (3, 2)))
                style_commands.append(('SPAN', (4, 1), (7, 1)))
                style_commands.append(('SPAN', (8, 1), (8, 2)))
                style_commands.append(('SPAN', (9, 1), (9, 2)))
                style_commands.append(('SPAN', (10, 0), (10, 2)))
            else:
                style_commands.append(('SPAN', (3, 0), (8, 0)))
                style_commands.append(('SPAN', (3, 1), (3, 2)))
                style_commands.append(('SPAN', (4, 1), (7, 1)))
                style_commands.append(('SPAN', (8, 1), (8, 2)))
                style_commands.append(('SPAN', (9, 0), (9, 2)))
        else:
            # Theory course - check curriculum to determine column spans
            is_old_curriculum = semester.curriculum and semester.curriculum.code == 'OLD'
            # SL, Student ID and Name span 3 rows
            style_commands.append(('SPAN', (0, 0), (0, 2)))  # SL
            style_commands.append(('SPAN', (1, 0), (1, 2)))  # Student ID
            style_commands.append(('SPAN', (2, 0), (2, 2)))  # Name
            if is_old_curriculum:
                # Old curriculum: Class Test has 3 columns (First, Second, Best)
                style_commands.append(('SPAN', (3, 0), (10, 0)))  # Theory Course CA header
                style_commands.append(('SPAN', (3, 1), (3, 2)))  # Attendance
                style_commands.append(('SPAN', (4, 1), (7, 1)))  # Assignment/Presentation
                style_commands.append(('SPAN', (8, 1), (10, 1)))  # Class Test
                style_commands.append(('SPAN', (11, 0), (11, 2)))  # Total
            else:
                # New curriculum: Mid-Term Exam is single column
                style_commands.append(('SPAN', (3, 0), (8, 0)))  # Theory Course CA header
                style_commands.append(('SPAN', (3, 1), (3, 2)))  # Attendance
                style_commands.append(('SPAN', (4, 1), (7, 1)))  # Assignment/Presentation
                style_commands.append(('SPAN', (8, 1), (8, 2)))  # Mid-Term Exam
                style_commands.append(('SPAN', (9, 0), (9, 2)))  # Total
        
        table.setStyle(TableStyle(style_commands))
        
        elements.append(table)

        def _draw_ca_marks_pdf_footer(cnv, page_num, total_pages):
            _draw_course_teacher_signature_pdf_footer(
                cnv, page_num, total_pages, _ca_lm, _ca_rm
            )

        _CaFooterCanvas = _make_deferred_footer_canvas_class(_draw_ca_marks_pdf_footer)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=_ca_rm,
            leftMargin=_ca_lm,
            topMargin=_ca_tm,
            bottomMargin=_ca_bm,
        )
        doc.build(elements, canvasmaker=_CaFooterCanvas)
        pdf_bytes = buffer.getvalue()

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"CA_Marks_{course.code}_{semester.name}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        return HttpResponse(f"Error generating PDF: {str(e)}", status=500)


@login_required
def export_midterm_marks_pdf(request):
    """Export theory mid-term Q1–Q6 marks to PDF (new curriculum)."""
    try:
        semester, course, students, centre_id = _midterm_marks_export_queryset(request)
        if semester is None:
            return redirect('ca-management')

        midterm_marks = {
            m.student_id: m
            for m in MidtermExamMark.objects.filter(
                student__in=students,
                course=course,
                semester=semester,
            )
        }
        return _build_midterm_marks_pdf_response(
            semester, course, students, centre_id, midterm_marks, blank=False
        )

    except Exception as e:
        return HttpResponse(f'Error generating PDF: {str(e)}', status=500)


def _midterm_marks_export_queryset(request, *, staff_only=False):
    """
    Validate mid-term export request and return (semester, course, students, centre_id).
    On failure returns (None, None, None, None) after setting messages and redirect is caller's duty.
    """
    if staff_only:
        if not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, "You don't have permission to export blank mid-term marks sheets.")
            return None, None, None, None
    elif not (
        request.user.is_superuser
        or request.user.is_staff
        or check_teacher_permission(request.user, 'can_manage_ca')
    ):
        messages.error(request, "You don't have permission to export mid-term marks.")
        return None, None, None, None

    semester_id = request.GET.get('semester')
    course_id = request.GET.get('course')
    centre_id = request.GET.get('centre')

    if not semester_id or not course_id:
        messages.error(request, 'Please select a semester and course.')
        return None, None, None, None

    try:
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
    except (Semester.DoesNotExist, Course.DoesNotExist):
        messages.error(request, 'Invalid semester or course.')
        return None, None, None, None

    if not staff_only and not _user_can_edit_ca_and_midterm(request, semester, course, centre_id):
        messages.error(request, 'Only the course teacher can export Mid-Term marks for this course.')
        return None, None, None, None

    if course.is_lab or course.course_type == 'PROJECT':
        messages.error(request, 'Mid-term marks export applies only to theory courses.')
        return None, None, None, None
    if not semester.curriculum or semester.curriculum.code == 'OLD':
        messages.error(request, 'Mid-term marks export applies only to new curriculum semesters.')
        return None, None, None, None

    students = Student.objects.filter(semesters=semester).extra(
        select={
            'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
            'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)",
        }
    ).order_by('-first_two_digits', 'last_three_digits')
    students = filter_students_queryset_by_centre(students, centre_id)
    return semester, course, students, centre_id


def _build_midterm_marks_pdf_response(semester, course, students, centre_id, midterm_marks, *, blank=False):
    """Build mid-term marks PDF (filled or blank sheet)."""
    _mt_lm = 54
    _mt_rm = 54
    _mt_tm = 34
    _mt_bm = 70

    page_width, _page_height = landscape(A4)
    available_width = page_width - _mt_lm - _mt_rm
    elements = []

    header_img_path = 'bou_routines_app/static/pdf_routine_top.png'
    try:
        padding_for_image = 2
        img_obj = Image(
            header_img_path,
            width=available_width - (2 * padding_for_image),
            height=45,
        )
        header_img_table = Table([[img_obj]], colWidths=[available_width])
        header_img_table.setStyle(
            TableStyle(
                [
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), padding_for_image),
                    ('RIGHTPADDING', (0, 0), (-1, -1), padding_for_image),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]
            )
        )
        elements.append(header_img_table)
    except Exception:
        pass
    elements.append(Spacer(1, -4))

    centre_name = ''
    if centre_id:
        try:
            centre_name = Centre.objects.get(id=int(centre_id)).name
        except (Centre.DoesNotExist, ValueError, TypeError):
            pass

    header_style = ParagraphStyle(
        'MtHeaderStyle',
        fontName='Helvetica-Bold',
        fontSize=15,
        alignment=1,
        leading=18,
        spaceAfter=0,
        spaceBefore=0,
    )
    header_style_small = ParagraphStyle(
        'MtHeaderStyleSmall',
        fontName='Helvetica-Bold',
        fontSize=11,
        alignment=1,
        leading=14,
        spaceAfter=0,
        spaceBefore=0,
    )
    header_style_normal = ParagraphStyle(
        'MtHeaderStyleNormal',
        fontName='Helvetica',
        fontSize=10,
        alignment=1,
        leading=11,
        spaceAfter=0,
        spaceBefore=0,
    )
    header_style_bold = ParagraphStyle(
        'MtHeaderStyleBold',
        fontName='Helvetica-Bold',
        fontSize=12,
        alignment=1,
        leading=15,
        spaceAfter=0,
        spaceBefore=0,
    )

    left_content = []
    left_content.append(Paragraph('B. Sc in Computer Science and Engineering Program', header_style))
    session = semester.session or ''
    if session:
        left_content.append(Paragraph(f'{session} Session', header_style_small))
    term = semester.term or ''
    semester_full_name = semester.semester_full_name or ''
    if term or semester_full_name:
        left_content.append(Paragraph(f'{term} Term {semester_full_name}'.strip(), header_style_small))
    left_content.append(Spacer(1, 2))
    course_name_display = f'{course.code} - {course.name}' if course else 'Course'
    title_prefix = 'Mid-Term Marks Sheet' if blank else 'Mid-Term Marks'
    left_content.append(Paragraph(f'{title_prefix} - {course_name_display}', header_style_bold))

    teacher_name = None
    if centre_id:
        try:
            centre = Centre.objects.get(id=int(centre_id))
            semester_course = SemesterCourse.objects.filter(
                semester=semester,
                course=course,
                centre=centre,
            ).select_related('teacher').first()
            if semester_course and semester_course.teacher:
                teacher_name = semester_course.teacher.name
                if not centre_name:
                    centre_name = centre.name
        except (Centre.DoesNotExist, ValueError, TypeError):
            pass
    if teacher_name:
        left_content.append(Paragraph(f'<b>Faculty:</b> {teacher_name}', header_style_normal))
    if not centre_name:
        first_sc = SemesterCourse.objects.filter(semester=semester).select_related('centre').first()
        if first_sc and first_sc.centre:
            centre_name = first_sc.centre.name
    if centre_name:
        left_content.append(Paragraph(f'<b>Study Center:</b> {centre_name}', header_style_normal))

    left_box_table = Table(
        [[left_content]],
        colWidths=[available_width],
        hAlign='CENTER',
        style=TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]),
    )
    elements.append(Spacer(1, 4))
    elements.append(left_box_table)
    elements.append(Spacer(1, 4))

    set_max = MidtermExamMark.SET_MARKS_MAX
    raw_max = MidtermExamMark.RAW_TOTAL_MAX

    table_data = [
        [
            'SL. No',
            'Student ID',
            'Name',
            f'Theory Mid-Term Exam (total max {raw_max})',
            '',
            '',
            '',
            '',
            '',
            'Total',
        ],
        [
            '',
            '',
            '',
            f'Group A\n(Any 2 of Q1–Q3, max {set_max} each)',
            '',
            '',
            f'Group B\n(Any 1 of Q4–Q5, max {set_max})',
            '',
            f'Group C\n(Q6, max {set_max})',
            '',
        ],
        ['', '', '', 'Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', ''],
    ]

    for sl_no, student in enumerate(students, start=1):
        if blank:
            table_data.append(
                [str(sl_no), student.id, student.name.upper(), '', '', '', '', '', '', '']
            )
        else:
            mm = midterm_marks.get(student.id)
            if mm:
                q_cells = [_fmt_export_mark(getattr(mm, f'q{i}', None), 0) for i in range(1, 7)]
                total_cell = mm.raw_total_display()
            else:
                q_cells = [''] * 6
                total_cell = '-'
            table_data.append(
                [str(sl_no), student.id, student.name.upper(), *q_cells, total_cell]
            )

    sl_width = 40
    student_id_width = 80
    name_width = 150
    remaining_width = available_width - sl_width - student_id_width - name_width
    mark_col_width = remaining_width / 7.0
    col_widths = [sl_width, student_id_width, name_width] + [mark_col_width] * 7

    table = Table(table_data, colWidths=col_widths, repeatRows=3)
    header_rows = 3
    style_commands = [
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, header_rows - 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, header_rows - 1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, header_rows - 1), 8),
        ('TOPPADDING', (0, 0), (-1, header_rows - 1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, header_rows), (-1, -1), 8),
        ('FONTSIZE', (1, header_rows), (1, -1), 9),
        ('FONTNAME', (1, header_rows), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (2, header_rows), (2, -1), 7),
        ('FONTNAME', (2, header_rows), (2, -1), 'Helvetica-Bold'),
        ('SPAN', (0, 0), (0, 2)),
        ('SPAN', (1, 0), (1, 2)),
        ('SPAN', (2, 0), (2, 2)),
        ('SPAN', (3, 0), (8, 0)),
        ('SPAN', (3, 1), (5, 1)),
        ('SPAN', (6, 1), (7, 1)),
        ('SPAN', (8, 1), (8, 1)),
        ('SPAN', (9, 0), (9, 2)),
    ]
    table.setStyle(TableStyle(style_commands))
    elements.append(table)

    def _draw_midterm_pdf_footer(cnv, page_num, total_pages):
        _draw_course_teacher_signature_pdf_footer(
            cnv, page_num, total_pages, _mt_lm, _mt_rm
        )

    _MtFooterCanvas = _make_deferred_footer_canvas_class(_draw_midterm_pdf_footer)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=_mt_rm,
        leftMargin=_mt_lm,
        topMargin=_mt_tm,
        bottomMargin=_mt_bm,
    )
    doc.build(elements, canvasmaker=_MtFooterCanvas)
    pdf_bytes = buffer.getvalue()

    prefix = 'Blank_' if blank else ''
    filename = f'{prefix}Midterm_Marks_{course.code}_{semester.name}.pdf'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_blank_midterm_marks_pdf(request):
    """Export blank mid-term marks sheet (Student ID and Name only; Q1–Q6 and Total blank)."""
    try:
        semester, course, students, centre_id = _midterm_marks_export_queryset(
            request, staff_only=True
        )
        if semester is None:
            return redirect('ca-management')
        return _build_midterm_marks_pdf_response(
            semester, course, students, centre_id, {}, blank=True
        )
    except Exception as e:
        return HttpResponse(f'Error generating PDF: {str(e)}', status=500)


@login_required
def export_midterm_marks_excel(request):
    """Export theory mid-term Q1–Q6 marks to Excel (same header and table layout as PDF)."""
    try:
        semester, course, students, centre_id = _midterm_marks_export_queryset(request)
        if semester is None:
            return redirect('ca-management')

        midterm_marks = {
            m.student_id: m
            for m in MidtermExamMark.objects.filter(
                student__in=students,
                course=course,
                semester=semester,
            )
        }

        header_rows = _midterm_marks_export_table_header_rows()
        num_cols = len(header_rows[0])
        teacher_name, centre_name = _ca_marks_export_teacher_and_centre(semester, course, centre_id)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Mid-Term Marks')

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 15,
            'align': 'center',
            'valign': 'vcenter',
        })
        subtitle_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'align': 'center',
            'valign': 'vcenter',
        })
        normal_format = workbook.add_format({
            'font_size': 10,
            'align': 'center',
            'valign': 'vcenter',
        })
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 9,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'text_wrap': True,
        })
        cell_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 8,
        })
        cell_stripe_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 8,
            'bg_color': '#D3D3D3',
        })
        id_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 9,
            'bold': True,
        })
        id_stripe_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 9,
            'bold': True,
            'bg_color': '#D3D3D3',
        })
        name_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 7,
            'bold': True,
        })
        name_stripe_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 7,
            'bold': True,
            'bg_color': '#D3D3D3',
        })

        row = 0
        last_col = max(num_cols - 1, 0)
        worksheet.merge_range(
            row, 0, row, last_col,
            'B. Sc in Computer Science and Engineering Program',
            title_format,
        )
        row += 1
        session = semester.session or ''
        if session:
            worksheet.merge_range(row, 0, row, last_col, f'{session} Session', subtitle_format)
            row += 1
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            worksheet.merge_range(
                row, 0, row, last_col,
                f'{term} Term {semester_full_name}'.strip(),
                subtitle_format,
            )
            row += 1
        course_name_display = f'{course.code} - {course.name}'
        worksheet.merge_range(
            row, 0, row, last_col,
            f'Mid-Term Marks - {course_name_display}',
            subtitle_format,
        )
        row += 1
        if teacher_name:
            worksheet.merge_range(
                row, 0, row, last_col, f'Faculty: {teacher_name}', normal_format,
            )
            row += 1
        if centre_name:
            worksheet.merge_range(
                row, 0, row, last_col, f'Study Center: {centre_name}', normal_format,
            )
            row += 1

        table_header_start = row
        row += len(header_rows)
        _midterm_marks_export_apply_table_header_merges(
            worksheet, table_header_start, header_format, header_rows,
        )

        for sl_no, student in enumerate(students, start=1):
            stripe = sl_no % 2 == 0
            data = _midterm_marks_export_student_row(sl_no, student, midterm_marks.get(student.id))
            for col, value in enumerate(data):
                if col == 0:
                    fmt = cell_stripe_format if stripe else cell_format
                elif col == 1:
                    fmt = id_stripe_format if stripe else id_format
                elif col == 2:
                    fmt = name_stripe_format if stripe else name_format
                else:
                    fmt = cell_stripe_format if stripe else cell_format
                worksheet.write(row, col, value, fmt)
            row += 1

        worksheet.set_column(0, 0, 6)
        worksheet.set_column(1, 1, 12)
        worksheet.set_column(2, 2, 22)
        if num_cols > 3:
            worksheet.set_column(3, num_cols - 1, 9)
        for hr in range(len(header_rows)):
            worksheet.set_row(table_header_start + hr, 28)

        _excel_apply_landscape_a4_print_setup(worksheet, row - 1, last_col)

        workbook.close()
        output.seek(0)

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        filename = f'Midterm_Marks_{course.code}_{semester.name}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        return HttpResponse(f'Error generating Excel: {str(e)}', status=500)


def _midterm_marks_export_table_header_rows():
    """Multi-row mid-term table headers matching the PDF export."""
    set_max = MidtermExamMark.SET_MARKS_MAX
    raw_max = MidtermExamMark.RAW_TOTAL_MAX
    return [
        [
            'SL. No', 'Student ID', 'Name',
            f'Theory Mid-Term Exam (total max {raw_max})', '', '', '', '', '',
            'Total',
        ],
        [
            '', '', '',
            f'Group A\n(Any 2 of Q1–Q3, max {set_max} each)', '', '',
            f'Group B\n(Any 1 of Q4–Q5, max {set_max})', '',
            f'Group C\n(Q6, max {set_max})', '',
        ],
        ['', '', '', 'Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', ''],
    ]


def _midterm_marks_export_apply_table_header_merges(
    worksheet, start_row, header_fmt, header_rows,
):
    """Apply merged header cells for the mid-term marks table (same layout as PDF)."""
    num_header_rows = len(header_rows)
    last_row = num_header_rows - 1

    def cell_text(r, c):
        if r < len(header_rows) and c < len(header_rows[r]):
            return header_rows[r][c] or ''
        return ''

    def merge(r1, c1, r2, c2):
        worksheet.merge_range(
            start_row + r1, c1, start_row + r2, c2, cell_text(r1, c1), header_fmt,
        )

    def write(r, c):
        text = cell_text(r, c)
        if text:
            worksheet.write(start_row + r, c, text, header_fmt)

    merge(0, 0, last_row, 0)
    merge(0, 1, last_row, 1)
    merge(0, 2, last_row, 2)
    merge(0, 3, 0, 8)
    merge(1, 3, 1, 5)
    merge(1, 6, 1, 7)
    write(1, 8)
    for c in range(3, 9):
        write(2, c)
    merge(0, 9, last_row, 9)


def _midterm_marks_export_student_row(sl_no, student, mm):
    """One data row for mid-term Excel export (matches PDF)."""
    if mm:
        q_cells = [_fmt_export_mark(getattr(mm, f'q{i}', None), 0) for i in range(1, 7)]
        total_cell = mm.raw_total_display()
    else:
        q_cells = [''] * 6
        total_cell = '-'
    return [sl_no, student.id, student.name.upper(), *q_cells, total_cell]


@login_required
def export_blank_ca_marks_pdf(request):
    """Export blank CA marks sheet to PDF (only Student ID and Name filled, all other columns blank)"""
    try:
        # Check permissions - only admin/superuser can download blank sheets
        if not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, "You don't have permission to export blank CA marks sheets.")
            return redirect('ca-management')
        
        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        centre_id = request.GET.get('centre')
        
        if not semester_id or not course_id:
            messages.error(request, "Please select a semester and course.")
            return redirect('ca-management')
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        
        # Get students with custom sorting
        students = Student.objects.filter(semesters=semester).extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        students = filter_students_queryset_by_centre(students, centre_id)
        
        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=54,
            leftMargin=54,
            topMargin=34,
            # Leave room for per-page footer signature + page number
            bottomMargin=70
        )
        
        # Get page width and calculate available width
        page_width, page_height = landscape(A4)
        available_width = page_width - doc.leftMargin - doc.rightMargin
        
        elements = []
        
        # --- HEADER IMAGE SECTION ---
        header_img_path = 'bou_routines_app/static/pdf_routine_top.png'
        try:
            padding_for_image = 2
            img_obj = Image(header_img_path, width=available_width - (2 * padding_for_image), height=45)
            header_img_table = Table([[img_obj]], colWidths=[available_width])
            header_img_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1, -1), padding_for_image),
                ('RIGHTPADDING', (0,0), (-1, -1), padding_for_image),
                ('TOPPADDING', (0,0), (-1, -1), 0),
                ('BOTTOMPADDING', (0,0), (-1, -1), 0),
            ]))
            elements.append(header_img_table)
        except Exception as e:
            print(f"Error loading header image: {e}")
            pass
        elements.append(Spacer(1, -4))
        
        # Initialize centre_name
        centre_name = ''
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
                centre_name = centre.name
            except Centre.DoesNotExist:
                pass
        
        # Build header (same as regular export)
        header_style = ParagraphStyle(
            'HeaderStyle',
            fontName='Helvetica-Bold',
            fontSize=15,
            alignment=1,
            leading=18,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_small = ParagraphStyle(
            'HeaderStyleSmall',
            fontName='Helvetica-Bold',
            fontSize=11,
            alignment=1,
            leading=14,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_normal = ParagraphStyle(
            'HeaderStyleNormal',
            fontName='Helvetica',
            fontSize=10,
            alignment=1,
            leading=11,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_bold = ParagraphStyle(
            'HeaderStyleBold',
            fontName='Helvetica-Bold',
            fontSize=12,
            alignment=1,
            leading=15,
            spaceAfter=0,
            spaceBefore=0,
        )
        
        left_content = []
        program_name = 'B. Sc in Computer Science and Engineering Program'
        left_content.append(Paragraph(program_name, header_style))
        session = semester.session or ''
        if session:
            left_content.append(Paragraph(f'{session} Session', header_style_small))
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            combined = f'{term} Term {semester_full_name}'.strip()
            left_content.append(Paragraph(combined, header_style_small))
        left_content.append(Spacer(1, 2))
        course_name_display = f"{course.code} - {course.name}" if course else "Course"
        left_content.append(Paragraph(f'CA Marks Sheet - {course_name_display}', header_style_bold))
        # Get teacher name from SemesterCourse
        teacher_name = None
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
                semester_course = SemesterCourse.objects.filter(
                    semester=semester,
                    course=course,
                    centre=centre
                ).select_related('teacher').first()
                if semester_course and semester_course.teacher:
                    teacher_name = semester_course.teacher.name
            except Centre.DoesNotExist:
                pass
        # Only show teacher if found
        if teacher_name:
            left_content.append(Paragraph(f'<b>Faculty:</b> {teacher_name}', header_style_normal))
        if not centre_name:
            first_sc = SemesterCourse.objects.filter(semester=semester).select_related('centre').first()
            if first_sc and first_sc.centre:
                centre_name = first_sc.centre.name
        if centre_name:
            left_content.append(Paragraph(f'<b>Study Center:</b> {centre_name}', header_style_normal))
        
        # Build right column (contact person box) - same as regular export
        # Get coordinator for this specific semester/centre combination
        coordinator = None
        if centre:
            semester_centre_coordinator = SemesterCentreCoordinator.objects.filter(
                semester=semester,
                centre=centre
            ).select_related('program_coordinator', 'program_coordinator__teacher').first()
            if semester_centre_coordinator:
                coordinator = semester_centre_coordinator.program_coordinator
        contact_info_lines = []
        
        if coordinator:
            contact_label = Paragraph(
                'Contact Person',
                ParagraphStyle(
                    'ContactLabel',
                    fontName='Helvetica-Bold',
                    fontSize=11,
                    alignment=0,
                    textColor=colors.white,
                    spaceAfter=0,
                    spaceBefore=0,
                    leading=14,
                )
            )
            contact_label_table = Table(
                [[contact_label]],
                colWidths=[190],
                hAlign='RIGHT',
                style=TableStyle([
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                    ('TOPPADDING', (0,0), (-1,-1), -3),
                    ('LEFTPADDING', (0,0), (-1,-1), 0),
                    ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ])
            )
            if coordinator.teacher:
                contact_info_lines.append(coordinator.teacher.name)
            if coordinator.designation:
                contact_info_lines.append(coordinator.designation)
            if coordinator.secondary_designation:
                contact_info_lines.append(coordinator.secondary_designation)
            contact_info_lines.append('Bangladesh Open University')
            if coordinator.phone:
                contact_info_lines.append(f'Phone/Whatsapp: {coordinator.phone}')
            if coordinator.email:
                contact_info_lines.append(f'email:{coordinator.email}')
        else:
            contact_info_lines.append('Bangladesh Open University')
            contact_label = Paragraph(
                'Contact Person',
                ParagraphStyle(
                    'ContactLabel',
                    fontName='Helvetica-Bold',
                    fontSize=11,
                    alignment=0,
                    textColor=colors.white,
                    spaceAfter=0,
                    spaceBefore=0,
                    leading=14,
                )
            )
            contact_label_table = Table(
                [[contact_label]],
                colWidths=[190],
                hAlign='RIGHT',
                style=TableStyle([
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                    ('TOPPADDING', (0,0), (-1,-1), -3),
                    ('LEFTPADDING', (0,0), (-1,-1), 0),
                    ('RIGHTPADDING', (0,0), (-1,-1), 0),
                ])
            )
        
        contact_info_para = Paragraph(
            '<br/>'.join(contact_info_lines),
            ParagraphStyle(
                'ContactBox',
                fontName='Helvetica',
                fontSize=10,
                alignment=0,
                textColor=colors.black,
                leftIndent=2,
                leading=10,
                spaceBefore=0,
                spaceAfter=0,
            )
        )
        contact_table = Table(
            [[contact_label_table], [contact_info_para]],
            colWidths=[190],
            hAlign='RIGHT',
        )
        contact_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('ROUNDED', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#2c3e50')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (0, 0), 6),
            ('BOTTOMPADDING', (0, 0), (0, 0), 4),
            ('TOPPADDING', (0, 1), (0, 1), 4),
            ('BOTTOMPADDING', (0, 1), (0, 1), 6),
        ]))
        
        left_box_table = Table(
            [[left_content]],
            colWidths=[available_width-190],
            hAlign='LEFT',
            style=TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ])
        )
        two_col_table = Table(
            [[left_box_table, contact_table]],
            colWidths=[available_width-190, 190],
            hAlign='LEFT'
        )
        two_col_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
            ('VALIGN', (1, 0), (1, 0), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        elements.append(Spacer(1, 4))
        elements.append(two_col_table)
        elements.append(Spacer(1, 4))
        
        # Build table data with multi-row headers (same structure as regular export)
        table_data = []
        
        # Get effective weights for display
        if course.course_type == 'PROJECT':
            total_ca = course.effective_project_supervisor_weight + course.effective_project_evaluation_weight + course.effective_project_presentation_weight
            header_row_1 = [
                'Student ID', 'Name',
                f'Project Work CA (Total: {total_ca}%)', '', '',
                'Total'
            ]
            header_row_2 = [
                '', '',
                f'Supervisor\n({course.effective_project_supervisor_weight}%)',
                f'Evaluation\n({course.effective_project_evaluation_weight}%)',
                f'Presentation\n({course.effective_project_presentation_weight}%)',
                ''
            ]
            table_data.append(header_row_1)
            table_data.append(header_row_2)
        elif course.is_lab:
            total_ca = course.effective_lab_ca_total_marks
            p2w = course.effective_lab_ca_practical2_weight
            if p2w:
                header_row_1 = [
                    'Student ID', 'Name',
                    f'Lab Course CA (Total: {total_ca}%)', '', '', '', '', '', '',
                    'Total'
                ]
                header_row_2 = [
                    '', '',
                    f'Attendance\n({course.effective_lab_ca_attendance_weight}%)',
                    f'Assignment/Lab Report\n({course.effective_lab_ca_assignment_weight}%)', '', '', '',
                    f'Experiment/\nLab Project\n({course.effective_lab_ca_practical_weight}%)',
                    f'Experiment/\nLab Project\n({p2w}%)',
                    ''
                ]
                header_row_3 = [
                    '', '', '',
                    'First', 'Second', 'Third', 'Average', '', '', ''
                ]
            else:
                total_ca = (
                    course.effective_lab_ca_attendance_weight
                    + course.effective_lab_ca_assignment_weight
                    + course.effective_lab_ca_practical_weight
                )
                header_row_1 = [
                    'Student ID', 'Name',
                    f'Lab Course CA (Total: {total_ca}%)', '', '', '', '',
                    '', 'Total'
                ]
                header_row_2 = [
                    '', '',
                    f'Attendance\n({course.effective_lab_ca_attendance_weight}%)',
                    f'Assignment/Lab Report\n({course.effective_lab_ca_assignment_weight}%)', '', '', '',
                    f'Experiment/\nLab Project\n({course.effective_lab_ca_practical_weight}%)',
                    ''
                ]
                header_row_3 = [
                    '', '',
                    '',
                    'First', 'Second', 'Third', 'Average',
                    '', ''
                ]
            table_data.append(header_row_1)
            table_data.append(header_row_2)
            table_data.append(header_row_3)
        else:
            # Theory course headers - check curriculum
            is_old_curriculum = semester.curriculum and semester.curriculum.code == 'OLD'
            if is_old_curriculum:
                # Old curriculum: use class tests
                exam_weight = course.effective_ca_quiz_weight
                total_ca = course.effective_ca_attendance_weight + course.effective_ca_assignment_weight + exam_weight
                header_row_1 = [
                    'Student ID', 'Name',
                    f'Theory Course CA (Total: {total_ca}%)', '', '', '', '', '', '',
                    '', 'Total'
                ]
                header_row_2 = [
                    '', '',
                    f'Attendance\n({course.effective_ca_attendance_weight}%)',
                    f'Assignment/Presentation\n({course.effective_ca_assignment_weight}%)', '', '', '',
                    f'Class Test\n({exam_weight}%)', '', '',
                    'Total'
                ]
                header_row_3 = [
                    '', '',
                    '',
                    'First', 'Second', 'Third', 'Average',
                    'First', 'Second', 'Best',
                    'Total'
                ]
            else:
                # New curriculum: use mid-term
                exam_weight = course.effective_ca_midterm_weight
                total_ca = course.effective_ca_attendance_weight + course.effective_ca_assignment_weight + exam_weight
                header_row_1 = [
                    'Student ID', 'Name',
                    f'Theory Course CA (Total: {total_ca}%)', '', '', '', '',
                    '', 'Total'
                ]
                header_row_2 = [
                    '', '',
                    f'Attendance\n({course.effective_ca_attendance_weight}%)',
                    f'Assignment/Presentation\n({course.effective_ca_assignment_weight}%)', '', '', '',
                    f'Mid-Term\nExam\n({exam_weight}%)',
                    'Total'
                ]
                header_row_3 = [
                    '', '',
                    '',
                    'First', 'Second', 'Third', 'Average',
                    '', 'Total'
                ]
            table_data.append(header_row_1)
            table_data.append(header_row_2)
            table_data.append(header_row_3)
        
        # Data rows - only Student ID and Name filled, all other cells blank
        for student in students:
            if course.course_type == 'PROJECT':
                row = [student.id, student.name.upper(), '', '', '', '']
            elif course.is_lab:
                if course.effective_lab_ca_practical2_weight:
                    row = [student.id, student.name.upper(), '', '', '', '', '', '', '', '']
                else:
                    row = [student.id, student.name.upper(), '', '', '', '', '', '', '']
            else:
                # Theory course - check curriculum
                is_old_curriculum = semester.curriculum and semester.curriculum.code == 'OLD'
                if is_old_curriculum:
                    # Old curriculum: 11 columns (Student ID, Name, Attendance, First, Second, Third, Average, First Class Test, Second Class Test, Best, Total)
                    row = [student.id, student.name.upper(), '', '', '', '', '', '', '', '', '']
                else:
                    # New curriculum: 9 columns (Student ID, Name, Attendance, First, Second, Third, Average, Mid-Term, Total)
                    row = [student.id, student.name.upper(), '', '', '', '', '', '', '']
            table_data.append(row)
        
        # Create table with full width to align with header and footer
        # Calculate column widths based on available width
        num_cols = len(table_data[0]) if table_data else 0
        if num_cols > 0:
            # Allocate more width to Student ID and Name columns
            student_id_width = 80  # Fixed width for Student ID
            name_width = 150  # Wider width for Name to prevent cutoff
            # Remaining width for mark columns
            remaining_width = available_width - student_id_width - name_width
            mark_cols = num_cols - 2  # Exclude Student ID and Name
            mark_col_width = remaining_width / mark_cols if mark_cols > 0 else 0
            # Build column widths array
            col_widths = [student_id_width, name_width] + [mark_col_width] * mark_cols
            table = Table(table_data, colWidths=col_widths)
        else:
            table = Table(table_data)
        
        # Determine header row count
        if course.course_type == 'PROJECT':
            header_rows = 2
        else:
            header_rows = 3
        
        # Build style with merged cells for headers (same as regular export)
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, header_rows - 1), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, header_rows - 1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),  # Name column (Student ID, Name, …)
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, header_rows - 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, header_rows - 1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, header_rows - 1), 8),
            ('TOPPADDING', (0, 0), (-1, header_rows - 1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, header_rows), (-1, -1), 8),
            # Student ID: bold + slightly larger (match Attendance export)
            ('FONTSIZE', (1, header_rows), (1, -1), 9),
            ('FONTNAME', (1, header_rows), (1, -1), 'Helvetica-Bold'),
            # Name: bold, compact
            ('FONTSIZE', (2, header_rows), (2, -1), 7),
            ('FONTNAME', (2, header_rows), (2, -1), 'Helvetica-Bold'),
        ]
        
        # Add cell spans for headers (same as regular export)
        if course.course_type == 'PROJECT':
            style_commands.append(('SPAN', (0, 0), (0, 1)))  # Student ID
            style_commands.append(('SPAN', (1, 0), (1, 1)))  # Name
            style_commands.append(('SPAN', (2, 0), (4, 0)))  # Project Work CA header
            style_commands.append(('SPAN', (5, 0), (5, 1)))  # Total
        elif course.is_lab:
            style_commands.append(('SPAN', (0, 0), (0, 2)))  # Student ID
            style_commands.append(('SPAN', (1, 0), (1, 2)))  # Name
            if course.effective_lab_ca_practical2_weight:
                style_commands.append(('SPAN', (2, 0), (8, 0)))
                style_commands.append(('SPAN', (2, 1), (2, 2)))
                style_commands.append(('SPAN', (3, 1), (6, 1)))
                style_commands.append(('SPAN', (7, 1), (7, 2)))
                style_commands.append(('SPAN', (8, 1), (8, 2)))
                style_commands.append(('SPAN', (9, 0), (9, 2)))
            else:
                style_commands.append(('SPAN', (2, 0), (7, 0)))
                style_commands.append(('SPAN', (2, 1), (2, 2)))
                style_commands.append(('SPAN', (3, 1), (6, 1)))
                style_commands.append(('SPAN', (7, 1), (7, 2)))
                style_commands.append(('SPAN', (8, 0), (8, 2)))
        else:
            # Theory course - check curriculum
            is_old_curriculum = semester.curriculum and semester.curriculum.code == 'OLD'
            style_commands.append(('SPAN', (0, 0), (0, 2)))  # Student ID
            style_commands.append(('SPAN', (1, 0), (1, 2)))  # Name
            if is_old_curriculum:
                # Old curriculum: Class Test has 3 columns (First, Second, Best)
                style_commands.append(('SPAN', (2, 0), (9, 0)))  # Theory Course CA header (spans columns 2-9)
                style_commands.append(('SPAN', (2, 1), (2, 2)))  # Attendance (spans rows 1-2)
                style_commands.append(('SPAN', (3, 1), (6, 1)))  # Assignment/Presentation (spans columns 3-6, row 1)
                style_commands.append(('SPAN', (7, 1), (9, 1)))  # Class Test (spans columns 7-9, row 1)
                style_commands.append(('SPAN', (10, 0), (10, 2)))  # Total (spans rows 0-2, column 10)
            else:
                # New curriculum: Mid-Term Exam is single column
                style_commands.append(('SPAN', (2, 0), (7, 0)))  # Theory Course CA header (spans columns 2-7)
                style_commands.append(('SPAN', (2, 1), (2, 2)))  # Attendance (spans rows 1-2)
                style_commands.append(('SPAN', (3, 1), (6, 1)))  # Assignment/Presentation (spans columns 3-6, row 1)
                style_commands.append(('SPAN', (7, 1), (7, 2)))  # Mid-Term Exam (spans rows 1-2)
                style_commands.append(('SPAN', (8, 0), (8, 2)))  # Total (spans rows 0-2, column 8)
        
        table.setStyle(TableStyle(style_commands))
        
        elements.append(table)
        
        # Add footer with signatures (same as regular export)
        elements.append(Spacer(1, 40))  # Increased from 24 to 40 for more space above signature
        signature_style = ParagraphStyle(
            'SignatureStyle',
            fontName='Helvetica',
            fontSize=10,
            alignment=TA_RIGHT,
            leading=6,
            spaceBefore=0,
            spaceAfter=0,
        )
        signature_style_left = ParagraphStyle(
            'SignatureStyleLeft',
            fontName='Helvetica',
            fontSize=10,
            alignment=0,
            leading=6,
            spaceBefore=0,
            spaceAfter=0,
        )
        signature_data = [[Paragraph("External Examiner", signature_style)]]
        signature_data_left = [[Paragraph("Internal Examiner", signature_style_left)]]
        signature_table_width = 250
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
        elements.append(signature_wrapper_table)
        
        # Build PDF
        doc.build(elements, onFirstPage=_pdf_add_page_number, onLaterPages=_pdf_add_page_number)
        buffer.seek(0)
        
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        filename = f"Blank_CA_Marks_{course.code}_{semester.name}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        return HttpResponse(f"Error generating PDF: {str(e)}", status=500)

@login_required
def export_ca_marks_excel(request):
    """Export CA marks to Excel (same header and table layout as PDF export)."""
    try:
        if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_manage_ca')):
            messages.error(request, "You don't have permission to export CA marks.")
            return redirect('ca-management')

        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        centre_id = request.GET.get('centre')

        if not semester_id or not course_id:
            messages.error(request, "Please select a semester and course.")
            return redirect('ca-management')

        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        if not _user_can_edit_ca_and_midterm(request, semester, course, centre_id):
            messages.error(request, "Only the course teacher can export CA marks for this course.")
            return redirect('ca-management')

        students = Student.objects.filter(semesters=semester).extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        students = filter_students_queryset_by_centre(students, centre_id)
        ca_marks = _ca_marks_dict_for_students_course_semester(students, course, semester)

        header_rows = _ca_marks_export_table_header_rows(course, semester)
        num_cols = len(header_rows[0])
        teacher_name, centre_name = _ca_marks_export_teacher_and_centre(semester, course, centre_id)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('CA Marks')

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 15,
            'align': 'center',
            'valign': 'vcenter',
        })
        subtitle_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'align': 'center',
            'valign': 'vcenter',
        })
        normal_format = workbook.add_format({
            'font_size': 10,
            'align': 'center',
            'valign': 'vcenter',
        })
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 9,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'text_wrap': True,
        })
        cell_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 8,
        })
        cell_stripe_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 8,
            'bg_color': '#D3D3D3',
        })
        id_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 9,
            'bold': True,
        })
        id_stripe_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 9,
            'bold': True,
            'bg_color': '#D3D3D3',
        })
        name_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 7,
            'bold': True,
        })
        name_stripe_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'font_size': 7,
            'bold': True,
            'bg_color': '#D3D3D3',
        })

        row = 0
        last_col = max(num_cols - 1, 0)
        worksheet.merge_range(
            row, 0, row, last_col,
            'B. Sc in Computer Science and Engineering Program',
            title_format,
        )
        row += 1
        session = semester.session or ''
        if session:
            worksheet.merge_range(row, 0, row, last_col, f'{session} Session', subtitle_format)
            row += 1
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            worksheet.merge_range(
                row, 0, row, last_col,
                f'{term} Term {semester_full_name}'.strip(),
                subtitle_format,
            )
            row += 1
        worksheet.merge_range(
            row, 0, row, last_col,
            'Continuous Assessment (CA) Marks',
            subtitle_format,
        )
        row += 1
        if teacher_name:
            worksheet.merge_range(
                row, 0, row, last_col, f'Faculty: {teacher_name}', normal_format,
            )
            row += 1
        if centre_name:
            worksheet.merge_range(
                row, 0, row, last_col, f'Study Center: {centre_name}', normal_format,
            )
            row += 1

        table_header_start = row
        row += len(header_rows)
        _ca_marks_export_apply_table_header_merges(
            worksheet, course, semester, table_header_start, header_format, header_rows
        )

        for sl_no, student in enumerate(students, start=1):
            stripe = sl_no % 2 == 0
            data = _ca_marks_export_student_row(
                course, semester, sl_no, student, ca_marks.get(student.id)
            )
            for col, value in enumerate(data):
                if col == 1:
                    fmt = id_stripe_format if stripe else id_format
                elif col == 2:
                    fmt = name_stripe_format if stripe else name_format
                else:
                    fmt = cell_stripe_format if stripe else cell_format
                worksheet.write(row, col, value, fmt)
            row += 1

        worksheet.set_column(0, 0, 6)
        worksheet.set_column(1, 1, 12)
        worksheet.set_column(2, 2, 22)
        if num_cols > 3:
            worksheet.set_column(3, num_cols - 1, 9)

        _excel_apply_landscape_a4_print_setup(worksheet, row - 1, last_col)

        workbook.close()
        output.seek(0)

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        filename = f"CA_Marks_{course.code}_{semester.name}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        return HttpResponse(f"Error generating Excel: {str(e)}", status=500)


def _final_exam_lab_export_meta(course, semester):
    """Lab final exam column maxima (matches ca_management / HTML table)."""
    meta = {
        'lab_final_exam_max': 50,
        'lab_final_uses_viva': False,
        'lab_final_problem_solving_max': 50,
        'lab_final_viva_max': 5,
    }
    if not course.is_lab:
        return meta
    if semester.curriculum and semester.curriculum.code == 'OLD':
        meta['lab_final_exam_max'] = 60
    elif semester.curriculum:
        meta['lab_final_exam_max'] = 25
        meta['lab_final_uses_viva'] = True
        meta['lab_final_problem_solving_max'] = 20
    else:
        meta['lab_final_exam_max'] = 60
    return meta


def _final_exam_export_examiner_name(semester, course, centre_id, teacher_role):
    """Resolve examiner display name for final exam exports."""
    teacher_name = None
    sample_mark = FinalExamMark.objects.filter(course=course, semester=semester).first()
    if sample_mark:
        if teacher_role == 'teacher1' and sample_mark.teacher1_evaluator:
            teacher_name = sample_mark.teacher1_evaluator.name
        elif teacher_role == 'teacher2' and sample_mark.teacher2_evaluator:
            teacher_name = sample_mark.teacher2_evaluator.name
        elif teacher_role == 'teacher3' and sample_mark.teacher3_evaluator:
            teacher_name = sample_mark.teacher3_evaluator.name
    if not teacher_name:
        drc_centre = Centre.objects.filter(code='DRC').first()
        duet_centre = Centre.objects.filter(code='DUET').first()
        if teacher_role == 'teacher1' and drc_centre:
            sc = SemesterCourse.objects.filter(
                semester=semester, course=course, centre=drc_centre,
            ).select_related('teacher').first()
            if sc and sc.teacher:
                teacher_name = sc.teacher.name
        elif teacher_role == 'teacher2' and duet_centre:
            sc = SemesterCourse.objects.filter(
                semester=semester, course=course, centre=duet_centre,
            ).select_related('teacher').first()
            if sc and sc.teacher:
                teacher_name = sc.teacher.name
        elif teacher_role == 'teacher3' and sample_mark and sample_mark.teacher3_evaluator:
            teacher_name = sample_mark.teacher3_evaluator.name
    return teacher_name


def _final_exam_q_prefix(teacher_role):
    if teacher_role == 'teacher2':
        return 'teacher2'
    if teacher_role == 'teacher3':
        return 'teacher3'
    return 'teacher1'


def _final_exam_theory_table_header_rows():
    set_max = 14
    raw_max = 70
    return [
        [
            'SL.\nNo', 'Student ID', 'Name',
            f'Theory Course Final Exam (Total: {raw_max} marks)', '', '', '', '', '', '',
            'Total',
        ],
        [
            '', '', '',
            f'Group A\n(Any 2 of Q1–Q3,\nmax {set_max} per set)', '', '',
            f'Group B\n(Any 2 of Q4–Q6,\nmax {set_max} per set)', '', '',
            f'Group C\n(Q7,\nmax {set_max})', '',
        ],
        ['', '', '', 'Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', ''],
    ]


def _final_exam_lab_table_header_rows(course, semester, *, blank=False):
    meta = _final_exam_lab_export_meta(course, semester)
    if meta['lab_final_uses_viva']:
        if blank:
            # Blank sheet: Problem Solving only (no Lab Course Final Exam super-header)
            return [
                [
                    'SL.\nNo', 'Student ID', 'Name',
                    f"Problem Solving\n(max {meta['lab_final_problem_solving_max']})",
                ],
            ]
        return [
            [
                'SL.\nNo', 'Student ID', 'Name',
                f"Lab Course Final Exam (Total: {meta['lab_final_exam_max']} marks)", '', '',
            ],
            [
                '', '', '',
                f"Problem Solving\n(max {meta['lab_final_problem_solving_max']})",
                f"Viva\n(max {meta['lab_final_viva_max']})",
                'Total',
            ],
        ]
    if blank:
        return [
            ['SL.\nNo', 'Student ID', 'Name', 'Lab Course Final Exam Mark'],
        ]
    return [
        ['SL.\nNo', 'Student ID', 'Name', 'Lab Course Final Exam Mark', 'Total'],
    ]


def _final_exam_build_theory_student_row(sl_no, student, mark, teacher_role, *, blank=False):
    import math
    if blank:
        return [str(sl_no), student.id, student.name.upper(), *([''] * 7), '']
    if not mark:
        return [str(sl_no), student.id, student.name.upper(), *([''] * 7), '-']
    if getattr(mark, 'exam_absent', False):
        return [str(sl_no), student.id, student.name.upper(), *(['AB'] * 7), 'AB']
    prefix = _final_exam_q_prefix(teacher_role)
    q_vals = [getattr(mark, f'{prefix}_q{i}', None) for i in range(1, 8)]
    total_raw = getattr(mark, f'{prefix}_total', None)
    if total_raw is not None:
        total_cell = str(int(math.ceil(float(total_raw))))
    else:
        total_cell = str(int(math.ceil(sum(float(v or 0) for v in q_vals))))
    return [
        str(sl_no), student.id, student.name.upper(),
        *[_fmt_export_mark(v) for v in q_vals],
        total_cell,
    ]


def _final_exam_build_lab_student_row(sl_no, student, mark, teacher_role, course, semester, *, blank=False):
    import math
    meta = _final_exam_lab_export_meta(course, semester)
    if blank:
        # Blank PDF: one empty marks column only (no Viva / Total)
        return [str(sl_no), student.id, student.name.upper(), '']
    if not mark:
        if meta['lab_final_uses_viva']:
            return [str(sl_no), student.id, student.name.upper(), '', '', '-']
        return [str(sl_no), student.id, student.name.upper(), '', '-']
    if getattr(mark, 'exam_absent', False):
        if meta['lab_final_uses_viva']:
            return [str(sl_no), student.id, student.name.upper(), 'AB', 'AB', 'AB']
        return [str(sl_no), student.id, student.name.upper(), 'AB', 'AB']
    n = 2 if teacher_role == 'teacher2' else 1
    if meta['lab_final_uses_viva']:
        ps_raw = getattr(mark, f'teacher{n}_lab_final_exam_mark', None)
        viv_raw = getattr(mark, f'teacher{n}_lab_viva_mark', None)
        ps = float(ps_raw or 0)
        viv = float(viv_raw or 0)
        return [
            str(sl_no), student.id, student.name.upper(),
            _fmt_export_mark(ps_raw), _fmt_export_mark(viv_raw),
            str(int(math.ceil(ps + viv))),
        ]
    v_raw = getattr(mark, f'teacher{n}_lab_final_exam_mark', None)
    v = float(v_raw or 0)
    return [
        str(sl_no), student.id, student.name.upper(),
        _fmt_export_mark(v_raw), str(int(math.ceil(v))),
    ]


def _final_exam_pdf_theory_col_widths(available_width):
    """Portrait A4: compact Q1–Q7/Total so Name can stay wide."""
    sl_w, id_w = 22, 66
    q_w = 32
    tot_w = 32
    used = sl_w + id_w + (q_w * 7) + tot_w
    name_w = max(95, available_width - used)
    return [sl_w, id_w, name_w] + [q_w] * 7 + [tot_w]


def _final_exam_pdf_lab_col_widths(course, semester, available_width, *, blank=False):
    """Portrait A4: wide Name; narrower Problem Solving / Viva / Total."""
    sl_w, id_w, name_w = 24, 70, 175
    meta = _final_exam_lab_export_meta(course, semester)
    if blank:
        used = sl_w + id_w + name_w
        return [sl_w, id_w, name_w, max(80, available_width - used)]
    if meta['lab_final_uses_viva']:
        rest = max(130.0, available_width - sl_w - id_w - name_w)
        # Keep mark columns compact so Name can stay wide
        ps_w = max(48.0, rest * 0.38)
        viv_w = max(40.0, rest * 0.28)
        tot_w = max(40.0, rest - ps_w - viv_w)
        return [sl_w, id_w, name_w, ps_w, viv_w, tot_w]
    used = sl_w + id_w + name_w
    mark_w = max(55, (available_width - used) / 2.0)
    return [sl_w, id_w, name_w, mark_w, mark_w]


def _final_exam_pdf_table_style_commands(header_row_count):
    return [
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, header_row_count - 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, header_row_count - 1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, header_row_count - 1), 8),
        ('TOPPADDING', (0, 0), (-1, header_row_count - 1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, header_row_count), (-1, -1), 8),
        ('FONTSIZE', (1, header_row_count), (1, -1), 9),
        ('FONTNAME', (1, header_row_count), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (2, header_row_count), (2, -1), 8),
        ('FONTNAME', (2, header_row_count), (2, -1), 'Helvetica-Bold'),
        # Compact student rows (filled + blank Semester Final PDFs)
        ('TOPPADDING', (0, header_row_count), (-1, -1), 1),
        ('BOTTOMPADDING', (0, header_row_count), (-1, -1), 1),
    ]


def _final_exam_pdf_theory_header_spans():
    last = 2
    return [
        ('SPAN', (0, 0), (0, last)),
        ('SPAN', (1, 0), (1, last)),
        ('SPAN', (2, 0), (2, last)),
        ('SPAN', (3, 0), (9, 0)),
        ('SPAN', (3, 1), (5, 1)),
        ('SPAN', (6, 1), (8, 1)),
        ('SPAN', (9, 1), (9, 1)),
        ('SPAN', (10, 0), (10, last)),
    ]


def _final_exam_pdf_lab_header_spans(uses_viva, *, blank=False):
    if blank:
        return []
    if not uses_viva:
        return []
    return [
        ('SPAN', (0, 0), (0, 1)),
        ('SPAN', (1, 0), (1, 1)),
        ('SPAN', (2, 0), (2, 1)),
        ('SPAN', (3, 0), (5, 0)),
    ]


def _final_exam_pdf_marks_table(
    course, semester, students, final_exam_marks, teacher_role, available_width, *, blank=False,
):
    if course.is_lab:
        header_rows = _final_exam_lab_table_header_rows(course, semester, blank=blank)
        meta = _final_exam_lab_export_meta(course, semester)
        table_data = [list(row) for row in header_rows]
        for sl_no, student in enumerate(students, start=1):
            mark = None if blank else final_exam_marks.get(student.id)
            table_data.append(
                _final_exam_build_lab_student_row(
                    sl_no, student, mark, teacher_role, course, semester, blank=blank,
                )
            )
        col_widths = _final_exam_pdf_lab_col_widths(
            course, semester, available_width, blank=blank,
        )
        span_cmds = _final_exam_pdf_lab_header_spans(
            meta['lab_final_uses_viva'], blank=blank,
        )
    else:
        header_rows = _final_exam_theory_table_header_rows()
        table_data = [list(row) for row in header_rows]
        for sl_no, student in enumerate(students, start=1):
            mark = None if blank else final_exam_marks.get(student.id)
            table_data.append(
                _final_exam_build_theory_student_row(
                    sl_no, student, mark, teacher_role, blank=blank,
                )
            )
        col_widths = _final_exam_pdf_theory_col_widths(available_width)
        span_cmds = _final_exam_pdf_theory_header_spans() + [
            # Group A/B/C: wrap "max …" on its own line without growing header height
            ('FONTSIZE', (3, 1), (9, 1), 7.5),
            ('LEADING', (3, 1), (9, 1), 8.5),
            ('TOPPADDING', (3, 1), (9, 1), 2),
            ('BOTTOMPADDING', (3, 1), (9, 1), 2),
        ]

    header_row_count = len(header_rows)
    table = Table(table_data, colWidths=col_widths, repeatRows=header_row_count)
    table.setStyle(TableStyle(_final_exam_pdf_table_style_commands(header_row_count) + span_cmds))
    return table


def _final_exam_excel_apply_theory_header_merges(worksheet, start_row, header_fmt, header_rows):
    last_row = len(header_rows) - 1

    def cell_text(r, c):
        if r < len(header_rows) and c < len(header_rows[r]):
            return header_rows[r][c] or ''
        return ''

    def merge(r1, c1, r2, c2):
        worksheet.merge_range(
            start_row + r1, c1, start_row + r2, c2, cell_text(r1, c1), header_fmt,
        )

    def write(r, c):
        text = cell_text(r, c)
        if text:
            worksheet.write(start_row + r, c, text, header_fmt)

    merge(0, 0, last_row, 0)
    merge(0, 1, last_row, 1)
    merge(0, 2, last_row, 2)
    merge(0, 3, 0, 9)
    merge(1, 3, 1, 5)
    merge(1, 6, 1, 8)
    write(1, 9)
    for c in range(3, 10):
        write(2, c)
    merge(0, 10, last_row, 10)


def _final_exam_excel_apply_lab_header_merges(worksheet, start_row, header_fmt, header_rows, uses_viva):
    if not uses_viva:
        for c, text in enumerate(header_rows[0]):
            if text:
                worksheet.write(start_row, c, text, header_fmt)
        return

    last_row = len(header_rows) - 1

    def cell_text(r, c):
        if r < len(header_rows) and c < len(header_rows[r]):
            return header_rows[r][c] or ''
        return ''

    def merge(r1, c1, r2, c2):
        worksheet.merge_range(
            start_row + r1, c1, start_row + r2, c2, cell_text(r1, c1), header_fmt,
        )

    def write(r, c):
        text = cell_text(r, c)
        if text:
            worksheet.write(start_row + r, c, text, header_fmt)

    merge(0, 0, last_row, 0)
    merge(0, 1, last_row, 1)
    merge(0, 2, last_row, 2)
    merge(0, 3, 0, 5)
    for c in range(3, 6):
        write(1, c)


@login_required
def export_final_exam_pdf(request):
    """Export Final Exam marks to PDF"""
    try:
        import math
        # Check permissions
        if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_manage_final_marks')):
            messages.error(request, "You don't have permission to export Final Exam marks.")
            return redirect('ca-management')
        
        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        centre_id = request.GET.get('centre')
        teacher_role = request.GET.get('teacher_role', 'teacher1')
        
        if not semester_id or not course_id:
            messages.error(request, "Please select a semester and course.")
            return redirect('ca-management')
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        if course.is_lab and teacher_role == 'teacher3':
            teacher_role = 'teacher1'
        
        # Get centre if provided
        centre = None
        centre_name = ''
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
                centre_name = centre.name
            except Centre.DoesNotExist:
                pass
        
        # Get students with custom sorting
        students = Student.objects.filter(semesters=semester).extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        students = filter_students_queryset_by_centre(students, centre_id)
        
        # Get existing Final Exam marks
        existing_marks = FinalExamMark.objects.filter(
            student__in=students,
            course=course,
            semester=semester
        )
        
        final_exam_marks = {}
        for mark in existing_marks:
            final_exam_marks[mark.student.id] = mark
        
        _fe_lm = 40
        _fe_rm = 40
        _fe_tm = 34
        _fe_bm = 90

        # Portrait A4
        page_width, page_height = A4
        available_width = page_width - _fe_lm - _fe_rm

        elements = []
        
        # --- HEADER IMAGE SECTION ---
        header_img_path = 'bou_routines_app/static/pdf_routine_top.png'
        try:
            padding_for_image = 2
            img_obj = Image(header_img_path, width=available_width - (2 * padding_for_image), height=45)
            header_img_table = Table([[img_obj]], colWidths=[available_width])
            header_img_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1, -1), padding_for_image),
                ('RIGHTPADDING', (0,0), (-1, -1), padding_for_image),
                ('TOPPADDING', (0,0), (-1, -1), 0),
                ('BOTTOMPADDING', (0,0), (-1, -1), 0),
            ]))
            elements.append(header_img_table)
        except Exception as e:
            print(f"Error loading header image: {e}")
            pass
        elements.append(Spacer(1, -4))
        
        # Initialize centre_name if not already set
        if not centre_name:
            first_sc = SemesterCourse.objects.filter(semester=semester).select_related('centre').first()
            if first_sc and first_sc.centre:
                centre_name = first_sc.centre.name
        
        # Build left column (program/session/term/commencement/study center)
        header_style = ParagraphStyle(
            'HeaderStyle',
            fontName='Helvetica-Bold',
            fontSize=15,
            alignment=1,
            leading=18,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_small = ParagraphStyle(
            'HeaderStyleSmall',
            fontName='Helvetica-Bold',
            fontSize=11,
            alignment=1,
            leading=14,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_normal = ParagraphStyle(
            'HeaderStyleNormal',
            fontName='Helvetica',
            fontSize=10,
            alignment=1,
            leading=11,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_bold = ParagraphStyle(
            'HeaderStyleBold',
            fontName='Helvetica-Bold',
            fontSize=12,
            alignment=1,
            leading=15,
            spaceAfter=0,
            spaceBefore=0,
        )
        
        left_content = []
        program_name = 'B. Sc in Computer Science and Engineering Program'
        left_content.append(Paragraph(program_name, header_style))
        session = semester.session or ''
        if session:
            left_content.append(Paragraph(f'{session} Session', header_style_small))
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            combined = f'{term} Term {semester_full_name}'.strip()
            left_content.append(Paragraph(combined, header_style_small))
        left_content.append(Spacer(1, 2))
        course_name_display = f"{course.code} - {course.name}" if course else "Course"
        left_content.append(Paragraph(f'Semester Final Marks - {course_name_display}', header_style_bold))
        teacher_name = _final_exam_export_examiner_name(semester, course, centre_id, teacher_role)
        
        # Only show teacher if found
        if teacher_name:
            left_content.append(Paragraph(f'<b>Examiner:</b> {teacher_name}', header_style_normal))
        if centre_name:
            left_content.append(Paragraph(f'<b>Study Center:</b> {centre_name}', header_style_normal))
        
        # Header block (no Contact Person box)
        left_box_table = Table(
            [[left_content]],
            colWidths=[available_width],
            hAlign='CENTER',
            style=TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ])
        )
        elements.append(Spacer(1, 4))
        elements.append(left_box_table)
        elements.append(Spacer(1, 4))
        
        table = _final_exam_pdf_marks_table(
            course, semester, students, final_exam_marks, teacher_role, available_width,
        )
        elements.append(table)

        def _draw_final_exam_marks_pdf_footer(cnv, page_num, total_pages):
            pw, _ph = A4
            left_x = _fe_lm
            right_x_end = pw - _fe_rm
            sig_w = min(180, (right_x_end - left_x - 40) / 2.0)
            right_x = right_x_end - sig_w
            footer_y_line = 48
            footer_y_text = 34
            cnv.saveState()
            cnv.setLineWidth(1)
            cnv.setStrokeColor(colors.black)
            cnv.line(left_x, footer_y_line, left_x + sig_w, footer_y_line)
            cnv.line(right_x, footer_y_line, right_x_end, footer_y_line)
            cnv.setFont('Helvetica', 10)
            cnv.drawString(left_x, footer_y_text, 'Internal Examiner')
            cnv.drawRightString(right_x_end, footer_y_text, 'External Examiner')
            cnv.setFont('Helvetica', 9)
            cnv.drawCentredString(
                pw / 2.0, footer_y_text, _pdf_page_number_label(page_num, total_pages)
            )
            cnv.restoreState()

        _FeMarksFooterCanvas = _make_deferred_footer_canvas_class(_draw_final_exam_marks_pdf_footer)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=_fe_rm,
            leftMargin=_fe_lm,
            topMargin=_fe_tm,
            bottomMargin=_fe_bm,
        )
        doc.build(elements, canvasmaker=_FeMarksFooterCanvas)
        pdf_bytes = buffer.getvalue()

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"Final_Exam_Marks_{course.code}_{semester.name}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        return HttpResponse(f"Error generating PDF: {str(e)}", status=500)

@login_required
def export_blank_final_exam_pdf(request):
    """Export blank Final Exam marks sheet to PDF (only Student ID and Name filled, all other columns blank)"""
    try:
        # Check permissions - only admin/superuser can download blank sheets
        if not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, "You don't have permission to export blank Final Exam marks sheets.")
            return redirect('ca-management')
        
        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        centre_id = request.GET.get('centre')
        teacher_role = request.GET.get('teacher_role', 'teacher1')
        
        if not semester_id or not course_id:
            messages.error(request, "Please select a semester and course.")
            return redirect('ca-management')
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        
        # Get students with custom sorting
        students = Student.objects.filter(semesters=semester).extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        students = filter_students_queryset_by_centre(students, centre_id)

        _bfe_lm = 40
        _bfe_rm = 40
        _bfe_tm = 34
        _bfe_bm = 90
        page_width, page_height = A4
        available_width = page_width - _bfe_lm - _bfe_rm

        elements = []
        
        # --- HEADER IMAGE SECTION ---
        header_img_path = 'bou_routines_app/static/pdf_routine_top.png'
        try:
            padding_for_image = 2
            img_obj = Image(header_img_path, width=available_width - (2 * padding_for_image), height=45)
            header_img_table = Table([[img_obj]], colWidths=[available_width])
            header_img_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1, -1), padding_for_image),
                ('RIGHTPADDING', (0,0), (-1, -1), padding_for_image),
                ('TOPPADDING', (0,0), (-1, -1), 0),
                ('BOTTOMPADDING', (0,0), (-1, -1), 0),
            ]))
            elements.append(header_img_table)
        except Exception as e:
            print(f"Error loading header image: {e}")
            pass
        elements.append(Spacer(1, -4))
        
        # Initialize centre_name
        centre_name = ''
        if centre_id:
            try:
                centre = Centre.objects.get(id=centre_id)
                centre_name = centre.name
            except Centre.DoesNotExist:
                pass
        
        # Build header (same as regular export)
        header_style = ParagraphStyle(
            'HeaderStyle',
            fontName='Helvetica-Bold',
            fontSize=15,
            alignment=1,
            leading=18,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_small = ParagraphStyle(
            'HeaderStyleSmall',
            fontName='Helvetica-Bold',
            fontSize=11,
            alignment=1,
            leading=14,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_normal = ParagraphStyle(
            'HeaderStyleNormal',
            fontName='Helvetica',
            fontSize=10,
            alignment=1,
            leading=11,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_bold = ParagraphStyle(
            'HeaderStyleBold',
            fontName='Helvetica-Bold',
            fontSize=12,
            alignment=1,
            leading=15,
            spaceAfter=0,
            spaceBefore=0,
        )
        
        left_content = []
        program_name = 'B. Sc in Computer Science and Engineering Program'
        left_content.append(Paragraph(program_name, header_style))
        session = semester.session or ''
        if session:
            left_content.append(Paragraph(f'{session} Session', header_style_small))
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            combined = f'{term} Term {semester_full_name}'.strip()
            left_content.append(Paragraph(combined, header_style_small))
        left_content.append(Spacer(1, 2))
        course_name_display = f"{course.code} - {course.name}" if course else "Course"
        left_content.append(Paragraph(f'Final Exam Marks Sheet - {course_name_display}', header_style_bold))
        # Blank sheet: omit Examiner line (filled PDF still shows it)
        if not centre_name:
            first_sc = SemesterCourse.objects.filter(semester=semester).select_related('centre').first()
            if first_sc and first_sc.centre:
                centre_name = first_sc.centre.name
        if centre_name:
            left_content.append(Paragraph(f'<b>Study Center:</b> {centre_name}', header_style_normal))
        
        # Header block (no Contact Person / Examiner) — blank Final Exam PDF
        left_box_table = Table(
            [[left_content]],
            colWidths=[available_width],
            hAlign='CENTER',
            style=TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ])
        )
        elements.append(Spacer(1, 4))
        elements.append(left_box_table)
        elements.append(Spacer(1, 4))
        
        table = _final_exam_pdf_marks_table(
            course, semester, students, {}, teacher_role, available_width, blank=True,
        )
        elements.append(table)

        def _draw_blank_final_exam_pdf_footer(cnv, page_num, total_pages):
            pw, _ph = A4
            left_x = _bfe_lm
            right_x_end = pw - _bfe_rm
            sig_w = min(180, (right_x_end - left_x - 40) / 2.0)
            right_x = right_x_end - sig_w
            footer_y_line = 48
            footer_y_text = 34
            cnv.saveState()
            cnv.setLineWidth(1)
            cnv.setStrokeColor(colors.black)
            cnv.line(left_x, footer_y_line, left_x + sig_w, footer_y_line)
            cnv.line(right_x, footer_y_line, right_x_end, footer_y_line)
            cnv.setFont('Helvetica', 10)
            cnv.drawString(left_x, footer_y_text, 'Internal Examiner')
            cnv.drawRightString(right_x_end, footer_y_text, 'External Examiner')
            cnv.setFont('Helvetica', 9)
            cnv.drawCentredString(
                pw / 2.0, footer_y_text, _pdf_page_number_label(page_num, total_pages)
            )
            cnv.restoreState()

        _BlankFeFooterCanvas = _make_deferred_footer_canvas_class(_draw_blank_final_exam_pdf_footer)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=_bfe_rm,
            leftMargin=_bfe_lm,
            topMargin=_bfe_tm,
            bottomMargin=_bfe_bm,
        )
        doc.build(elements, canvasmaker=_BlankFeFooterCanvas)
        pdf_bytes = buffer.getvalue()

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"Blank_Final_Exam_Marks_{course.code}_{semester.name}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        return HttpResponse(f"Error generating PDF: {str(e)}", status=500)

@login_required
def export_final_exam_excel(request):
    """Export Final Exam marks to Excel (same header and table layout as PDF)."""
    try:
        if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_manage_final_marks')):
            messages.error(request, "You don't have permission to export Final Exam marks.")
            return redirect('ca-management')
        
        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        centre_id = request.GET.get('centre')
        teacher_role = request.GET.get('teacher_role', 'teacher1')
        
        if not semester_id or not course_id:
            messages.error(request, "Please select a semester and course.")
            return redirect('ca-management')
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        if course.is_lab and teacher_role == 'teacher3':
            teacher_role = 'teacher1'
        
        students = Student.objects.filter(semesters=semester).extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        students = filter_students_queryset_by_centre(students, centre_id)
        
        final_exam_marks = {
            m.student_id: m
            for m in FinalExamMark.objects.filter(
                student__in=students,
                course=course,
                semester=semester,
            )
        }

        if course.is_lab:
            header_rows = _final_exam_lab_table_header_rows(course, semester)
            lab_meta = _final_exam_lab_export_meta(course, semester)
        else:
            header_rows = _final_exam_theory_table_header_rows()
            lab_meta = None
        num_cols = len(header_rows[0])
        _, centre_name = _ca_marks_export_teacher_and_centre(semester, course, centre_id)
        examiner_name = _final_exam_export_examiner_name(semester, course, centre_id, teacher_role)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Semester Final Marks')

        title_format = workbook.add_format({
            'bold': True, 'font_size': 15, 'align': 'center', 'valign': 'vcenter',
        })
        subtitle_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'align': 'center', 'valign': 'vcenter',
        })
        normal_format = workbook.add_format({
            'font_size': 10, 'align': 'center', 'valign': 'vcenter',
        })
        header_format = workbook.add_format({
            'bold': True, 'font_size': 9, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'text_wrap': True,
        })
        cell_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 8,
        })
        cell_stripe_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 8,
            'bg_color': '#D3D3D3',
        })
        id_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 9, 'bold': True,
        })
        id_stripe_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 9, 'bold': True,
            'bg_color': '#D3D3D3',
        })
        name_format = workbook.add_format({
            'align': 'left', 'valign': 'vcenter', 'border': 1, 'font_size': 7, 'bold': True,
        })
        name_stripe_format = workbook.add_format({
            'align': 'left', 'valign': 'vcenter', 'border': 1, 'font_size': 7, 'bold': True,
            'bg_color': '#D3D3D3',
        })

        row = 0
        last_col = max(num_cols - 1, 0)
        worksheet.merge_range(
            row, 0, row, last_col,
            'B. Sc in Computer Science and Engineering Program',
            title_format,
        )
        row += 1
        session = semester.session or ''
        if session:
            worksheet.merge_range(row, 0, row, last_col, f'{session} Session', subtitle_format)
            row += 1
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            worksheet.merge_range(
                row, 0, row, last_col,
                f'{term} Term {semester_full_name}'.strip(),
                subtitle_format,
            )
            row += 1
        course_name_display = f'{course.code} - {course.name}'
        worksheet.merge_range(
            row, 0, row, last_col,
            f'Semester Final Marks - {course_name_display}',
            subtitle_format,
        )
        row += 1
        if examiner_name:
            worksheet.merge_range(
                row, 0, row, last_col, f'Examiner: {examiner_name}', normal_format,
            )
            row += 1
        if centre_name:
            worksheet.merge_range(
                row, 0, row, last_col, f'Study Center: {centre_name}', normal_format,
            )
            row += 1

        table_header_start = row
        row += len(header_rows)
        if course.is_lab:
            _final_exam_excel_apply_lab_header_merges(
                worksheet, table_header_start, header_format, header_rows,
                lab_meta['lab_final_uses_viva'],
            )
        else:
            _final_exam_excel_apply_theory_header_merges(
                worksheet, table_header_start, header_format, header_rows,
            )

        for sl_no, student in enumerate(students, start=1):
            stripe = sl_no % 2 == 0
            mark = final_exam_marks.get(student.id)
            if course.is_lab:
                data = _final_exam_build_lab_student_row(
                    sl_no, student, mark, teacher_role, course, semester,
                )
            else:
                data = _final_exam_build_theory_student_row(
                    sl_no, student, mark, teacher_role,
                )
            for col, value in enumerate(data):
                if col == 0:
                    fmt = cell_stripe_format if stripe else cell_format
                elif col == 1:
                    fmt = id_stripe_format if stripe else id_format
                elif col == 2:
                    fmt = name_stripe_format if stripe else name_format
                else:
                    fmt = cell_stripe_format if stripe else cell_format
                worksheet.write(row, col, value, fmt)
            row += 1

        worksheet.set_column(0, 0, 5)
        worksheet.set_column(1, 1, 12)
        worksheet.set_column(2, 2, 28)
        if num_cols > 3:
            worksheet.set_column(3, num_cols - 1, 8)
        for hr in range(len(header_rows)):
            worksheet.set_row(table_header_start + hr, 28)

        _excel_apply_portrait_a4_print_setup(worksheet, row - 1, last_col)

        workbook.close()
        output.seek(0)
        
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        filename = f'Final_Exam_Marks_{course.code}_{semester.name}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        return HttpResponse(f'Error generating Excel: {str(e)}', status=500)





def _is_ca_management_admin(request):
    """Same rule as ca_management `is_admin` (staff without a teacher profile, or superuser)."""
    teacher = getattr(request.user, 'teacher', None) if hasattr(request.user, 'teacher') else None
    return bool(request.user.is_superuser or (request.user.is_staff and not teacher))


def _lab_final_exam_cap_for_summary(course, semester):
    """Max lab final total label for summary exports (matches ca_management)."""
    if (
        course
        and course.is_lab
        and semester
        and getattr(semester, 'curriculum', None)
    ):
        if semester.curriculum.code == 'OLD':
            return 60
        return 25
    if semester and getattr(semester, 'curriculum', None) and semester.curriculum.code == 'OLD':
        return 60
    return 50


def _ca_marks_dict_for_students_course_semester(students, course, semester):
    """Same CA lookup as ca_management: DB rows plus temp CAMark with auto attendance."""
    ca_marks = {}
    existing_marks = CAMark.objects.filter(
        student__in=students,
        course=course,
        semester=semester,
    )
    for mark in existing_marks:
        mark.attendance_mark = mark.calculate_attendance_mark()
        ca_marks[mark.student_id] = mark
    for student in students:
        if student.id not in ca_marks:
            temp_mark = CAMark(
                student=student,
                course=course,
                semester=semester,
            )
            temp_mark.attendance_mark = temp_mark.calculate_attendance_mark()
            ca_marks[student.id] = temp_mark
    return ca_marks


def _fmt_export_mark(value, places=2):
    """Format a mark for PDF/Excel export; None (unset) exports as a blank cell."""
    if value is None:
        return ''
    try:
        num = float(value)
    except (TypeError, ValueError):
        return ''
    if places <= 0:
        return str(int(num))
    return f'{num:.{places}f}'


def _ca_total_float(cam):
    if not cam:
        return 0.0
    try:
        return float(cam.calculate_total_ca_mark() or 0)
    except (TypeError, ValueError):
        return 0.0


def _ca_total_ceil_int(cam):
    """Same rule as CA Marks tab Total CA column (ceil_int template filter)."""
    try:
        return int(math.ceil(max(0.0, _ca_total_float(cam))))
    except (TypeError, ValueError, OverflowError):
        return 0


def _excel_apply_landscape_a4_print_setup(worksheet, last_row, last_col):
    """Landscape A4 print setup: fit all columns to one page width (like PDF)."""
    worksheet.set_landscape()
    worksheet.set_paper(9)  # A4
    worksheet.set_margins(left=0.3, right=0.3, top=0.35, bottom=0.35)
    worksheet.center_horizontally()
    worksheet.fit_to_pages(1, 0)
    if last_row >= 0 and last_col >= 0:
        worksheet.print_area(0, 0, last_row, last_col)


def _excel_apply_portrait_a4_print_setup(worksheet, last_row, last_col):
    """Portrait A4 print setup: fit all columns to one page width (like PDF)."""
    worksheet.set_portrait()
    worksheet.set_paper(9)  # A4
    worksheet.set_margins(left=0.3, right=0.3, top=0.35, bottom=0.35)
    worksheet.center_horizontally()
    worksheet.fit_to_pages(1, 0)
    if last_row >= 0 and last_col >= 0:
        worksheet.print_area(0, 0, last_row, last_col)


def _ca_marks_export_teacher_and_centre(semester, course, centre_id):
    teacher_name = None
    centre_name = ''
    if centre_id:
        try:
            centre = Centre.objects.get(id=centre_id)
            centre_name = centre.name
            semester_course = SemesterCourse.objects.filter(
                semester=semester,
                course=course,
                centre=centre,
            ).select_related('teacher').first()
            if semester_course and semester_course.teacher:
                teacher_name = semester_course.teacher.name
        except (Centre.DoesNotExist, ValueError, TypeError):
            pass
    if not centre_name:
        first_sc = SemesterCourse.objects.filter(semester=semester).select_related('centre').first()
        if first_sc and first_sc.centre:
            centre_name = first_sc.centre.name
    return teacher_name, centre_name


def _ca_marks_export_table_header_rows(course, semester):
    """Multi-row CA table headers matching the PDF export."""
    if course.course_type == 'PROJECT':
        total_ca = (
            course.effective_project_supervisor_weight
            + course.effective_project_evaluation_weight
            + course.effective_project_presentation_weight
        )
        return [
            [
                'SL. No', 'Student ID', 'Name',
                f'Project Work CA (Total: {total_ca})', '', '',
                'Total',
            ],
            [
                '', '', '',
                f'Supervisor ({course.effective_project_supervisor_weight})',
                f'Evaluation ({course.effective_project_evaluation_weight})',
                f'Presentation ({course.effective_project_presentation_weight})',
                '',
            ],
        ]

    if course.is_lab:
        p2w = course.effective_lab_ca_practical2_weight
        if p2w:
            total_ca = course.effective_lab_ca_total_marks
            return [
                [
                    'SL. No', 'Student ID', 'Name',
                    f'Lab Course CA (Total: {total_ca})', '', '', '', '', '', '',
                    'Total',
                ],
                [
                    '', '', '',
                    f'Attendance ({course.effective_lab_ca_attendance_weight})',
                    f'Assignment/Lab Report ({course.effective_lab_ca_assignment_weight})', '', '', '',
                    f'Experiment/ Lab Project ({course.effective_lab_ca_practical_weight})',
                    f'Experiment/ Lab Project ({p2w})',
                    '',
                ],
                [
                    '', '', '', '',
                    'First', 'Second', 'Third', 'Average', '', '', '',
                ],
            ]
        total_ca = (
            course.effective_lab_ca_attendance_weight
            + course.effective_lab_ca_assignment_weight
            + course.effective_lab_ca_practical_weight
        )
        return [
            [
                'SL. No', 'Student ID', 'Name',
                f'Lab Course CA (Total: {total_ca})', '', '', '', '',
                '', 'Total',
            ],
            [
                '', '', '',
                f'Attendance ({course.effective_lab_ca_attendance_weight})',
                f'Assignment/Lab Report ({course.effective_lab_ca_assignment_weight})', '', '', '',
                f'Experiment/ Lab Project ({course.effective_lab_ca_practical_weight})',
                '',
            ],
            [
                '', '', '',
                '',
                'First', 'Second', 'Third', 'Average',
                '', '',
            ],
        ]

    is_old_curriculum = semester.curriculum and semester.curriculum.code == 'OLD'
    if is_old_curriculum:
        exam_weight = course.effective_ca_quiz_weight
        total_ca = course.effective_ca_attendance_weight + course.effective_ca_assignment_weight + exam_weight
        return [
            [
                'SL. No', 'Student ID', 'Name',
                f'Theory Course CA (Total: {total_ca})', '', '', '', '', '', '',
                '', 'Total',
            ],
            [
                '', '', '',
                f'Attendance ({course.effective_ca_attendance_weight})',
                f'Assignment/Presentation ({course.effective_ca_assignment_weight})', '', '', '',
                f'Class Test ({exam_weight})', '', '',
                'Total',
            ],
            [
                '', '', '',
                '',
                'First', 'Second', 'Third', 'Average',
                'First', 'Second', 'Best',
                'Total',
            ],
        ]

    exam_weight = course.effective_ca_midterm_weight
    total_ca = course.effective_ca_attendance_weight + course.effective_ca_assignment_weight + exam_weight
    return [
        [
            'SL. No', 'Student ID', 'Name',
            f'Theory Course CA (Total: {total_ca})', '', '', '', '',
            '', 'Total',
        ],
        [
            '', '', '',
            f'Attendance ({course.effective_ca_attendance_weight})',
            f'Assignment/Presentation ({course.effective_ca_assignment_weight})', '', '', '',
            f'Mid-Term Exam ({exam_weight})',
            'Total',
        ],
        [
            '', '', '',
            '',
            'First', 'Second', 'Third', 'Average',
            '', 'Total',
        ],
    ]


def _ca_marks_export_student_row(course, semester, sl_no, student, mark):
    """One CA marks data row matching the PDF export."""
    if mark:
        if course.course_type == 'PROJECT':
            return [
                str(sl_no), student.id, student.name.upper(),
                _fmt_export_mark(mark.project_supervisor_mark),
                _fmt_export_mark(mark.project_evaluation_mark),
                _fmt_export_mark(mark.project_presentation_mark),
                str(_ca_total_ceil_int(mark)),
            ]
        if course.is_lab:
            if course.effective_lab_ca_practical2_weight:
                return [
                    str(sl_no), student.id, student.name.upper(),
                    _fmt_export_mark(mark.attendance_mark),
                    _fmt_export_mark(mark.first_lab_assignment_mark),
                    _fmt_export_mark(mark.second_lab_assignment_mark),
                    _fmt_export_mark(mark.third_lab_assignment_mark),
                    _fmt_export_mark(mark.lab_assignment_mark),
                    _fmt_export_mark(mark.lab_practical_mark),
                    _fmt_export_mark(mark.second_lab_practical_mark),
                    str(_ca_total_ceil_int(mark)),
                ]
            return [
                str(sl_no), student.id, student.name.upper(),
                _fmt_export_mark(mark.attendance_mark),
                _fmt_export_mark(mark.first_lab_assignment_mark),
                _fmt_export_mark(mark.second_lab_assignment_mark),
                _fmt_export_mark(mark.third_lab_assignment_mark),
                _fmt_export_mark(mark.lab_assignment_mark),
                _fmt_export_mark(mark.lab_practical_mark),
                str(_ca_total_ceil_int(mark)),
            ]
        is_old_curriculum = semester.curriculum and semester.curriculum.code == 'OLD'
        if is_old_curriculum:
            return [
                str(sl_no), student.id, student.name.upper(),
                _fmt_export_mark(mark.attendance_mark),
                _fmt_export_mark(mark.first_assignment_mark),
                _fmt_export_mark(mark.second_assignment_mark),
                _fmt_export_mark(mark.third_assignment_mark),
                _fmt_export_mark(mark.assignment_mark),
                _fmt_export_mark(mark.first_class_test_mark),
                _fmt_export_mark(mark.second_class_test_mark),
                _fmt_export_mark(mark.class_test_mark),
                str(_ca_total_ceil_int(mark)),
            ]
        return [
            str(sl_no), student.id, student.name.upper(),
            _fmt_export_mark(mark.attendance_mark),
            _fmt_export_mark(mark.first_assignment_mark),
            _fmt_export_mark(mark.second_assignment_mark),
            _fmt_export_mark(mark.third_assignment_mark),
            _fmt_export_mark(mark.assignment_mark),
            _fmt_export_mark(mark.midterm_mark),
            str(_ca_total_ceil_int(mark)),
        ]

    if course.course_type == 'PROJECT':
        empty = [str(sl_no), student.id, student.name.upper(), '0.00', '0.00', '0.00', '0']
    elif course.is_lab:
        if course.effective_lab_ca_practical2_weight:
            empty = [str(sl_no), student.id, student.name.upper()] + ['0.00'] * 8 + ['0']
        else:
            empty = [str(sl_no), student.id, student.name.upper()] + ['0.00'] * 6 + ['0']
    elif semester.curriculum and semester.curriculum.code == 'OLD':
        empty = [str(sl_no), student.id, student.name.upper()] + ['0.00'] * 8 + ['0']
    else:
        empty = [str(sl_no), student.id, student.name.upper()] + ['0.00'] * 6 + ['0']
    return empty


def _ca_marks_export_apply_table_header_merges(
    worksheet, course, semester, start_row, header_fmt, header_rows
):
    """Apply merged header cells for the CA marks table (same layout as PDF)."""
    num_header_rows = len(header_rows)

    def cell_text(r, c):
        if r < len(header_rows) and c < len(header_rows[r]):
            return (header_rows[r][c] or '').replace('\n', ' ')
        return ''

    def merge(r1, c1, r2, c2):
        worksheet.merge_range(
            start_row + r1, c1, start_row + r2, c2, cell_text(r1, c1), header_fmt
        )

    def write(r, c):
        text = cell_text(r, c)
        if text:
            worksheet.write(start_row + r, c, text, header_fmt)

    last_row = num_header_rows - 1
    merge(0, 0, last_row, 0)
    merge(0, 1, last_row, 1)
    merge(0, 2, last_row, 2)

    if course.course_type == 'PROJECT':
        merge(0, 3, 0, 5)
        for c in range(3, 6):
            write(1, c)
        merge(0, 6, last_row, 6)
        return

    if course.is_lab:
        if course.effective_lab_ca_practical2_weight:
            merge(0, 3, 0, 9)
            merge(1, 3, last_row, 3)
            merge(1, 4, 1, 7)
            for c in range(4, 8):
                write(2, c)
            merge(1, 8, last_row, 8)
            merge(1, 9, last_row, 9)
            merge(0, 10, last_row, 10)
        else:
            merge(0, 3, 0, 8)
            merge(1, 3, last_row, 3)
            merge(1, 4, 1, 7)
            for c in range(4, 8):
                write(2, c)
            merge(1, 8, last_row, 8)
            merge(0, 9, last_row, 9)
        return

    is_old_curriculum = semester.curriculum and semester.curriculum.code == 'OLD'
    if is_old_curriculum:
        merge(0, 3, 0, 10)
        merge(1, 3, last_row, 3)
        merge(1, 4, 1, 7)
        for c in range(4, 8):
            write(2, c)
        merge(1, 8, 1, 10)
        for c in range(8, 11):
            write(2, c)
        merge(0, 11, last_row, 11)
    else:
        merge(0, 3, 0, 8)
        merge(1, 3, last_row, 3)
        merge(1, 4, 1, 7)
        for c in range(4, 8):
            write(2, c)
        merge(1, 8, last_row, 8)
        merge(0, 9, last_row, 9)


def _examiner_summary_headers_and_rows(
    students, course, semester, final_exam_marks, include_status=True, ca_marks=None
):
    """
    Build (headers, rows) for the Final Exam Summary tab — same figures as ca_management examiner_summary_rows.
    Each row is a list of values for Excel/PDF.
    When include_status is False (e.g. PDF export), the Status column is omitted.
    """
    if ca_marks is None:
        ca_marks = _ca_marks_dict_for_students_course_semester(students, course, semester)
    lab_cap = _lab_final_exam_cap_for_summary(course, semester)
    headers = []
    rows = []

    if course.is_lab:
        headers = [
            'SL. No',
            'Student ID',
            'Name',
            f'Internal (max {lab_cap})',
            f'External (max {lab_cap})',
            'Variation',
            'Final total',
            'Total CA',
            'Total',
        ]
        if include_status:
            headers.append('Status')
        for idx, student in enumerate(students, start=1):
            fm = final_exam_marks.get(student.id)
            cam = ca_marks.get(student.id)
            ca_ceil = _ca_total_ceil_int(cam)
            if fm and fm.exam_absent:
                row = [idx, student.id, student.name, 'AB', 'AB', 'AB', 'AB', ca_ceil, 'AB']
                if include_status:
                    row.append('AB')
                rows.append(row)
                continue
            t_int = float(fm.lab_examiner_split_total(1)) if fm else 0.0
            t_ext = float(fm.lab_examiner_split_total(2)) if fm else 0.0
            mo = float(fm.final_exam_total or 0) if fm else 0.0
            diff = abs(t_int - t_ext)
            tot = round(mo + ca_ceil, 2)
            row = [
                idx,
                student.id,
                student.name,
                round(t_int, 2),
                round(t_ext, 2),
                round(diff, 2),
                round(mo, 2),
                ca_ceil,
                tot,
            ]
            if include_status:
                row.append('OK')
            rows.append(row)
    else:
        headers = [
            'SL. No',
            'Student ID',
            'Name',
            'First examiner (70)',
            'Second examiner (70)',
            'Variation',
            'Third examiner (70)',
            'Final exam (70)',
            'Total CA',
            'Total',
        ]
        if include_status:
            headers.append('Status')
        for idx, student in enumerate(students, start=1):
            fm = final_exam_marks.get(student.id)
            cam = ca_marks.get(student.id)
            ca_ceil = _ca_total_ceil_int(cam)
            if not fm:
                row = [idx, student.id, student.name, '—', '—', '—', '—', '—', ca_ceil, '—']
                if include_status:
                    row.append('')
                rows.append(row)
                continue
            if fm.exam_absent:
                row = [
                    idx,
                    student.id,
                    student.name,
                    'AB',
                    'AB',
                    'AB',
                    'AB',
                    'AB',
                    ca_ceil,
                    'AB',
                ]
                if include_status:
                    row.append('AB')
                rows.append(row)
                continue
            t1 = float(fm.teacher1_total or 0)
            t2 = float(fm.teacher2_total or 0)
            t3 = float(fm.teacher3_total or 0)
            diff_abs = abs(t1 - t2)
            mo = float(fm.final_exam_total or 0)
            req_third = bool(fm.is_third_examiner_required)
            if req_third or t3 > 0:
                third_cell = round(t3, 2)
            else:
                third_cell = '—'
            if fm.is_third_examiner_required:
                status = 'Third Examiner Needed'
            else:
                status = 'OK'
            tot = round(mo + ca_ceil, 2)
            row = [
                idx,
                student.id,
                student.name,
                round(t1, 2),
                round(t2, 2),
                round(diff_abs, 2),
                third_cell,
                round(mo, 2),
                ca_ceil,
                tot,
            ]
            if include_status:
                row.append(status)
            rows.append(row)
    return headers, rows


def _examiner_summary_pdf_table_header_row(course, semester, hdr_style):
    """ReportLab Paragraph cells: label + max mark on separate lines (matches Semester Final PDF style)."""
    lab_cap = _lab_final_exam_cap_for_summary(course, semester)
    if course.is_lab:
        return [
            Paragraph('SL. No', hdr_style),
            Paragraph('Student ID', hdr_style),
            Paragraph('Name', hdr_style),
            Paragraph(f'Internal<br/>(max {lab_cap})', hdr_style),
            Paragraph(f'External<br/>(max {lab_cap})', hdr_style),
            Paragraph('Variation', hdr_style),
            Paragraph('Final total', hdr_style),
            Paragraph('Total CA', hdr_style),
            Paragraph('Total', hdr_style),
        ]
    return [
        Paragraph('SL. No', hdr_style),
        Paragraph('Student ID', hdr_style),
        Paragraph('Name', hdr_style),
        Paragraph('First examiner<br/>(70)', hdr_style),
        Paragraph('Second examiner<br/>(70)', hdr_style),
        Paragraph('Variation', hdr_style),
        Paragraph('Third examiner<br/>(70)', hdr_style),
        Paragraph('Final exam<br/>(70)', hdr_style),
        Paragraph('Total CA', hdr_style),
        Paragraph('Total', hdr_style),
    ]


@login_required
def export_final_exam_summary_excel(request):
    """Export Final Exam Summary to Excel (same header and table layout as PDF)."""
    try:
        if not _is_ca_management_admin(request):
            messages.error(request, "You don't have permission to export the Final Exam Summary.")
            return redirect('ca-management')

        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        centre_id = request.GET.get('centre')

        if not semester_id or not course_id:
            messages.error(request, 'Please select a semester and course.')
            return redirect('ca-management')

        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)

        students = Student.objects.filter(semesters=semester).extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)",
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        students = filter_students_queryset_by_centre(students, centre_id)

        final_exam_marks = {
            m.student_id: m
            for m in FinalExamMark.objects.filter(
                student__in=students,
                course=course,
                semester=semester,
            )
        }

        headers, data_rows = _examiner_summary_headers_and_rows(
            list(students), course, semester, final_exam_marks, include_status=False,
        )
        num_cols = len(headers)
        _, centre_name = _ca_marks_export_teacher_and_centre(semester, course, centre_id)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Final Exam Summary')

        title_format = workbook.add_format({
            'bold': True, 'font_size': 15, 'align': 'center', 'valign': 'vcenter',
        })
        subtitle_format = workbook.add_format({
            'bold': True, 'font_size': 11, 'align': 'center', 'valign': 'vcenter',
        })
        normal_format = workbook.add_format({
            'font_size': 10, 'align': 'center', 'valign': 'vcenter',
        })
        header_format = workbook.add_format({
            'bold': True, 'font_size': 9, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'text_wrap': True,
        })
        cell_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 8,
        })
        cell_stripe_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 8,
            'bg_color': '#D3D3D3',
        })
        id_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 9, 'bold': True,
        })
        id_stripe_format = workbook.add_format({
            'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 9, 'bold': True,
            'bg_color': '#D3D3D3',
        })
        name_format = workbook.add_format({
            'align': 'left', 'valign': 'vcenter', 'border': 1, 'font_size': 7, 'bold': True,
        })
        name_stripe_format = workbook.add_format({
            'align': 'left', 'valign': 'vcenter', 'border': 1, 'font_size': 7, 'bold': True,
            'bg_color': '#D3D3D3',
        })

        row = 0
        last_col = max(num_cols - 1, 0)
        worksheet.merge_range(
            row, 0, row, last_col,
            'B. Sc in Computer Science and Engineering Program',
            title_format,
        )
        row += 1
        session = semester.session or ''
        if session:
            worksheet.merge_range(row, 0, row, last_col, f'{session} Session', subtitle_format)
            row += 1
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            worksheet.merge_range(
                row, 0, row, last_col,
                f'{term} Term {semester_full_name}'.strip(),
                subtitle_format,
            )
            row += 1
        course_name_display = f'{course.code} - {course.name}'
        worksheet.merge_range(
            row, 0, row, last_col,
            f'Final Exam Summary - {course_name_display}',
            subtitle_format,
        )
        row += 1
        if centre_name:
            worksheet.merge_range(
                row, 0, row, last_col, f'Study Center: {centre_name}', normal_format,
            )
            row += 1

        table_header_start = row
        for col, label in enumerate(headers):
            worksheet.write(row, col, label, header_format)
        row += 1
        worksheet.set_row(table_header_start, 28)

        for data_row in data_rows:
            sl_no = data_row[0]
            stripe = isinstance(sl_no, int) and sl_no % 2 == 0
            for col, val in enumerate(data_row):
                if col == 2 and isinstance(val, str):
                    val = val.upper()
                if col == 0:
                    fmt = cell_stripe_format if stripe else cell_format
                elif col == 1:
                    fmt = id_stripe_format if stripe else id_format
                elif col == 2:
                    fmt = name_stripe_format if stripe else name_format
                else:
                    fmt = cell_stripe_format if stripe else cell_format
                worksheet.write(row, col, val, fmt)
            row += 1

        worksheet.set_column(0, 0, 6)
        worksheet.set_column(1, 1, 12)
        worksheet.set_column(2, 2, 22)
        if num_cols > 3:
            worksheet.set_column(3, num_cols - 1, 9)

        _excel_apply_landscape_a4_print_setup(worksheet, row - 1, last_col)

        workbook.close()
        output.seek(0)

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        fname = f'Final_Exam_Summary_{course.code}_{semester.name}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response

    except Exception as e:
        return HttpResponse(f'Error generating Excel: {str(e)}', status=500)


@login_required
def export_final_exam_summary_pdf(request):
    """
    Export Final Exam Summary (admin consolidated view) to PDF.
    Matches Semester Final Marks PDF layout (banner, study center, table borders,
    chairman signature + page numbers) but omits the Examiner line.
    """
    try:
        if not _is_ca_management_admin(request):
            messages.error(request, "You don't have permission to export the Final Exam Summary.")
            return redirect('ca-management')

        semester_id = request.GET.get('semester')
        course_id = request.GET.get('course')
        centre_id = request.GET.get('centre')

        if not semester_id or not course_id:
            messages.error(request, 'Please select a semester and course.')
            return redirect('ca-management')

        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)

        centre_name = ''
        if centre_id:
            try:
                centre_name = Centre.objects.get(id=int(centre_id)).name
            except (Centre.DoesNotExist, ValueError, TypeError):
                pass

        students = Student.objects.filter(semesters=semester).extra(
            select={
                'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)",
            }
        ).order_by('-first_two_digits', 'last_three_digits')
        students = filter_students_queryset_by_centre(students, centre_id)

        existing_marks = FinalExamMark.objects.filter(
            student__in=students,
            course=course,
            semester=semester,
        )
        final_exam_marks = {m.student_id: m for m in existing_marks}

        headers, data_rows = _examiner_summary_headers_and_rows(
            list(students), course, semester, final_exam_marks, include_status=False
        )

        _fes_lm = 54
        _fes_rm = 54
        _fes_tm = 34
        _fes_bm = 90
        page_width, _page_height = landscape(A4)
        available_width = page_width - _fes_lm - _fes_rm

        elements = []

        header_img_path = 'bou_routines_app/static/pdf_routine_top.png'
        try:
            padding_for_image = 2
            img_obj = Image(
                header_img_path,
                width=available_width - (2 * padding_for_image),
                height=45,
            )
            header_img_table = Table([[img_obj]], colWidths=[available_width])
            header_img_table.setStyle(
                TableStyle(
                    [
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), padding_for_image),
                        ('RIGHTPADDING', (0, 0), (-1, -1), padding_for_image),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ]
                )
            )
            elements.append(header_img_table)
        except Exception:
            pass
        elements.append(Spacer(1, -4))

        if not centre_name:
            first_sc = SemesterCourse.objects.filter(semester=semester).select_related('centre').first()
            if first_sc and first_sc.centre:
                centre_name = first_sc.centre.name

        header_style = ParagraphStyle(
            'FESumHeaderStyle',
            fontName='Helvetica-Bold',
            fontSize=15,
            alignment=1,
            leading=18,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_small = ParagraphStyle(
            'FESumHeaderStyleSmall',
            fontName='Helvetica-Bold',
            fontSize=11,
            alignment=1,
            leading=14,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_normal = ParagraphStyle(
            'FESumHeaderStyleNormal',
            fontName='Helvetica',
            fontSize=10,
            alignment=1,
            leading=11,
            spaceAfter=0,
            spaceBefore=0,
        )
        header_style_bold = ParagraphStyle(
            'FESumHeaderStyleBold',
            fontName='Helvetica-Bold',
            fontSize=12,
            alignment=1,
            leading=15,
            spaceAfter=0,
            spaceBefore=0,
        )

        left_content = []
        program_name = 'B. Sc in Computer Science and Engineering Program'
        left_content.append(Paragraph(program_name, header_style))
        session = semester.session or ''
        if session:
            left_content.append(Paragraph(f'{session} Session', header_style_small))
        term = semester.term or ''
        semester_full_name = semester.semester_full_name or ''
        if term or semester_full_name:
            combined = f'{term} Term {semester_full_name}'.strip()
            left_content.append(Paragraph(combined, header_style_small))
        left_content.append(Spacer(1, 2))
        course_name_display = f'{course.code} - {course.name}' if course else 'Course'
        left_content.append(
            Paragraph(f'Final Exam Summary - {course_name_display}', header_style_bold)
        )
        if centre_name:
            left_content.append(
                Paragraph(f'<b>Study Center:</b> {centre_name}', header_style_normal)
            )

        left_box_table = Table(
            [[left_content]],
            colWidths=[available_width],
            hAlign='CENTER',
            style=TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]),
        )
        elements.append(Spacer(1, 4))
        elements.append(left_box_table)
        elements.append(Spacer(1, 4))

        hdr_tbl_style = ParagraphStyle(
            'FESumTblHdr',
            fontName='Helvetica-Bold',
            fontSize=9,
            alignment=TA_CENTER,
            leading=11,
            spaceBefore=0,
            spaceAfter=0,
        )
        pdf_header_row = _examiner_summary_pdf_table_header_row(course, semester, hdr_tbl_style)

        table_data = [pdf_header_row]
        for r in data_rows:
            row = [str(c) for c in r]
            if len(row) > 2:
                row[2] = str(row[2]).upper()
            table_data.append(row)

        num_cols = len(headers)
        if course.is_lab:
            sl_w, id_w, name_w = 40, 80, 150
            rest = max(40.0, available_width - sl_w - id_w - name_w)
            u = rest / 6.0
            col_widths = [sl_w, id_w, name_w, u, u, u, u, u, u]
        else:
            sl_w, id_w, name_w = 40, 80, 150
            rest = max(40.0, available_width - sl_w - id_w - name_w)
            u = rest / 7.0
            col_widths = [sl_w, id_w, name_w, u, u, u, u, u, u, u]

        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('TOPPADDING', (0, 0), (-1, 0), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('FONTSIZE', (1, 1), (1, -1), 9),
                    ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),
                    ('ALIGN', (2, 0), (2, -1), 'LEFT'),
                ]
            )
        )
        elements.append(tbl)

        def _draw_final_exam_summary_pdf_footer(cnv, page_num, total_pages):
            pw, _ph = landscape(A4)
            left_x = _fes_lm
            footer_y_line = 48
            footer_y_text = 34
            sig_line_width = 280
            cnv.saveState()
            cnv.setLineWidth(1)
            cnv.setStrokeColor(colors.black)
            cnv.line(left_x, footer_y_line, left_x + sig_line_width, footer_y_line)
            cnv.setFont('Helvetica', 10)
            cnv.drawString(left_x, footer_y_text, 'Chairman of the Examination Committee')
            cnv.setFont('Helvetica', 9)
            cnv.drawRightString(
                pw - _fes_rm, footer_y_text, _pdf_page_number_label(page_num, total_pages)
            )
            cnv.restoreState()

        _FesFooterCanvas = _make_deferred_footer_canvas_class(_draw_final_exam_summary_pdf_footer)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=_fes_rm,
            leftMargin=_fes_lm,
            topMargin=_fes_tm,
            bottomMargin=_fes_bm,
        )
        doc.build(elements, canvasmaker=_FesFooterCanvas)
        pdf_bytes = buffer.getvalue()

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        fname = f'Final_Exam_Summary_{course.code}_{semester.name}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response

    except Exception as e:
        return HttpResponse(f'Error generating PDF: {str(e)}', status=500)


# Teacher Registration Views

@login_required
def teacher_register(request):
    """Teacher registration form - Admin only"""
    # Only allow administrators to access registration
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, 'Only administrators can register new teachers. Please contact an administrator.')
        return redirect('admin:index')
    
    if request.method == 'POST':
        form = TeacherRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}. The teacher can now login!')
            return redirect('admin:bou_routines_app_teacher_changelist')
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
@never_cache
def ca_management(request):
    """
    CA (Continuous Assessment) management page
    Similar to attendance calendar but for CA marks
    """
    # Check permissions
    if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_manage_ca')):
        messages.error(request, "You don't have permission to manage CA marks.")
        return redirect('teacher-dashboard')
    
    # Marks page is new-curriculum only; never expose curriculum in the URL
    if request.method == 'GET' and 'curriculum' in request.GET:
        q = request.GET.copy()
        q.pop('curriculum', None)
        target = reverse('ca-management')
        if q:
            target = f'{target}?{q.urlencode()}'
        return redirect(target)
    
    # Get teacher profile
    teacher = None
    if hasattr(request.user, 'teacher'):
        teacher = request.user.teacher
    elif request.user.is_superuser or request.user.is_staff:
        teacher = None  # Admin can manage all courses
    
    # Get all curricula
    curricula = Curriculum.objects.filter(is_active=True).order_by('name')
    
    # Get all centres
    centres = Centre.objects.filter(is_active=True).order_by('name')
    
    # Curriculum is not read from GET (URL); POST may send hidden field (coerce OLD away)
    selected_curriculum_id = request.POST.get('curriculum')
    selected_curriculum = None
    
    if selected_curriculum_id:
        try:
            selected_curriculum_id = int(selected_curriculum_id)
            selected_curriculum = Curriculum.objects.get(id=selected_curriculum_id)
            if selected_curriculum.code == 'OLD':
                selected_curriculum = None
                selected_curriculum_id = None
        except (Curriculum.DoesNotExist, ValueError, TypeError):
            selected_curriculum = None
            selected_curriculum_id = None
    
    if not selected_curriculum and curricula.exists():
        selected_curriculum, selected_curriculum_id = _default_new_curriculum(curricula)
    
    # Get selected centre from request
    selected_centre_id = request.GET.get('centre') or request.POST.get('centre')
    selected_centre = None
    
    if selected_centre_id:
        try:
            selected_centre_id = int(selected_centre_id)
            selected_centre = Centre.objects.get(id=selected_centre_id)
        except (Centre.DoesNotExist, ValueError):
            selected_centre = None
            selected_centre_id = None
    
    # If no centre selected, default to DRC BEFORE filtering semesters
    if not selected_centre:
        try:
            selected_centre = Centre.objects.get(code='DRC')
            selected_centre_id = selected_centre.id
        except Centre.DoesNotExist:
            selected_centre = None
            selected_centre_id = None

    # Default marks semester: Y1S1 (new curriculum); term/session are taken from that row, not hard-coded
    marks_default_semester_id = None
    if selected_curriculum:
        _y1_default = (
            Semester.objects.filter(curriculum=selected_curriculum, name='Y1S1')
            .order_by('order', 'id')
            .first()
        )
        if _y1_default:
            marks_default_semester_id = _y1_default.id
        if marks_default_semester_id is None:
            _first_any = (
                Semester.objects.filter(curriculum=selected_curriculum)
                .order_by('order', 'id')
                .first()
            )
            if _first_any:
                marks_default_semester_id = _first_any.id

    raw_semester_for_filter = request.GET.get('semester') or request.POST.get('semester')
    early_semester_id = None
    if raw_semester_for_filter:
        try:
            early_semester_id = int(raw_semester_for_filter)
        except (ValueError, TypeError):
            early_semester_id = None

    selected_term = (request.GET.get('term') or request.POST.get('term') or '').strip()
    selected_session = (request.GET.get('session') or request.POST.get('session') or '').strip()

    _term_session_source_id = early_semester_id
    if (
        _term_session_source_id is None
        and request.method == 'GET'
        and 'semester' not in request.GET
        and marks_default_semester_id
    ):
        _term_session_source_id = marks_default_semester_id

    if _term_session_source_id and selected_curriculum:
        try:
            _es = Semester.objects.get(id=_term_session_source_id, curriculum=selected_curriculum)
            if 'term' not in request.GET and 'term' not in request.POST:
                if 'semester' in request.GET or 'semester' in request.POST:
                    selected_term = (_es.term or '').strip()
                else:
                    selected_term = _pick_default_term_for_curriculum(
                        selected_curriculum
                    ) or (_es.term or '').strip()
        except Semester.DoesNotExist:
            pass

    if (
        selected_curriculum
        and not (selected_term or '').strip()
        and 'term' not in request.GET
        and 'term' not in request.POST
        and 'semester' not in request.GET
        and 'semester' not in request.POST
    ):
        picked = _pick_default_term_for_curriculum(selected_curriculum)
        if picked:
            selected_term = picked

    term_choices = []
    if selected_curriculum:
        _semester_base = Semester.objects.filter(curriculum=selected_curriculum)
        term_choices = sorted(
            {
                (t or '').strip()
                for t in _semester_base.exclude(term__isnull=True).exclude(term='').values_list('term', flat=True)
            },
            key=lambda x: (x.lower(), x),
        )
        semesters_qs = _semester_base.order_by('order', 'name')
        if selected_term:
            semesters_qs = semesters_qs.filter(term=selected_term)
        semester_list = list(semesters_qs)
        if (
            marks_default_semester_id
            and not any(s.id == marks_default_semester_id for s in semester_list)
        ):
            try:
                _orph_y1 = Semester.objects.get(
                    id=marks_default_semester_id, curriculum=selected_curriculum
                )
                semester_list.append(_orph_y1)
                semester_list.sort(key=lambda s: (s.order, s.name))
            except Semester.DoesNotExist:
                pass
        if early_semester_id:
            try:
                orphan = Semester.objects.get(id=early_semester_id, curriculum=selected_curriculum)
                if not any(s.id == orphan.id for s in semester_list):
                    semester_list.append(orphan)
                    semester_list.sort(key=lambda s: (s.order, s.name))
            except Semester.DoesNotExist:
                pass
        semesters = semester_list
    else:
        term_choices = []
        semesters = []

    default_semester_id_for_filter = marks_default_semester_id
    if selected_curriculum and semesters:
        if (
            request.method == 'GET'
            and 'semester' not in request.GET
            and selected_term
        ):
            sid = _first_semester_id_matching_term(semesters, selected_term)
            if sid is not None:
                default_semester_id_for_filter = sid
    
    # Get semester and course from request
    semester_id = request.GET.get('semester') or request.POST.get('semester')
    course_id = request.GET.get('course') or request.POST.get('course')
    
    # Convert to integers if provided
    if semester_id:
        try:
            semester_id = int(semester_id)
        except (ValueError, TypeError):
            semester_id = None
    
    if course_id:
        try:
            course_id = int(course_id)
        except (ValueError, TypeError):
            course_id = None

    if semester_id:
        try:
            _sem_chk = Semester.objects.select_related('curriculum').get(pk=semester_id)
            if _sem_chk.curriculum and _sem_chk.curriculum.code == 'OLD':
                semester_id = None
                course_id = None
                messages.warning(
                    request,
                    'Marks use new curriculum only; old-curriculum semesters are not available here.',
                )
        except Semester.DoesNotExist:
            pass

    if (
        semester_id is None
        and default_semester_id_for_filter is not None
        and request.method == 'GET'
        and 'semester' not in request.GET
    ):
        semester_id = default_semester_id_for_filter

    session_choices = _student_session_choices_for_semester(
        semester_id,
        selected_centre_id if selected_centre_id else None,
    )
    
    # Initialize selected semester and course objects
    selected_semester = None
    selected_course = None
    
    # Get courses for the selected semester
    courses_queryset = Course.objects.none()
    if semester_id:
        if teacher:
            # Course teachers and assigned final-exam examiners (same scope as get_courses_for_semester for_marks)
            sc_qs = SemesterCourse.objects.filter(
                semester_id=semester_id,
                course_id__in=_teacher_marks_accessible_course_ids(teacher, semester_id),
            )
            if selected_centre_id:
                sc_qs = sc_qs.filter(centre_id=selected_centre_id)
            courses_queryset = Course.objects.filter(
                id__in=sc_qs.values_list('course_id', flat=True).distinct()
            )
        else:
            # Admin users can see all courses in the selected semester
            courses_queryset = Course.objects.filter(
                semestercourse__semester_id=semester_id
            ).distinct()
            if selected_centre_id:
                courses_queryset = courses_queryset.filter(
                    semestercourse__centre_id=selected_centre_id
                ).distinct()
    
    # Get students for the selected course and semester
    students = Student.objects.none()
    ca_marks = {}
    final_exam_marks = {}
    midterm_marks = {}
    lab_chairman_obj = None
    if semester_id and course_id:
        try:
            selected_semester = Semester.objects.get(id=semester_id)
            # Get the course from SemesterCourse to ensure we get the correct course
            # for this specific semester (which is already filtered by centre)
            # Get centre from request for filtering SemesterCourse
            centre_id = request.GET.get('centre') or request.POST.get('centre')
            semester_course = None
            if centre_id:
                try:
                    centre = Centre.objects.get(id=centre_id)
                    semester_course = SemesterCourse.objects.filter(
                        semester=selected_semester,
                        course_id=course_id,
                        centre=centre
                    ).select_related(
                        'course',
                        'teacher',
                        'teacher__centre',
                        'lab_examination_chairman',
                    ).first()
                except Centre.DoesNotExist:
                    pass
            
            # Fallback: get any SemesterCourse for this semester and course if centre not provided
            if not semester_course:
                semester_course = SemesterCourse.objects.filter(
                    semester=selected_semester,
                    course_id=course_id
                ).select_related(
                    'course',
                    'teacher',
                    'teacher__centre',
                    'lab_examination_chairman',
                ).first()
            
            if semester_course:
                selected_course = semester_course.course
                # Use semester-specific teacher
                course_teacher = semester_course.teacher
                if semester_course.lab_examination_chairman_id:
                    lab_chairman_obj = semester_course.lab_examination_chairman
            else:
                # Fallback to direct course lookup if SemesterCourse not found
                selected_course = Course.objects.get(id=course_id)
                course_teacher = None  # No teacher if SemesterCourse doesn't exist
            
            # Get students enrolled in this semester with custom sorting
            # Sort by first two digits (descending), then last three digits (ascending)
            students = Student.objects.filter(semesters=selected_semester).extra(
                select={
                    'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
                    'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)"
                }
            ).order_by('-first_two_digits', 'last_three_digits')
            if selected_centre:
                students = students.filter(centre=selected_centre)
            if (selected_session or '').strip():
                students = students.filter(session=(selected_session or '').strip())

            ca_marks = _ca_marks_dict_for_students_course_semester(
                students, selected_course, selected_semester
            )

            # Get existing Final Exam marks for these students
            existing_final_marks = FinalExamMark.objects.filter(
                student__in=students,
                course=selected_course,
                semester=selected_semester
            )
            
            # Create a dictionary for easy lookup
            for mark in existing_final_marks:
                final_exam_marks[mark.student.id] = mark

            existing_midterm_marks = MidtermExamMark.objects.filter(
                student__in=students,
                course=selected_course,
                semester=selected_semester,
            )
            for mark in existing_midterm_marks:
                midterm_marks[mark.student.id] = mark

        except (Semester.DoesNotExist, Course.DoesNotExist):
            messages.error(request, "Invalid semester or course selected.")
    
    # Determine teacher role based on user type
    # Users with teacher profile are always treated as teachers, even if is_staff=True
    is_admin = request.user.is_superuser or (request.user.is_staff and not teacher)
    teacher_role = None
    can_select_evaluator = False
    
    if is_admin:
        # Administrators can select any evaluator
        teacher_role = request.GET.get('teacher_role', 'teacher1')
        if teacher_role not in ['teacher1', 'teacher2', 'teacher3']:
            teacher_role = 'teacher1'
        can_select_evaluator = True
    elif teacher:
        # Teachers can only see their own role
        # Check which evaluator role this teacher has for this course/semester
        if semester_id and course_id:
            try:
                semester = Semester.objects.get(id=semester_id)
                course = Course.objects.get(id=course_id)
                
                # Evaluator role: SemesterCourse (canonical), then FinalExamMark (legacy)
                centre_for_sample = request.GET.get('centre') or request.POST.get('centre')
                if centre_for_sample:
                    try:
                        centre_obj = Centre.objects.get(id=int(centre_for_sample))
                        sc_role = SemesterCourse.objects.filter(
                            semester=semester, course=course, centre=centre_obj
                        ).first()
                        if sc_role:
                            if sc_role.final_exam_evaluator1_id == teacher.id:
                                teacher_role = 'teacher1'
                            elif sc_role.final_exam_evaluator2_id == teacher.id:
                                teacher_role = 'teacher2'
                            elif sc_role.final_exam_evaluator3_id == teacher.id:
                                teacher_role = 'teacher3'
                    except (Centre.DoesNotExist, ValueError, TypeError):
                        pass

                sample_mark = final_exam_mark_sample_for_scope(course, semester, centre_for_sample)

                if not teacher_role and sample_mark:
                    if sample_mark.teacher1_evaluator == teacher:
                        teacher_role = 'teacher1'
                    elif sample_mark.teacher2_evaluator == teacher:
                        teacher_role = 'teacher2'
                    elif sample_mark.teacher3_evaluator == teacher:
                        teacher_role = 'teacher3'
                
                # If not found in existing marks, determine role based on teacher's centre
                # Teacher 1 is from DRC, Teacher 2 is from DUET (for the same course)
                if not teacher_role:
                    if teacher.centre.code == 'DRC':
                        teacher_role = 'teacher1'
                    elif teacher.centre.code == 'DUET':
                        teacher_role = 'teacher2'
                    else:
                        # Default: if teacher is the course teacher, assign based on centre
                        # Otherwise, default to teacher1
                        teacher_role = 'teacher1'
                    
            except (Semester.DoesNotExist, Course.DoesNotExist):
                teacher_role = 'teacher1'
        else:
            teacher_role = 'teacher1'
        can_select_evaluator = False
    else:
        # Default for other users
        teacher_role = 'teacher1'
        can_select_evaluator = False
    
    # Lab final: OLD = single field max 60; new curriculum = problem 20 + viva 5 (25 total in UI)
    lab_final_exam_max = 50
    lab_final_uses_viva = False
    lab_final_problem_solving_max = 50
    lab_final_viva_max = 0
    if (
        selected_course
        and selected_course.is_lab
        and selected_semester
        and getattr(selected_semester, 'curriculum', None)
    ):
        if selected_semester.curriculum.code == 'OLD':
            lab_final_exam_max = 60
        else:
            lab_final_exam_max = 25
            lab_final_uses_viva = True
            lab_final_problem_solving_max = 20
            lab_final_viva_max = 5
    elif selected_semester and getattr(selected_semester, 'curriculum', None) and selected_semester.curriculum.code == 'OLD':
        lab_final_exam_max = 60

    show_midterm_marks_tab = bool(
        semester_id
        and course_id
        and selected_semester
        and selected_course
        and not getattr(selected_course, 'is_lab', False)
        and getattr(selected_course, 'course_type', None) != 'PROJECT'
        and getattr(selected_semester, 'curriculum', None)
        and selected_semester.curriculum.code != 'OLD'
    )

    # Examiner-only (not the course teacher): CA / Mid-Term hidden; Semester Final only.
    # Course teacher (with or without examiner role) and admins keep CA / Mid-Term.
    can_edit_ca_and_midterm = bool(is_admin)
    if not can_edit_ca_and_midterm and teacher and selected_semester and selected_course:
        can_edit_ca_and_midterm = _is_course_teacher_for_scope(
            teacher, selected_semester, selected_course, selected_centre_id,
        )
    show_ca_marks_tab = bool(can_edit_ca_and_midterm and semester_id and course_id and students)
    if not can_edit_ca_and_midterm:
        show_midterm_marks_tab = False

    if course_id:
        try:
            _c_sel = Course.objects.get(id=int(course_id))
            if _c_sel.is_lab and teacher_role == 'teacher3':
                teacher_role = 'teacher1'
        except (Course.DoesNotExist, ValueError, TypeError):
            pass

    context = {
        'teacher': teacher,
        'is_admin': is_admin,
        'curricula': curricula,
        'selected_curriculum_id': selected_curriculum_id,
        'selected_curriculum': selected_curriculum,
        'centres': centres,
        'selected_centre': selected_centre,
        'selected_centre_id': selected_centre_id,
        'semesters': semesters,
        'term_choices': term_choices,
        'session_choices': session_choices,
        'selected_term': selected_term,
        'selected_session': selected_session,
        'courses': courses_queryset.order_by('code'),
        'selected_semester_id': semester_id,
        'selected_course_id': course_id,
        'selected_semester': selected_semester,
        'selected_course': selected_course,
        'students': students,
        'ca_marks': ca_marks,
        'final_exam_marks': final_exam_marks,
        'midterm_marks': midterm_marks,
        'teacher_role': teacher_role,
        'can_select_evaluator': can_select_evaluator,
        'can_select_chairman': can_select_evaluator and lab_final_uses_viva,
        'lab_final_exam_max': lab_final_exam_max,
        'lab_final_uses_viva': lab_final_uses_viva,
        'lab_final_problem_solving_max': lab_final_problem_solving_max,
        'lab_final_viva_max': lab_final_viva_max,
        'can_edit_lab_viva': lab_final_uses_viva and (
            is_admin
            or _user_can_edit_lab_viva(
                request.user,
                teacher=teacher,
                semester=selected_semester,
                course=selected_course,
                centre=selected_centre,
            )
        ),
        'show_midterm_marks_tab': show_midterm_marks_tab,
        'show_ca_marks_tab': show_ca_marks_tab,
        'can_edit_ca_and_midterm': can_edit_ca_and_midterm,
        'midterm_set_max': MidtermExamMark.SET_MARKS_MAX,
        'midterm_raw_total_max': MidtermExamMark.RAW_TOTAL_MAX,
    }
    
    # Get evaluator teachers for the selected course
    teacher1_evaluator_obj = None
    teacher2_evaluator_obj = None
    teacher3_evaluator_obj = None
    
    if semester_id and course_id:
        try:
            semester = Semester.objects.get(id=semester_id)
            # Get the course from SemesterCourse to ensure we get the correct course
            # for this specific semester (which is already filtered by centre)
            # Get centre from request for filtering SemesterCourse
            centre_id = request.GET.get('centre') or request.POST.get('centre')
            semester_course = None
            if centre_id:
                try:
                    centre = Centre.objects.get(id=centre_id)
                    semester_course = SemesterCourse.objects.filter(
                        semester=semester,
                        course_id=course_id,
                        centre=centre
                    ).select_related('course', 'teacher', 'teacher__centre').first()
                except Centre.DoesNotExist:
                    pass
            
            # Fallback: get any SemesterCourse for this semester and course if centre not provided
            if not semester_course:
                semester_course = SemesterCourse.objects.filter(
                    semester=semester,
                    course_id=course_id
                ).select_related('course', 'teacher', 'teacher__centre').first()
            
            if semester_course:
                course = semester_course.course
                # Use semester-specific teacher
                course_teacher = semester_course.teacher
            else:
                # Fallback to direct course lookup if SemesterCourse not found
                course = Course.objects.get(id=course_id)
                course_teacher = None  # No teacher if SemesterCourse doesn't exist
            
            context['selected_semester'] = semester
            context['selected_course'] = course
            # Add effective teacher to context for template use
            context['course_teacher'] = course_teacher
            
            # Examiners: SemesterCourse.final_exam_evaluator1–3 (canonical), then FinalExamMark.
            # Do not invent UI defaults from course teachers — empty until explicitly assigned.
            centre_for_evaluators = centre_id or selected_centre_id
            if centre_for_evaluators:
                try:
                    cev = Centre.objects.get(id=int(centre_for_evaluators))
                    sc_ev = SemesterCourse.objects.filter(
                        semester=semester, course=course, centre=cev
                    ).select_related(
                        'final_exam_evaluator1',
                        'final_exam_evaluator2',
                        'final_exam_evaluator3',
                        'lab_examination_chairman',
                    ).first()
                    if sc_ev:
                        if sc_ev.final_exam_evaluator1:
                            teacher1_evaluator_obj = sc_ev.final_exam_evaluator1
                        if sc_ev.final_exam_evaluator2:
                            teacher2_evaluator_obj = sc_ev.final_exam_evaluator2
                        if sc_ev.final_exam_evaluator3:
                            teacher3_evaluator_obj = sc_ev.final_exam_evaluator3
                        if sc_ev.lab_examination_chairman:
                            lab_chairman_obj = sc_ev.lab_examination_chairman
                except (Centre.DoesNotExist, ValueError, TypeError):
                    pass

            sample_mark = final_exam_mark_sample_for_scope(course, semester, centre_for_evaluators)

            if sample_mark:
                if not teacher1_evaluator_obj and sample_mark.teacher1_evaluator:
                    teacher1_evaluator_obj = sample_mark.teacher1_evaluator
                if not teacher2_evaluator_obj and sample_mark.teacher2_evaluator:
                    teacher2_evaluator_obj = sample_mark.teacher2_evaluator
                if not teacher3_evaluator_obj and sample_mark.teacher3_evaluator:
                    teacher3_evaluator_obj = sample_mark.teacher3_evaluator

            # No UI defaults for First/Second/Third — show empty "Search for a teacher..."
            # until an examiner is explicitly assigned (SemesterCourse / FinalExamMark above).
            
        except (Semester.DoesNotExist, Course.DoesNotExist):
            pass
    
    context['teacher1_evaluator'] = teacher1_evaluator_obj
    context['teacher2_evaluator'] = teacher2_evaluator_obj
    context['teacher3_evaluator'] = teacher3_evaluator_obj
    context['lab_chairman'] = lab_chairman_obj
    
    # Check if current teacher is assigned as an evaluator for this course/semester
    # Admin users can always see the tab
    show_final_exam_tab = is_admin
    
    if not show_final_exam_tab and teacher and selected_semester and selected_course:
        show_final_exam_tab = _is_final_exam_evaluator_for_scope(
            teacher, selected_semester, selected_course, selected_centre_id
        )
        if not show_final_exam_tab:
            if teacher1_evaluator_obj and teacher1_evaluator_obj == teacher:
                show_final_exam_tab = True
            elif teacher2_evaluator_obj and teacher2_evaluator_obj == teacher:
                show_final_exam_tab = True
    
    context['show_final_exam_tab'] = show_final_exam_tab
    
    # Read-only "Final Exam Summary" tab: examiner totals, variation, consolidated mark (admins only)
    examiner_summary_rows = []
    if (
        is_admin
        and show_final_exam_tab
        and selected_semester
        and selected_course
        and students
    ):
        for idx, student in enumerate(students, start=1):
            fm = final_exam_marks.get(student.id)
            cm = ca_marks.get(student.id)
            ca_ceil = _ca_total_ceil_int(cm)
            if selected_course.is_lab:
                t_int = float(fm.lab_examiner_split_total(1)) if fm else 0.0
                t_ext = float(fm.lab_examiner_split_total(2)) if fm else 0.0
                mo = float(fm.final_exam_total or 0) if fm else 0.0
                if fm and fm.exam_absent:
                    course_total = 'AB'
                else:
                    course_total = round(mo + ca_ceil, 2)
                examiner_summary_rows.append({
                    'sl': idx,
                    'student': student,
                    'final_mark': fm,
                    'is_lab': True,
                    'lab_internal_total': t_int,
                    'lab_external_total': t_ext,
                    'lab_diff': abs(t_int - t_ext),
                    'marks_obtained': mo,
                    'total_ca': ca_ceil,
                    'course_total': course_total,
                })
            else:
                t1 = float(fm.teacher1_total or 0) if fm else 0.0
                t2 = float(fm.teacher2_total or 0) if fm else 0.0
                t3 = float(fm.teacher3_total or 0) if fm else 0.0
                diff_abs = abs(t1 - t2)
                mo = float(fm.final_exam_total or 0) if fm else 0.0
                if fm and fm.exam_absent:
                    course_total = 'AB'
                elif fm:
                    course_total = round(mo + ca_ceil, 2)
                else:
                    course_total = '—'
                examiner_summary_rows.append({
                    'sl': idx,
                    'student': student,
                    'final_mark': fm,
                    'is_lab': False,
                    't1': t1,
                    't2': t2,
                    't3': t3,
                    'diff_abs': diff_abs,
                    'marks_obtained': mo,
                    'requires_third': (fm.is_third_examiner_required if fm else False),
                    'total_ca': ca_ceil,
                    'course_total': course_total,
                })
    context['examiner_summary_rows'] = examiner_summary_rows
    
    # Get all teachers for admin to select from (only for admins)
    if is_admin:
        all_teachers = Teacher.objects.all().order_by('name')
        context['all_teachers'] = all_teachers
    
    return render(request, 'bou_routines_app/ca_management.html', context)


def _clamp_mark_float(raw, maximum=None):
    """Parse a numeric mark from client JSON: no negatives; optionally cap at maximum."""
    try:
        x = float(raw)
    except (TypeError, ValueError):
        x = 0.0
    if x < 0:
        x = 0.0
    if maximum is not None:
        try:
            mx = float(maximum)
            if x > mx:
                x = mx
        except (TypeError, ValueError):
            pass
    return x


def _parse_optional_mark_float(raw, maximum=None):
    """Parse teacher-entered mark: None/blank -> None; 0 is a valid explicit mark."""
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip() == '':
        return None
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return None
    if x < 0:
        x = 0.0
    if maximum is not None:
        try:
            mx = float(maximum)
            if x > mx:
                x = mx
        except (TypeError, ValueError):
            pass
    return x


def _optional_mark_decimal(raw, maximum=None):
    from decimal import Decimal

    val = _parse_optional_mark_float(raw, maximum)
    if val is None:
        return None
    return Decimal(str(val))


def _parse_final_exam_q_mark(raw):
    """Theory final exam one question set: integer 0..14; blank clears (None)."""
    if raw is None or raw == '':
        return None
    try:
        x = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if x < 0:
        x = 0.0
    if x > 14:
        x = 14.0
    xi = int(x)  # truncate toward zero; UI is integer-only
    if xi > 14:
        xi = 14
    return xi


def _parse_midterm_q_mark(raw):
    """Theory mid-term one question set: integer 0..SET_MARKS_MAX; blank clears (None)."""
    mx = MidtermExamMark.SET_MARKS_MAX
    if raw is None or raw == '':
        return None
    try:
        x = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if x < 0:
        x = 0.0
    if x > mx:
        x = float(mx)
    xi = int(x)
    if xi > mx:
        xi = mx
    return xi


def _apply_theory_final_exam_q_fields(final_mark, teacher_role, marks_data):
    """
    Apply Q1..Q7 from marks_data to the right teacher_* fields.
    Only updates a column when the key is present so sparse requests never wipe
    other questions (e.g. mid-edit auto-save with only one Q filled in).

    If a full row POST sets all seven Qs to 0, treat as unset (NULL). That pattern
    is legacy UI/default fill, not a valid entry under group rules (at most five
    questions can be entered).
    """
    prefix = {'teacher1': 'teacher1', 'teacher2': 'teacher2', 'teacher3': 'teacher3'}.get(teacher_role, 'teacher1')
    parsed = {}
    for i in range(1, 8):
        k = f'q{i}'
        if k not in marks_data:
            continue
        parsed[i] = _parse_final_exam_q_mark(marks_data.get(k))
    if len(parsed) == 7 and all(v == 0 for v in parsed.values()):
        for i in range(1, 8):
            setattr(final_mark, f'{prefix}_q{i}', None)
        return
    for i, val in parsed.items():
        setattr(final_mark, f'{prefix}_q{i}', val)


def _merge_theory_q_state(marks_data, final_mark, teacher_role):
    """Q1..Q7 after applying marks_data (partial POST) on top of existing final_mark for the active teacher."""
    prefix = {'teacher1': 'teacher1', 'teacher2': 'teacher2', 'teacher3': 'teacher3'}.get(teacher_role, 'teacher1')
    state = {}
    for i in range(1, 8):
        k = f'q{i}'
        if k in marks_data:
            state[i] = _parse_final_exam_q_mark(marks_data.get(k))
        else:
            state[i] = getattr(final_mark, f'{prefix}_q{i}', None)
    return state


def _theory_q_group_rules_ok(state):
    """At most two entered marks in Q1–Q3, at most two in Q4–Q6; Q7 is unrestricted (matches UI)."""
    def is_entered(i):
        return state.get(i) is not None

    a = sum(1 for i in (1, 2, 3) if is_entered(i))
    b = sum(1 for i in (4, 5, 6) if is_entered(i))
    return a <= 2 and b <= 2


def _midterm_theory_q_group_rules_ok(state):
    """Six-set mid-term: at most two entered in Q1–Q3, at most one in Q4–Q5; Q6 unrestricted."""
    def is_entered(i):
        return state.get(i) is not None

    a = sum(1 for i in (1, 2, 3) if is_entered(i))
    b = sum(1 for i in (4, 5) if is_entered(i))
    return a <= 2 and b <= 1


def _merge_midterm_q_state(marks_data, mm):
    """Q1..Q6 after applying marks_data (partial POST) on top of existing MidtermExamMark."""
    mx = MidtermExamMark.SET_MARKS_MAX
    state = {}
    for i in range(1, 7):
        k = f'q{i}'
        if k in marks_data:
            state[i] = _parse_midterm_q_mark(marks_data.get(k))
        else:
            prev = getattr(mm, f'q{i}', None) if mm else None
            if prev is None:
                state[i] = None
            else:
                pv = int(float(prev))
                state[i] = min(mx, max(0, pv))
    return state


def _apply_midterm_q_fields(mm, marks_data):
    """Apply only keys present in marks_data (sparse auto-save safe)."""
    from decimal import Decimal

    for i in range(1, 7):
        k = f'q{i}'
        if k not in marks_data:
            continue
        val = _parse_midterm_q_mark(marks_data.get(k))
        setattr(mm, f'q{i}', None if val is None else Decimal(str(val)))


def _user_can_edit_lab_viva(user, teacher=None, semester=None, course=None, centre=None):
    """
    Lab final viva column: assigned chairman for this offering, global chairman
    permission, superuser, or marks-page admin (staff without a teacher profile).
    """
    if user.is_superuser:
        return True
    if teacher is None:
        teacher = get_teacher_from_user(user)
    if user.is_staff and not teacher:
        return True
    if teacher and semester and course and centre:
        centre_obj = centre if isinstance(centre, Centre) else None
        if centre_obj is None:
            try:
                centre_obj = Centre.objects.get(id=int(centre))
            except (Centre.DoesNotExist, ValueError, TypeError):
                centre_obj = None
        if centre_obj:
            sc = SemesterCourse.objects.filter(
                semester=semester,
                course=course,
                centre=centre_obj,
            ).only('lab_examination_chairman_id').first()
            if sc and sc.lab_examination_chairman_id == teacher.id:
                return True
    return check_teacher_permission(user, 'can_chair_examination')


def _teacher_marks_accessible_course_ids(teacher, semester_id):
    """
    Course IDs this teacher may open on the Marks page for a semester.

    Includes offerings where they are the course teacher or an assigned
    final-exam examiner at any study centre. The selected-centre filter is
    applied separately so a DRC teacher/examiner can open the same course
    at DUET (Semester Final only — CA / Mid-Term stay centre-scoped).
    """
    if not teacher or not semester_id:
        return []
    return list(
        SemesterCourse.objects.filter(semester_id=semester_id).filter(
            Q(teacher=teacher)
            | Q(final_exam_evaluator1=teacher)
            | Q(final_exam_evaluator2=teacher)
            | Q(final_exam_evaluator3=teacher)
        ).values_list('course_id', flat=True).distinct()
    )


def _is_course_teacher_for_scope(teacher, semester, course, centre_id):
    """True if this teacher is SemesterCourse.teacher for the given offering."""
    if not teacher or not semester or not course:
        return False
    qs = SemesterCourse.objects.filter(
        semester=semester,
        course=course,
        teacher=teacher,
    )
    if centre_id not in (None, ''):
        try:
            qs = qs.filter(centre_id=int(centre_id))
        except (ValueError, TypeError):
            pass
    return qs.exists()


def _is_final_exam_evaluator_for_scope(teacher, semester, course, centre_id):
    """
    True if this teacher may use the Semester Final tab in CA management (non-admins).
    Kept in sync with show_final_exam_tab in ca_management.

    Course teacher or assigned examiner at any centre of this offering may enter
    Semester Final for the other centre as well (typical DRC/DUET examiner pair).
    """
    if not teacher or not semester or not course:
        return False
    if centre_id not in (None, ''):
        try:
            sc_tab = SemesterCourse.objects.filter(
                semester=semester,
                course=course,
                centre_id=int(centre_id),
            ).first()
            if sc_tab and (
                sc_tab.final_exam_evaluator1 == teacher
                or sc_tab.final_exam_evaluator2 == teacher
                or sc_tab.final_exam_evaluator3 == teacher
            ):
                return True
        except (ValueError, TypeError):
            pass
    if SemesterCourse.objects.filter(semester=semester, course=course).filter(
        Q(teacher=teacher)
        | Q(final_exam_evaluator1=teacher)
        | Q(final_exam_evaluator2=teacher)
        | Q(final_exam_evaluator3=teacher)
    ).exists():
        return True
    sample_mark = final_exam_mark_sample_for_scope(course, semester, centre_id)
    if sample_mark and (
        sample_mark.teacher1_evaluator == teacher
        or sample_mark.teacher2_evaluator == teacher
        or sample_mark.teacher3_evaluator == teacher
    ):
        return True
    return False


def _reject_if_not_course_teacher_for_ca_midterm(request, semester, course, centre_id):
    """
    Examiner-only teachers may enter Semester Final marks, but not CA / Mid-Term.
    Admins always allowed. Course teachers (including those who are also examiners) allowed.
    """
    if _user_can_edit_ca_and_midterm(request, semester, course, centre_id):
        return None
    return JsonResponse(
        {'error': 'Only the course teacher can manage CA and Mid-Term marks for this course.'},
        status=403,
    )


def _user_can_edit_ca_and_midterm(request, semester, course, centre_id):
    teacher_user = get_teacher_from_user(request.user)
    is_admin = request.user.is_superuser or (request.user.is_staff and not teacher_user)
    if is_admin:
        return True
    return bool(
        teacher_user
        and _is_course_teacher_for_scope(teacher_user, semester, course, centre_id)
    )


def _reject_old_curriculum_for_marks_json(semester, course=None):
    """Marks UI is new-curriculum only; block API saves for OLD scope."""
    if getattr(semester, 'curriculum', None) and semester.curriculum.code == 'OLD':
        return JsonResponse({'error': 'Marks are not available for old curriculum.'}, status=400)
    if course is not None and getattr(course, 'curriculum', None) and course.curriculum.code == 'OLD':
        return JsonResponse({'error': 'Marks are not available for old curriculum.'}, status=400)
    return None


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
        bad = _reject_old_curriculum_for_marks_json(semester, course)
        if bad:
            return bad

        centre_id_for_perm = request.POST.get('centre_id')
        denied = _reject_if_not_course_teacher_for_ca_midterm(
            request, semester, course, centre_id_for_perm,
        )
        if denied:
            return denied
        
        # Get teacher
        teacher = None
        if hasattr(request.user, 'teacher'):
            teacher = request.user.teacher
        elif request.user.is_superuser or request.user.is_staff:
            # For admin users, we need to get the course teacher from SemesterCourse
            # Get centre from request if available
            centre_id = request.POST.get('centre_id')
            semester_course = None
            if centre_id:
                try:
                    centre = Centre.objects.get(id=centre_id)
                    semester_course = SemesterCourse.objects.filter(
                        semester=semester,
                        course=course,
                        centre=centre
                    ).select_related('teacher').first()
                except Centre.DoesNotExist:
                    pass
            
            # Fallback: get any SemesterCourse for this semester and course
            if not semester_course:
                semester_course = SemesterCourse.objects.filter(
                    semester=semester,
                    course=course
                ).select_related('teacher').first()
            
            if semester_course:
                teacher = semester_course.teacher
        
        if not teacher:
            # More detailed error message
            error_msg = 'Teacher not found. '
            if hasattr(request.user, 'teacher'):
                error_msg += f'User {request.user.username} has no teacher profile.'
            elif request.user.is_superuser or request.user.is_staff:
                error_msg += f'Could not find teacher for semester={semester_id}, course={course_id}'
                centre_id = request.POST.get('centre_id')
                if centre_id:
                    error_msg += f', centre={centre_id}'
            else:
                error_msg += f'User {request.user.username} does not have permission.'
            return JsonResponse({'error': error_msg}, status=400)
        
        # Process each student's marks
        students_data = request.POST.get('students_data')
        if not students_data:
            return JsonResponse({'error': 'No student data provided'}, status=400)
        
        import json
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            students_marks = json.loads(students_data)
            logger.info(f"CA marks save: Parsed JSON successfully. Keys: {list(students_marks.keys())}")
            if students_marks:
                first_key = list(students_marks.keys())[0]
                logger.info(f"CA marks save: First student ID: '{first_key}' (type: {type(first_key).__name__}, repr: {repr(first_key)})")
        except json.JSONDecodeError as e:
            logger.error(f"CA marks save: JSON decode error: {e}. Raw data: {students_data[:200]}")
            return JsonResponse({'error': f'Invalid JSON data: {str(e)}'}, status=400)
        
        if not students_marks:
            return JsonResponse({'error': 'Empty student data'}, status=400)
        
        saved_count = 0
        failed_students = []
        first_save_exception = None
        first_save_traceback = None
        
        # Log first few student IDs being processed for debugging
        sample_ids = list(students_marks.keys())[:5]
        logger.info(f"CA marks save: Processing {len(students_marks)} students. Sample IDs: {sample_ids}")
        logger.info(f"CA marks save: All student IDs received: {list(students_marks.keys())}")
        
        # Check if any of these IDs exist in database
        existing_students = Student.objects.filter(id__in=sample_ids).values_list('id', flat=True)
        logger.info(f"CA marks save: Found {len(existing_students)} of {len(sample_ids)} sample IDs in database: {list(existing_students)}")
        
        # Also check all IDs
        all_received_ids = [str(id).strip() for id in students_marks.keys()]
        all_existing_students = Student.objects.filter(id__in=all_received_ids).values_list('id', flat=True)
        logger.info(f"CA marks save: Found {len(all_existing_students)} of {len(all_received_ids)} total IDs in database")
        missing_ids = set(all_received_ids) - set(all_existing_students)
        if missing_ids:
            logger.warning(f"CA marks save: Missing student IDs: {missing_ids}")
        
        for student_id, marks_data in students_marks.items():
            try:
                # Student.id is a CharField, ensure we use string and strip whitespace
                student_id_clean = str(student_id).strip()
                logger.info(f"CA marks save: Looking up student with ID: '{student_id_clean}' (original: '{student_id}', type: {type(student_id).__name__})")
                
                # Direct database check first
                try:
                    student = Student.objects.get(id=student_id_clean)
                    logger.info(f"CA marks save: Successfully found student using .get(): {student.id} - {student.name}")
                except Student.DoesNotExist:
                    logger.warning(f"CA marks save: .get() failed for '{student_id_clean}', trying .filter()")
                    # Try with filter (more forgiving)
                    student = Student.objects.filter(id=student_id_clean).first()
                    if student:
                        logger.info(f"CA marks save: Found student using .filter(): {student.id} - {student.name}")
                    else:
                        # Try with the original ID (no cleaning)
                        logger.warning(f"CA marks save: Filter lookup failed for '{student_id_clean}', trying with original: '{student_id}'")
                        student = Student.objects.filter(id=student_id).first()
                        if student:
                            logger.info(f"CA marks save: Found student using original ID: {student.id} - {student.name}")
                
                if not student:
                    # Log all available student IDs for debugging
                    sample_students = list(Student.objects.all()[:5].values_list('id', flat=True))
                    logger.error(f"CA marks save: Student '{student_id_clean}' not found. Sample student IDs in DB: {sample_students}")
                    # Check if student exists with any variation - try direct query
                    direct_check = Student.objects.filter(id=student_id_clean).exists()
                    logger.error(f"CA marks save: Direct exists() check for '{student_id_clean}': {direct_check}")
                    # Check if student exists with any variation
                    all_students_count = Student.objects.count()
                    logger.error(f"CA marks save: Total students in DB: {all_students_count}")
                    raise Student.DoesNotExist(f"Student with ID '{student_id_clean}' not found")

                centre_id_post = request.POST.get('centre_id')
                if centre_id_post:
                    try:
                        expected_centre = Centre.objects.get(id=int(centre_id_post))
                        if student.centre_id != expected_centre.id:
                            logger.warning(
                                f"CA marks save: skipping {student_id_clean} (student centre "
                                f"{student.centre_id} != selected centre {expected_centre.id})"
                            )
                            continue
                    except (Centre.DoesNotExist, ValueError, TypeError):
                        pass
                
                # Get or create CA mark record
                # Get or create CA mark record
                ca_mark, created = CAMark.objects.get_or_create(
                    student=student,
                    course=course,
                    semester=semester,
                    defaults={'marked_by': teacher}
                )
                
                # Update marks based on course type
                if course.course_type == 'PROJECT':
                    # Project Work marks
                    ca_mark.project_supervisor_mark = _optional_mark_decimal(
                        marks_data.get('project_supervisor_mark'), course.effective_project_supervisor_weight
                    )
                    ca_mark.project_evaluation_mark = _optional_mark_decimal(
                        marks_data.get('project_evaluation_mark'), course.effective_project_evaluation_weight
                    )
                    ca_mark.project_presentation_mark = _optional_mark_decimal(
                        marks_data.get('project_presentation_mark'), course.effective_project_presentation_weight
                    )
                elif course.is_lab:
                    # Lab course marks
                    ca_mark.first_lab_assignment_mark = _optional_mark_decimal(
                        marks_data.get('first_lab_assignment_mark'), course.effective_lab_ca_assignment_weight
                    )
                    ca_mark.second_lab_assignment_mark = _optional_mark_decimal(
                        marks_data.get('second_lab_assignment_mark'), course.effective_lab_ca_assignment_weight
                    )
                    ca_mark.third_lab_assignment_mark = _optional_mark_decimal(
                        marks_data.get('third_lab_assignment_mark'), course.effective_lab_ca_assignment_weight
                    )
                    ca_mark.lab_practical_mark = _optional_mark_decimal(
                        marks_data.get('lab_practical_mark'), course.effective_lab_ca_practical_weight
                    )
                    if course.effective_lab_ca_practical2_weight:
                        ca_mark.second_lab_practical_mark = _optional_mark_decimal(
                            marks_data.get('second_lab_practical_mark'),
                            course.effective_lab_ca_practical2_weight,
                        )
                    else:
                        ca_mark.second_lab_practical_mark = None
                else:
                    # Theory course marks
                    ca_mark.first_assignment_mark = _optional_mark_decimal(
                        marks_data.get('first_assignment_mark'), course.effective_ca_assignment_weight
                    )
                    ca_mark.second_assignment_mark = _optional_mark_decimal(
                        marks_data.get('second_assignment_mark'), course.effective_ca_assignment_weight
                    )
                    ca_mark.third_assignment_mark = _optional_mark_decimal(
                        marks_data.get('third_assignment_mark'), course.effective_ca_assignment_weight
                    )
                    
                    # Determine which exam type to use based on curriculum
                    if semester.curriculum and semester.curriculum.code == 'OLD':
                        # Old curriculum: use class tests (best of first and second)
                        ca_mark.first_class_test_mark = _optional_mark_decimal(
                            marks_data.get('first_class_test_mark'), course.effective_ca_quiz_weight
                        )
                        ca_mark.second_class_test_mark = _optional_mark_decimal(
                            marks_data.get('second_class_test_mark'), course.effective_ca_quiz_weight
                        )
                        ca_mark.midterm_mark = None
                    else:
                        # New curriculum: mid-term from MidtermExamMark sheet when present
                        if MidtermExamMark.objects.filter(student=student, course=course, semester=semester).exists():
                            mm_sync = MidtermExamMark.objects.get(
                                student=student, course=course, semester=semester
                            )
                            ca_mark.midterm_mark = mm_sync.scaled_midterm_contribution()
                        else:
                            ca_mark.midterm_mark = _optional_mark_decimal(
                                marks_data.get('midterm_mark'), course.effective_ca_midterm_weight
                            )
                        ca_mark.first_class_test_mark = None
                        ca_mark.second_class_test_mark = None
                
                # Update metadata
                ca_mark.marked_by = teacher
                notes_val = marks_data.get('notes')
                ca_mark.notes = '' if notes_val is None else str(notes_val)
                
                # Validate that required fields are set before save
                if not ca_mark.marked_by:
                    logger.error(f"marked_by is None for student {student_id_clean}")
                    failed_students.append(student_id_clean)
                    continue
                
                # Save (this will trigger auto-calculation of attendance and total marks)
                # The save() method in CAMark model will auto-calculate:
                # - attendance_mark
                # - assignment_mark (average of three assignments)
                # - lab_assignment_mark (average of three lab assignments)
                # - total_ca_mark
                try:
                    # Log the state before save for debugging
                    logger.info(f"CA marks save: About to save for student {student_id_clean}. State: first_assignment={ca_mark.first_assignment_mark}, second_assignment={ca_mark.second_assignment_mark}, third_assignment={ca_mark.third_assignment_mark}, first_class_test={ca_mark.first_class_test_mark}, second_class_test={ca_mark.second_class_test_mark}, midterm={ca_mark.midterm_mark}, marked_by={ca_mark.marked_by.id if ca_mark.marked_by else 'None'}")
                    ca_mark.save()
                    saved_count += 1
                    logger.info(f"Successfully saved CA marks for student {student_id_clean}: first_assignment={ca_mark.first_assignment_mark}, midterm={ca_mark.midterm_mark}, total={ca_mark.total_ca_mark}")
                except Exception as save_ex:
                    import traceback
                    error_traceback = traceback.format_exc()
                    logger.error(f"Database error saving CA marks for student {student_id_clean}: {save_ex}")
                    logger.error(f"Full traceback:\n{error_traceback}")
                    logger.error(f"CA mark state: student={ca_mark.student.id}, course={ca_mark.course.code}, semester={ca_mark.semester.name}, marked_by={ca_mark.marked_by.id if ca_mark.marked_by else 'None'}")
                    logger.error(f"CA mark values: first_assignment={ca_mark.first_assignment_mark}, second_assignment={ca_mark.second_assignment_mark}, third_assignment={ca_mark.third_assignment_mark}")
                    if first_save_exception is None:
                        first_save_exception = str(save_ex)
                        first_save_traceback = error_traceback
                    failed_students.append(student_id_clean)
                    continue
                
            except Student.DoesNotExist:
                logger.warning(f"Student {student_id} (cleaned: '{student_id_clean}') not found")
                # Try to find similar IDs for debugging
                similar_students = Student.objects.filter(id__icontains=student_id_clean[:10]).values_list('id', flat=True)[:5]
                logger.warning(f"Similar student IDs found: {list(similar_students)}")
                failed_students.append(student_id_clean)
                continue
            except (ValueError, TypeError) as e:
                logger.error(f"Error processing marks for student {student_id}: {e}", exc_info=True)
                failed_students.append(student_id_clean)
                continue
            except Exception as e:
                # Catch any other exceptions during save (e.g., database errors, validation errors)
                logger.error(f"Unexpected error saving CA marks for student {student_id}: {e}", exc_info=True)
                failed_students.append(student_id_clean)
                continue
        
        if saved_count == 0:
            # More detailed error message
            total_students = len(students_marks)
            error_msg = f'No marks were saved out of {total_students} student(s). '
            if failed_students:
                sample_ids = failed_students[:5]  # Show first 5 failed IDs
                # Check if these are actually student lookup failures or other errors
                logger.warning(f"CA marks save failed: {total_students} students processed, 0 saved. Failed IDs: {failed_students[:10]}")
                # Verify if students actually exist
                existing_failed = Student.objects.filter(id__in=failed_students[:5]).values_list('id', flat=True)
                if existing_failed:
                    logger.error(f"CA marks save: Some failed IDs actually exist in DB: {list(existing_failed)}")
                    error_msg += f'Student IDs found but save failed: {", ".join(sample_ids)}. Check server logs for details.'
                else:
                    error_msg += f'Sample student IDs not found: {", ".join(sample_ids)}'
                if len(failed_students) > 5:
                    error_msg += f' (and {len(failed_students) - 5} more)'
                if first_save_exception:
                    error_msg += f' First error: {first_save_exception}'
            else:
                error_msg += 'Possible reasons: Student IDs not found in database, or all marks failed validation.'
            logger.warning(f"CA marks save failed: {total_students} students processed, 0 saved. Failed IDs: {failed_students[:10]}")
            return JsonResponse({'error': error_msg}, status=400)
        
        return JsonResponse({'success': True, 'message': 'CA marks saved successfully'})
        
    except (Semester.DoesNotExist, Course.DoesNotExist):
        return JsonResponse({'error': 'Invalid semester or course'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def save_midterm_marks(request):
    """
    Save theory mid-term Q1–Q6 (new curriculum), validate group rules, sync CAMark.midterm_mark.
    """
    if not (request.user.is_superuser or request.user.is_staff or check_teacher_permission(request.user, 'can_manage_ca')):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        semester_id = request.POST.get('semester_id')
        course_id = request.POST.get('course_id')
        if not semester_id or not course_id:
            return JsonResponse({'error': 'Semester and course are required'}, status=400)

        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)

        if course.is_lab or course.course_type == 'PROJECT':
            return JsonResponse({'error': 'Mid-term marks apply only to theory courses'}, status=400)
        if not semester.curriculum or semester.curriculum.code == 'OLD':
            return JsonResponse({'error': 'Mid-term marks apply only to new curriculum semesters'}, status=400)

        centre_id_for_perm = request.POST.get('centre_id')
        denied = _reject_if_not_course_teacher_for_ca_midterm(
            request, semester, course, centre_id_for_perm,
        )
        if denied:
            return denied

        teacher = None
        if hasattr(request.user, 'teacher'):
            teacher = request.user.teacher
        elif request.user.is_superuser or request.user.is_staff:
            centre_id = request.POST.get('centre_id')
            semester_course = None
            if centre_id:
                try:
                    centre = Centre.objects.get(id=int(centre_id))
                    semester_course = SemesterCourse.objects.filter(
                        semester=semester, course=course, centre=centre
                    ).select_related('teacher').first()
                except Centre.DoesNotExist:
                    pass
            if not semester_course:
                semester_course = SemesterCourse.objects.filter(
                    semester=semester, course=course
                ).select_related('teacher').first()
            if semester_course:
                teacher = semester_course.teacher

        if not teacher:
            return JsonResponse({'error': 'Teacher not found'}, status=400)

        students_data = request.POST.get('students_data')
        if not students_data:
            return JsonResponse({'error': 'No student data provided'}, status=400)

        import json

        try:
            students_marks = json.loads(students_data)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid students_data (JSON).'}, status=400)
        if not isinstance(students_marks, dict):
            return JsonResponse({'error': 'Invalid students_data format.'}, status=400)
        if not students_marks:
            return JsonResponse({'error': 'Empty student data'}, status=400)

        rows_updated = 0
        centre_id_post = request.POST.get('centre_id')

        for student_id, marks_data in students_marks.items():
            if not isinstance(marks_data, dict):
                return JsonResponse(
                    {'error': f'Invalid marks for student {student_id}: expected an object.'},
                    status=400,
                )
            try:
                student = Student.objects.get(id=str(student_id).strip())
            except Student.DoesNotExist:
                continue

            if centre_id_post:
                try:
                    expected_centre = Centre.objects.get(id=int(centre_id_post))
                    if student.centre_id is not None and student.centre_id != expected_centre.id:
                        continue
                except (Centre.DoesNotExist, ValueError, TypeError):
                    pass

            mm, _created = MidtermExamMark.objects.get_or_create(
                student=student,
                course=course,
                semester=semester,
                defaults={'marked_by': teacher},
            )
            merged = _merge_midterm_q_state(marks_data, mm)
            if not _midterm_theory_q_group_rules_ok(merged):
                return JsonResponse(
                    {
                        'error': (
                            'Mid-term rules: at most 2 of Q1–Q3 and at most 1 of Q4–Q5 can have marks '
                            'entered (including 0). Adjust Group A, Group B, and Q6, then save again.'
                        )
                    },
                    status=400,
                )

            _apply_midterm_q_fields(mm, marks_data)
            mm.marked_by = teacher
            mm.save()

            ca_mark, _ = CAMark.objects.get_or_create(
                student=student,
                course=course,
                semester=semester,
                defaults={'marked_by': teacher},
            )
            ca_mark.midterm_mark = mm.scaled_midterm_contribution()
            ca_mark.marked_by = teacher
            ca_mark.save()
            rows_updated += 1

        if rows_updated == 0:
            return JsonResponse(
                {'error': 'No mid-term rows were saved. Check student IDs and study centre.'},
                status=400,
            )

        return JsonResponse({'success': True, 'message': 'Mid-term marks saved successfully'})
    except (Semester.DoesNotExist, Course.DoesNotExist):
        return JsonResponse({'error': 'Invalid semester or course'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _apply_final_exam_examiner_assignments_from_post(request, semester, course):
    """
    Persist Assign Examiners from POST onto SemesterCourse (canonical) for this
    semester + course + study centre, then sync to FinalExamMark. Staff only.

    Keys: assign_teacher1_id, assign_teacher2_id, assign_teacher3_id — empty string clears.
    Returns None on success, or an error string for JsonResponse.
    """
    if not (request.user.is_superuser or request.user.is_staff):
        return None

    assign_keys = ('assign_teacher1_id', 'assign_teacher2_id', 'assign_teacher3_id')
    if not any(k in request.POST for k in assign_keys):
        return None
    # If all assign fields are empty, do nothing (avoids requiring centre on every marks-only save)
    if not any((request.POST.get(k) or '').strip() for k in assign_keys):
        return None

    cid = (request.POST.get('centre_id') or request.POST.get('centre') or '').strip()
    if not cid:
        return 'Study centre is required to save examiners.'

    try:
        centre = Centre.objects.get(id=int(cid))
    except (Centre.DoesNotExist, ValueError, TypeError):
        return 'Invalid study centre.'

    sc = SemesterCourse.objects.filter(
        semester=semester, course=course, centre=centre
    ).first()
    if not sc:
        return (
            'No Semester course row for this semester, course, and study centre. '
            'Add the offering in admin first.'
        )

    def _teacher_from_post(key):
        if key not in request.POST:
            return None
        raw = (request.POST.get(key) or '').strip()
        if not raw:
            return None
        try:
            return Teacher.objects.get(id=int(raw))
        except (ValueError, Teacher.DoesNotExist):
            return None

    if 'assign_teacher1_id' in request.POST:
        sc.final_exam_evaluator1 = _teacher_from_post('assign_teacher1_id')
    if 'assign_teacher2_id' in request.POST:
        sc.final_exam_evaluator2 = _teacher_from_post('assign_teacher2_id')
    if 'assign_teacher3_id' in request.POST:
        sc.final_exam_evaluator3 = _teacher_from_post('assign_teacher3_id')
    if course.is_lab:
        sc.final_exam_evaluator3 = None
    sc.save()

    _sync_final_exam_evaluators_from_semester_course(semester, course, centre)
    return None


@login_required
@require_POST
def save_semester_final_attendance(request):
    """
    Set FinalExamMark.exam_absent for one student (Semester Final Attendance UI).
    Auto-saved from the marks page without a separate Save button.
    Only administrators (same rule as ca_management is_admin) may use this;
    evaluators and other teachers have no visibility of the UI and must not POST here.
    """
    try:
        t_user = get_teacher_from_user(request.user)
        if not (request.user.is_superuser or (request.user.is_staff and not t_user)):
            return JsonResponse(
                {'error': 'Only administrators can update semester final attendance.'},
                status=403,
            )
        semester_id = request.POST.get('semester_id')
        course_id = request.POST.get('course_id')
        student_id = (request.POST.get('student_id') or '').strip()
        raw_absent = (request.POST.get('exam_absent') or '').strip().lower()
        exam_absent = raw_absent in ('1', 'true', 'yes', 'absent', 'on')
        teacher_role = (request.POST.get('teacher_role') or 'teacher1').strip()
        if teacher_role not in ('teacher1', 'teacher2', 'teacher3'):
            teacher_role = 'teacher1'

        if not semester_id or not course_id or not student_id:
            return JsonResponse({'error': 'semester_id, course_id, and student_id are required'}, status=400)

        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        bad = _reject_old_curriculum_for_marks_json(semester, course)
        if bad:
            return bad

        centre_id_for_perm = request.POST.get('centre_id') or request.POST.get('centre')
        teacher_user = get_teacher_from_user(request.user)
        can_post = (
            request.user.is_superuser
            or request.user.is_staff
            or check_teacher_permission(request.user, 'can_manage_final_marks')
            or (teacher_user is not None and _is_final_exam_evaluator_for_scope(teacher_user, semester, course, centre_id_for_perm))
        )
        if not can_post:
            return JsonResponse({'error': 'Permission denied'}, status=403)

        student = Student.objects.get(id=student_id)
        if centre_id_for_perm:
            try:
                expected_centre = Centre.objects.get(id=int(centre_id_for_perm))
                if student.centre_id is not None and student.centre_id != expected_centre.id:
                    return JsonResponse({'error': 'Student is not in the selected study centre.'}, status=400)
            except (Centre.DoesNotExist, ValueError, TypeError):
                pass

        teacher = None
        if hasattr(request.user, 'teacher'):
            teacher = request.user.teacher
        elif request.user.is_superuser or request.user.is_staff:
            drc_centre = Centre.objects.filter(code='DRC').first()
            duet_centre = Centre.objects.filter(code='DUET').first()
            if teacher_role == 'teacher1' and drc_centre:
                semester_course = SemesterCourse.objects.filter(
                    semester=semester,
                    course=course,
                    centre=drc_centre,
                ).select_related('teacher', 'teacher__centre').first()
                if semester_course and semester_course.teacher and semester_course.teacher.centre == drc_centre:
                    teacher = semester_course.teacher
            elif teacher_role == 'teacher2' and duet_centre:
                semester_course = SemesterCourse.objects.filter(
                    semester=semester,
                    course=course,
                    centre=duet_centre,
                ).select_related('teacher', 'teacher__centre').first()
                if semester_course and semester_course.teacher and semester_course.teacher.centre == duet_centre:
                    teacher = semester_course.teacher
            elif teacher_role == 'teacher3':
                sample_mark = FinalExamMark.objects.filter(course=course, semester=semester).first()
                if sample_mark and sample_mark.teacher3_evaluator:
                    teacher = sample_mark.teacher3_evaluator
                else:
                    teacher_id = request.POST.get('teacher3_id')
                    if teacher_id:
                        try:
                            teacher = Teacher.objects.get(id=teacher_id)
                        except Teacher.DoesNotExist:
                            pass
            if not teacher:
                centre_id = request.POST.get('centre_id') or request.POST.get('centre')
                semester_course = None
                if centre_id:
                    try:
                        centre = Centre.objects.get(id=centre_id)
                        semester_course = SemesterCourse.objects.filter(
                            semester=semester,
                            course=course,
                            centre=centre,
                        ).select_related('teacher').first()
                    except Centre.DoesNotExist:
                        pass
                if not semester_course:
                    semester_course = SemesterCourse.objects.filter(
                        semester=semester,
                        course=course,
                    ).select_related('teacher').first()
                if semester_course:
                    teacher = semester_course.teacher

        if not teacher:
            return JsonResponse({'error': 'Teacher not found for this record.'}, status=400)

        final_mark, _created = FinalExamMark.objects.get_or_create(
            student=student,
            course=course,
            semester=semester,
            defaults={'marked_by': teacher, 'exam_absent': False},
        )
        final_mark.exam_absent = bool(exam_absent)
        if final_mark.exam_absent:
            final_mark.clear_numeric_exam_fields()
        final_mark.marked_by = teacher
        final_mark.save()

        return JsonResponse({'success': True, 'exam_absent': final_mark.exam_absent})
    except Student.DoesNotExist:
        return JsonResponse({'error': 'Student not found'}, status=404)
    except (Semester.DoesNotExist, Course.DoesNotExist):
        return JsonResponse({'error': 'Invalid semester or course'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def save_final_exam_marks(request):
    """
    Save Semester Final Examination marks for students
    """
    try:
        semester_id = request.POST.get('semester_id')
        course_id = request.POST.get('course_id')
        teacher_role = (request.POST.get('teacher_role') or 'teacher1').strip()
        if teacher_role not in ('teacher1', 'teacher2', 'teacher3'):
            teacher_role = 'teacher1'
        
        if not semester_id or not course_id:
            return JsonResponse({'error': 'Semester and course are required'}, status=400)
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        bad = _reject_old_curriculum_for_marks_json(semester, course)
        if bad:
            return bad
        if course.is_lab and teacher_role == 'teacher3':
            teacher_role = 'teacher1'

        centre_id_for_perm = request.POST.get('centre_id') or request.POST.get('centre')
        teacher_user = get_teacher_from_user(request.user)
        can_post = (
            request.user.is_superuser
            or request.user.is_staff
            or check_teacher_permission(request.user, 'can_manage_final_marks')
            or (teacher_user is not None and _is_final_exam_evaluator_for_scope(teacher_user, semester, course, centre_id_for_perm))
        )
        if not can_post:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        # Teacher for marked_by / evaluator FKs.
        # Staff/superuser must resolve from SemesterCourse (lab internal/external at selected centre; theory DRC/DUET)
        # even if they also have user.teacher — otherwise the first branch skipped SC and mis-attributed lab saves.
        teacher = None
        if request.user.is_superuser or request.user.is_staff:
            drc_centre = Centre.objects.filter(code='DRC').first()
            duet_centre = Centre.objects.filter(code='DUET').first()
            centre_id_post = request.POST.get('centre_id') or request.POST.get('centre')
            if course.is_lab and centre_id_post:
                try:
                    centre_sel = Centre.objects.get(id=int(centre_id_post))
                    sc_lab = SemesterCourse.objects.filter(
                        semester=semester,
                        course=course,
                        centre=centre_sel,
                    ).select_related('final_exam_evaluator1', 'final_exam_evaluator2').first()
                    if sc_lab:
                        if teacher_role == 'teacher1' and sc_lab.final_exam_evaluator1:
                            teacher = sc_lab.final_exam_evaluator1
                        elif teacher_role == 'teacher2' and sc_lab.final_exam_evaluator2:
                            teacher = sc_lab.final_exam_evaluator2
                except (Centre.DoesNotExist, ValueError, TypeError):
                    pass

            if not teacher and teacher_role == 'teacher1':
                if drc_centre:
                    semester_course = SemesterCourse.objects.filter(
                        semester=semester,
                        course=course,
                        centre=drc_centre
                    ).select_related('teacher', 'teacher__centre').first()
                    if semester_course and semester_course.teacher and semester_course.teacher.centre == drc_centre:
                        teacher = semester_course.teacher
            elif not teacher and teacher_role == 'teacher2':
                if duet_centre:
                    semester_course = SemesterCourse.objects.filter(
                        semester=semester,
                        course=course,
                        centre=duet_centre
                    ).select_related('teacher', 'teacher__centre').first()
                    if semester_course and semester_course.teacher and semester_course.teacher.centre == duet_centre:
                        teacher = semester_course.teacher
            elif not teacher and teacher_role == 'teacher3' and not course.is_lab:
                sample_mark = FinalExamMark.objects.filter(
                    course=course,
                    semester=semester
                ).first()
                if sample_mark and sample_mark.teacher3_evaluator:
                    teacher = sample_mark.teacher3_evaluator
                else:
                    teacher_id = request.POST.get('teacher3_id')
                    if teacher_id:
                        try:
                            teacher = Teacher.objects.get(id=teacher_id)
                        except Teacher.DoesNotExist:
                            pass

            if not teacher:
                centre_id = request.POST.get('centre_id') or request.POST.get('centre')
                semester_course = None
                if centre_id:
                    try:
                        centre = Centre.objects.get(id=centre_id)
                        semester_course = SemesterCourse.objects.filter(
                            semester=semester,
                            course=course,
                            centre=centre
                        ).select_related('teacher').first()
                    except Centre.DoesNotExist:
                        pass

                if not semester_course:
                    semester_course = SemesterCourse.objects.filter(
                        semester=semester,
                        course=course
                    ).select_related('teacher').first()

                if semester_course:
                    teacher = semester_course.teacher

            if not teacher and hasattr(request.user, 'teacher'):
                teacher = request.user.teacher

        elif hasattr(request.user, 'teacher'):
            teacher = request.user.teacher

        if not teacher:
            return JsonResponse({'error': 'Teacher not found'}, status=400)
        
        # Process each student's marks
        notes_only_request = request.POST.get('notes_only') == '1'
        apply_assign_from_post = (
            not notes_only_request
            and (request.user.is_superuser or request.user.is_staff)
            and any(
                (request.POST.get(k) or '').strip()
                for k in ('assign_teacher1_id', 'assign_teacher2_id', 'assign_teacher3_id')
            )
        )
        if apply_assign_from_post:
            assign_err = _apply_final_exam_examiner_assignments_from_post(request, semester, course)
            if assign_err:
                return JsonResponse({'error': assign_err}, status=400)

        students_data = request.POST.get('students_data')
        rows_updated = 0
        if students_data:
            import json
            try:
                students_marks = json.loads(students_data)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid students_data (JSON).'}, status=400)
            if not isinstance(students_marks, dict):
                return JsonResponse({'error': 'Invalid students_data format.'}, status=400)
            
            for student_id, marks_data in students_marks.items():
                if not isinstance(marks_data, dict):
                    return JsonResponse(
                        {'error': f'Invalid marks for student {student_id}: expected an object, not a single value. Reload and try again.'},
                        status=400,
                    )
                try:
                    student = Student.objects.get(id=str(student_id).strip())

                    # Optional centre check: only skip if student has a centre and it differs
                    # (saves for students with centre=None were previously skipped, so nothing persisted)
                    centre_id_post = request.POST.get('centre_id') or request.POST.get('centre')
                    if centre_id_post:
                        try:
                            expected_centre = Centre.objects.get(id=int(centre_id_post))
                            if student.centre_id is not None and student.centre_id != expected_centre.id:
                                continue
                        except (Centre.DoesNotExist, ValueError, TypeError):
                            pass

                    # Get or create Final Exam mark record
                    final_mark, created = FinalExamMark.objects.get_or_create(
                        student=student,
                        course=course,
                        semester=semester,
                        defaults={'marked_by': teacher}
                    )

                    if notes_only_request:
                        if 'notes' in marks_data:
                            final_mark.notes = marks_data.get('notes', '') or ''
                        final_mark.save()
                        rows_updated += 1
                        continue

                    def _post_exam_absent(val):
                        if val is True or val == 'true' or val == '1' or val == 1:
                            return True
                        return False

                    # Any positive final-exam mark means the student is not exam-absent. Without this, a stale
                    # exam_absent=1 in the DB (from a prior AB) blocks all Q/ lab updates: we clear and never
                    # apply the posted marks (affects a subset of students but not all).
                    has_positive_final = False
                    if not course.is_lab:
                        for i in range(1, 8):
                            k = f'q{i}'
                            if k in marks_data and _parse_final_exam_q_mark(marks_data.get(k)) is not None:
                                has_positive_final = True
                                break
                    else:
                        lab_prefix = 'teacher1' if teacher_role != 'teacher2' else 'teacher2'
                        ps_key = f'{lab_prefix}_lab_final_exam_mark'
                        viv_key = f'{lab_prefix}_lab_viva_mark'
                        if ps_key not in marks_data and 'lab_final_exam_mark' in marks_data:
                            marks_data = {**marks_data, ps_key: marks_data.get('lab_final_exam_mark')}
                        if viv_key not in marks_data and 'lab_viva_mark' in marks_data:
                            marks_data = {**marks_data, viv_key: marks_data.get('lab_viva_mark')}
                        has_positive_final = False
                        for k in (ps_key, viv_key, 'lab_final_exam_mark', 'lab_viva_mark'):
                            if k not in marks_data:
                                continue
                            raw = marks_data.get(k)
                            if raw is None:
                                continue
                            if isinstance(raw, str) and raw.strip() == '':
                                continue
                            has_positive_final = True
                            break
                    if has_positive_final:
                        final_mark.exam_absent = False
                    elif 'exam_absent' in marks_data:
                        final_mark.exam_absent = _post_exam_absent(marks_data.get('exam_absent'))
                    # else: leave exam_absent as loaded (e.g. not mentioned in this POST)
                    exam_absent = final_mark.exam_absent
                    if exam_absent:
                        final_mark.clear_numeric_exam_fields()
                        final_mark.marked_by = teacher
                    else:
                        # Update marks based on course type
                        if course.is_lab:
                            lab_prefix = 'teacher1' if teacher_role != 'teacher2' else 'teacher2'
                            ps_key = f'{lab_prefix}_lab_final_exam_mark'
                            viv_key = f'{lab_prefix}_lab_viva_mark'
                            if ps_key not in marks_data and 'lab_final_exam_mark' in marks_data:
                                marks_data = {**marks_data, ps_key: marks_data.get('lab_final_exam_mark')}
                            if viv_key not in marks_data and 'lab_viva_mark' in marks_data:
                                marks_data = {**marks_data, viv_key: marks_data.get('lab_viva_mark')}
                            if semester.curriculum_id and semester.curriculum.code == 'OLD':
                                lab_final_max = 60.0
                                pr = _parse_optional_mark_float(marks_data.get(ps_key), lab_final_max)
                                from decimal import Decimal
                                setattr(
                                    final_mark,
                                    ps_key,
                                    None if pr is None else Decimal(str(max(0.0, min(pr, lab_final_max)))),
                                )
                                setattr(final_mark, viv_key, None)
                            else:
                                pr = _parse_optional_mark_float(marks_data.get(ps_key), 20.0)
                                from decimal import Decimal
                                setattr(
                                    final_mark,
                                    ps_key,
                                    None if pr is None else Decimal(str(max(0.0, min(pr, 20.0)))),
                                )
                                if _user_can_edit_lab_viva(
                                    request.user,
                                    teacher=get_teacher_from_user(request.user),
                                    semester=semester,
                                    course=course,
                                    centre=centre_id_for_perm,
                                ):
                                    viv = _parse_optional_mark_float(marks_data.get(viv_key), 5.0)
                                    setattr(
                                        final_mark,
                                        viv_key,
                                        None if viv is None else Decimal(str(max(0.0, min(viv, 5.0)))),
                                    )
                            if not apply_assign_from_post:
                                if lab_prefix == 'teacher1':
                                    final_mark.teacher1_evaluator = teacher
                                else:
                                    final_mark.teacher2_evaluator = teacher
                            final_mark.marked_by = teacher
                        else:
                            # Theory: Group A = Q1–Q3 (≤2 with marks), Group B = Q4–Q6 (≤2 with marks), Group C = Q7
                            merged_q = _merge_theory_q_state(marks_data, final_mark, teacher_role)
                            if not _theory_q_group_rules_ok(merged_q):
                                return JsonResponse(
                                    {
                                        'error': (
                                            'Theory final rules: at most 2 of Q1–Q3 and at most 2 of Q4–Q6 can have marks '
                                            'entered (including 0). Adjust Group A, Group B, and Q7, then save again.'
                                        )
                                    },
                                    status=400,
                                )
                            # 7 question sets (see _apply_theory_final_exam_q_fields: key must be
                            # present; omitted keys are left unchanged to avoid clearing other Qs on partial save.)
                            if teacher_role == 'teacher1':
                                _apply_theory_final_exam_q_fields(final_mark, 'teacher1', marks_data)
                                if not apply_assign_from_post:
                                    final_mark.teacher1_evaluator = teacher
                            elif teacher_role == 'teacher2':
                                _apply_theory_final_exam_q_fields(final_mark, 'teacher2', marks_data)
                                if not apply_assign_from_post:
                                    final_mark.teacher2_evaluator = teacher
                            elif teacher_role == 'teacher3':
                                _apply_theory_final_exam_q_fields(final_mark, 'teacher3', marks_data)
                                if not apply_assign_from_post:
                                    final_mark.teacher3_evaluator = teacher

                            final_mark.marked_by = teacher

                    # Update notes if provided
                    if 'notes' in marks_data:
                        final_mark.notes = marks_data.get('notes', '')

                    # Save (this will trigger auto-calculation of totals and discrepancy check)
                    final_mark.save()
                    rows_updated += 1

                except Student.DoesNotExist:
                    continue
            if not notes_only_request and students_marks and rows_updated == 0:
                return JsonResponse(
                    {
                        'error': (
                            'No final exam rows were saved. Check that students exist, IDs match the table, and '
                            'the selected study centre is correct. If the problem continues, try Save again after '
                            'a full page reload or ask an administrator to grant “Can manage semester final marks” '
                            'or add you as a final examiner for this course.'
                        )
                    },
                    status=400,
                )
        elif not notes_only_request:
            return JsonResponse(
                {'error': 'No students_data in request. If you use an ad blocker or privacy tool, try disabling it for this page.'},
                status=400,
            )
        
        msg = 'Remarks saved successfully' if notes_only_request else 'Final exam marks saved successfully'
        return JsonResponse({'success': True, 'message': msg})
        
    except (Semester.DoesNotExist, Course.DoesNotExist):
        return JsonResponse({'error': 'Invalid semester or course'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def assign_evaluator(request):
    """
    Assign or change evaluators for final exam marks (admin only)
    """
    if not user_can_assign_examiners(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        semester_id = request.POST.get('semester_id')
        course_id = request.POST.get('course_id')
        evaluator_number = request.POST.get('evaluator_number')
        teacher_id = request.POST.get('teacher_id')
        
        if not all([semester_id, course_id, evaluator_number, teacher_id]):
            return JsonResponse({'error': 'Missing required parameters'}, status=400)

        cid = (request.POST.get('centre_id') or request.POST.get('centre') or '').strip()
        if not cid:
            return JsonResponse({'error': 'Study centre is required to assign examiners'}, status=400)
        
        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        bad = _reject_old_curriculum_for_marks_json(semester, course)
        if bad:
            return bad
        teacher = Teacher.objects.get(id=teacher_id)
        evaluator_number = int(evaluator_number)

        if course.is_lab and evaluator_number == 3:
            return JsonResponse(
                {'error': 'Lab courses use Internal and External examiners only.'},
                status=400,
            )
        
        if evaluator_number not in [1, 2, 3]:
            return JsonResponse({'error': 'Invalid examiner number'}, status=400)

        try:
            centre = Centre.objects.get(id=int(cid))
        except (Centre.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'error': 'Invalid study centre'}, status=400)

        sc = SemesterCourse.objects.filter(
            semester=semester, course=course, centre=centre
        ).first()
        if not sc:
            return JsonResponse(
                {
                    'error': 'No Semester course row for this semester, course, and study centre.',
                },
                status=400,
            )

        if evaluator_number == 1:
            sc.final_exam_evaluator1 = teacher
        elif evaluator_number == 2:
            sc.final_exam_evaluator2 = teacher
        else:
            sc.final_exam_evaluator3 = teacher
        sc.save()

        _sync_final_exam_evaluators_from_semester_course(semester, course, centre)

        students = Student.objects.filter(semesters=semester)
        students = filter_students_queryset_by_centre(students, str(centre.id))
        updated_count = students.count()

        return JsonResponse({
            'success': True,
            'message': f'Examiner {evaluator_number} saved on Semester course and synced to {updated_count} student(s)',
            'teacher_name': teacher.name
        })
        
    except (Semester.DoesNotExist, Course.DoesNotExist, Teacher.DoesNotExist) as e:
        return JsonResponse({'error': str(e)}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def assign_chairman(request):
    """Assign examination chairman or members for lab course viva (per semester/course/centre)."""
    # Marks page shows this UI to admins who can assign examiners; allow the same here.
    if not (
        user_can_assign_chairman(request.user)
        or user_can_assign_examiners(request.user)
    ):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    assignment_fields = {
        'chairman': 'lab_examination_chairman',
        'member1': 'lab_examination_member1',
        'member2': 'lab_examination_member2',
        'member3': 'lab_examination_member3',
        'member4': 'lab_examination_member4',
    }

    try:
        semester_id = request.POST.get('semester_id')
        course_id = request.POST.get('course_id')
        teacher_id = (request.POST.get('teacher_id') or '').strip()
        assignment_type = (request.POST.get('assignment_type') or 'chairman').strip().lower()

        if assignment_type not in assignment_fields:
            return JsonResponse({'error': 'Invalid assignment type'}, status=400)

        if not semester_id or not course_id:
            return JsonResponse({'error': 'Missing required parameters'}, status=400)
        if assignment_type == 'chairman' and not teacher_id:
            return JsonResponse({'error': 'Teacher is required for chairman'}, status=400)

        cid = (request.POST.get('centre_id') or request.POST.get('centre') or '').strip()
        if not cid:
            return JsonResponse({'error': 'Study centre is required to assign chairman'}, status=400)

        semester = Semester.objects.get(id=semester_id)
        course = Course.objects.get(id=course_id)
        if not course.is_lab:
            return JsonResponse({'error': 'Chairman can only be assigned for lab courses'}, status=400)

        bad = _reject_old_curriculum_for_marks_json(semester, course)
        if bad:
            return bad

        teacher = None
        if teacher_id:
            teacher = Teacher.objects.get(id=teacher_id)

        try:
            centre = Centre.objects.get(id=int(cid))
        except (Centre.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'error': 'Invalid study centre'}, status=400)

        sc = SemesterCourse.objects.filter(
            semester=semester, course=course, centre=centre
        ).first()
        if not sc:
            return JsonResponse(
                {'error': 'No Semester course row for this semester, course, and study centre.'},
                status=400,
            )

        field_name = assignment_fields[assignment_type]
        setattr(sc, field_name, teacher)
        sc.save(update_fields=[field_name])

        labels = {
            'chairman': 'Lab examination chairman',
            'member1': 'Member 1',
            'member2': 'Member 2',
            'member3': 'Member 3',
            'member4': 'Member 4',
        }
        if teacher:
            message = f'{labels[assignment_type]} saved.'
        else:
            message = f'{labels[assignment_type]} cleared.'

        return JsonResponse({
            'success': True,
            'message': message,
            'teacher_name': teacher.name if teacher else '',
        })

    except (Semester.DoesNotExist, Course.DoesNotExist, Teacher.DoesNotExist) as e:
        return JsonResponse({'error': str(e)}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
