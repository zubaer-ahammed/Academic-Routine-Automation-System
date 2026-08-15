"""Semester tabulation sheet exports (PDF and Excel)."""

from __future__ import annotations

import io
import math
import xlsxwriter
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import Centre, FinalExamMark, Semester, SemesterCourse, Student
from .views import (
    _ca_marks_dict_for_students_course_semester,
    _ca_total_ceil_int,
    _excel_apply_landscape_a4_print_setup,
    _is_ca_management_admin,
    _lab_final_exam_cap_for_summary,
    _make_deferred_footer_canvas_class,
    filter_students_queryset_by_centre,
)

TABULATION_LOGO_PATH = settings.BASE_DIR / 'bou_routines_app' / 'static' / 'bou_logo_icon.png'
PROGRAM_NAME = 'B.Sc in Computer Science and Engineering'
_LOGO_MAX_SIDE = 62


def _tabulation_logo_flowable(max_width=_LOGO_MAX_SIDE, max_height=_LOGO_MAX_SIDE):
    """Load the BOU mark at its native aspect ratio (no square stretch)."""
    if not TABULATION_LOGO_PATH.exists():
        return ''
    logo = Image(str(TABULATION_LOGO_PATH))
    native_w = float(logo.imageWidth or 0)
    native_h = float(logo.imageHeight or 0)
    if native_w <= 0 or native_h <= 0:
        return logo
    scale = min(max_width / native_w, max_height / native_h)
    logo.drawWidth = native_w * scale
    logo.drawHeight = native_h * scale
    return logo

# UGC / new-curriculum numerical grade → letter grade → grade point
_GRADE_BANDS = (
    (80, 'A+', 4.00),
    (75, 'A', 3.75),
    (70, 'A-', 3.50),
    (65, 'B+', 3.25),
    (60, 'B', 3.00),
    (55, 'B-', 2.75),
    (50, 'C+', 2.50),
    (45, 'C', 2.25),
    (40, 'D', 2.00),
)

TABULATION_ABBREVIATIONS = (
    ('SF', 'Semester Final'),
    ('CA', 'Continuous Assessment'),
    ('IC', 'Incomplete'),
    ('AB', 'Absent'),
    ('NS', 'Not Submitted'),
    ('N/A', 'Not Applicable'),
)

def letter_and_grade_point(percent):
    """UGC scale. Pass (D or better) at 40% of the course total."""
    try:
        p = float(percent)
    except (TypeError, ValueError):
        return 'F', 0.00
    for threshold, letter, gp in _GRADE_BANDS:
        if p >= threshold:
            return letter, gp
    return 'F', 0.00


def course_percent(total, total_max):
    """Convert marks to a 0–100 percentage of the course maximum."""
    try:
        mx = float(total_max)
        tot = float(total)
    except (TypeError, ValueError):
        return 0.0
    if mx <= 0:
        return 0.0
    return min(100.0, max(0.0, (tot / mx) * 100.0))


def earned_credits(course_credits, grade_point):
    """Credits counted for a passed course (GP > 0). Failed / absent courses earn 0."""
    try:
        gp = float(grade_point)
        credits = float(course_credits or 0)
    except (TypeError, ValueError):
        return 0.0
    if gp <= 0:
        return 0.0
    return credits


def format_course_credits(credits):
    try:
        value = float(credits or 0)
    except (TypeError, ValueError):
        return '0.0'
    if value == int(value):
        return f'{int(value)}.0'
    return f'{value:.2f}'.rstrip('0').rstrip('.')


def _is_old_curriculum(semester):
    curriculum = getattr(semester, 'curriculum', None)
    return bool(curriculum and curriculum.code == 'OLD')


def course_component_maxima(course, semester):
    """
    SF / CA / Total maxima from curriculum rules used elsewhere in marks.
    Theory: SF 70 + CA weights. Lab: SF cap from final-exam UI + lab CA total.
    Project: CA only (100).
    """
    if getattr(course, 'course_type', None) == 'PROJECT':
        ca_max = (
            int(course.effective_project_supervisor_weight or 0)
            + int(course.effective_project_evaluation_weight or 0)
            + int(course.effective_project_presentation_weight or 0)
        )
        return 0, ca_max, ca_max

    if course.is_lab:
        sf_max = int(_lab_final_exam_cap_for_summary(course, semester) or 0)
        ca_max = int(course.effective_lab_ca_total_marks or 0)
        return sf_max, ca_max, sf_max + ca_max

    ca_max = (
        int(course.effective_ca_attendance_weight or 0)
        + int(course.effective_ca_assignment_weight or 0)
        + int(
            course.effective_ca_quiz_weight
            if _is_old_curriculum(semester)
            else course.effective_ca_midterm_weight
        )
    )
    sf_max = 70
    return sf_max, ca_max, sf_max + ca_max


def _centre_label(centre):
    if not centre:
        return ''
    name = (centre.name or '').strip()
    code = (centre.code or '').strip()
    if name and code and code not in name:
        return f'{name} ({code})'
    return name or code


def _semester_year_label(semester):
    return (semester.semester_full_name or semester.name or '').strip()


def _ordered_semester_courses(semester, centre):
    qs = SemesterCourse.objects.filter(semester=semester).select_related('course')
    if centre:
        qs = qs.filter(centre=centre)
    courses = []
    seen = set()
    for row in qs.order_by('course__code'):
        if row.course_id in seen:
            continue
        seen.add(row.course_id)
        courses.append(row.course)
    return courses


def _tabulation_students(semester, centre_id, session):
    students = Student.objects.filter(semesters=semester).extra(
        select={
            'first_two_digits': "CAST(SUBSTR(bou_routines_app_student.id, 1, 2) AS INTEGER)",
            'last_three_digits': "CAST(SUBSTR(bou_routines_app_student.id, -3) AS INTEGER)",
        }
    ).order_by('-first_two_digits', 'last_three_digits')
    students = filter_students_queryset_by_centre(students, centre_id)
    if (session or '').strip():
        students = students.filter(session=session.strip())
    return list(students)


def _sf_ceil_int(final_mark):
    if not final_mark:
        return 0
    try:
        return int(math.ceil(max(0.0, float(final_mark.final_exam_total or 0))))
    except (TypeError, ValueError, OverflowError):
        return 0


def _course_cell(student, course, semester, ca_by_student, fe_by_student):
    """One course block: SF, CA, Total, GP (AB when semester-final absent)."""
    sf_max, ca_max, total_max = course_component_maxima(course, semester)
    credits = float(course.credits or 0)
    cam = ca_by_student.get(student.id)
    fe = fe_by_student.get(student.id)
    ca_val = _ca_total_ceil_int(cam)
    if fe and getattr(fe, 'exam_absent', False):
        return {
            'sf': 'AB',
            'ca': ca_val,
            'total': 'AB',
            'gp': 'AB',
            'letter': 'F',
            'gp_value': 0.00,
            'earned_credits': 0.0,
            'course_credits': credits,
            'sf_max': sf_max,
            'ca_max': ca_max,
            'total_max': total_max,
        }
    sf_val = _sf_ceil_int(fe)
    total_val = sf_val + ca_val
    percent = course_percent(total_val, total_max)
    letter, gp = letter_and_grade_point(percent)
    return {
        'sf': sf_val,
        'ca': ca_val,
        'total': total_val,
        'gp': f'{gp:.2f}',
        'letter': letter,
        'gp_value': gp,
        'earned_credits': earned_credits(credits, gp),
        'course_credits': credits,
        'sf_max': sf_max,
        'ca_max': ca_max,
        'total_max': total_max,
    }


def build_tabulation_payload(semester, centre, session):
    courses = _ordered_semester_courses(semester, centre)
    centre_id = centre.id if centre else None
    students = _tabulation_students(semester, centre_id, session)
    ca_by_course = {}
    fe_by_course = {}
    for course in courses:
        ca_by_course[course.id] = _ca_marks_dict_for_students_course_semester(
            students, course, semester
        )
        fe_by_course[course.id] = {
            m.student_id: m
            for m in FinalExamMark.objects.filter(
                student__in=students,
                course=course,
                semester=semester,
            )
        }

    rows = []
    for student in students:
        cells = []
        gp_credit_sum = 0.0
        credit_sum = 0.0
        earned_sum = 0.0
        for course in courses:
            cell = _course_cell(
                student,
                course,
                semester,
                ca_by_course[course.id],
                fe_by_course[course.id],
            )
            cells.append(cell)
            credit_sum += cell['course_credits']
            gp_credit_sum += cell['gp_value'] * cell['course_credits']
            earned_sum += cell['earned_credits']
        sgpa = (gp_credit_sum / credit_sum) if credit_sum else 0.0
        rows.append(
            {
                'student': student,
                'cells': cells,
                'earned_credits': earned_sum,
                'sgpa': sgpa,
            }
        )

    return {
        'semester': semester,
        'centre': centre,
        'session_label': (session or '').strip() or 'ALL',
        'courses': courses,
        'students': students,
        'rows': rows,
        'course_maxima': [course_component_maxima(c, semester) for c in courses],
    }


def _tabulation_query_redirect():
    return redirect('ca-management')


def _load_tabulation_context(request):
    if not _is_ca_management_admin(request):
        messages.error(request, "You don't have permission to export the Tabulation Sheet.")
        return None

    semester_id = request.GET.get('semester')
    centre_id = request.GET.get('centre')
    session = (request.GET.get('session') or '').strip()

    if not semester_id:
        messages.error(request, 'Please select a semester to export the Tabulation Sheet.')
        return None

    try:
        semester = Semester.objects.select_related('curriculum').get(id=semester_id)
    except (Semester.DoesNotExist, ValueError, TypeError):
        messages.error(request, 'Selected semester was not found.')
        return None

    centre = None
    if centre_id:
        try:
            centre = Centre.objects.get(id=int(centre_id))
        except (Centre.DoesNotExist, ValueError, TypeError):
            centre = None

    if not centre:
        messages.error(request, 'Please select a study centre to export the Tabulation Sheet.')
        return None

    payload = build_tabulation_payload(semester, centre, session)
    if not payload['courses']:
        messages.error(
            request,
            'No courses are assigned to this semester and study centre.',
        )
        return None
    return payload


def _tabulation_header_flowables(payload, available_width):
    """Match the official sample: logo | centered titles | abbreviation legend, then boxed metadata."""
    title_style = ParagraphStyle(
        'TabTitle',
        fontName='Times-Bold',
        fontSize=18,
        alignment=TA_CENTER,
        leading=22,
        spaceAfter=0,
        spaceBefore=0,
    )
    addr_style = ParagraphStyle(
        'TabAddr',
        fontName='Times-Roman',
        fontSize=11,
        alignment=TA_CENTER,
        leading=14,
        spaceAfter=0,
        spaceBefore=1,
    )
    sheet_style = ParagraphStyle(
        'TabSheet',
        fontName='Times-Bold',
        fontSize=14,
        alignment=TA_CENTER,
        leading=18,
        spaceAfter=0,
        spaceBefore=4,
    )
    legend_style = ParagraphStyle(
        'TabLegend',
        fontName='Helvetica',
        fontSize=8,
        alignment=TA_LEFT,
        leading=11,
        spaceAfter=0,
        spaceBefore=0,
    )
    info_label_style = ParagraphStyle(
        'TabInfoLabel',
        fontName='Helvetica-Bold',
        fontSize=9,
        alignment=TA_LEFT,
        leading=12,
    )
    info_value_style = ParagraphStyle(
        'TabInfoValue',
        fontName='Helvetica',
        fontSize=9,
        alignment=TA_LEFT,
        leading=12,
    )

    try:
        logo_cell = _tabulation_logo_flowable()
    except Exception:
        logo_cell = ''

    titles = [
        Paragraph('Bangladesh Open University', title_style),
        Paragraph('Gazipur-1705, Bangladesh', addr_style),
        Paragraph('<u>Tabulation Sheet</u>', sheet_style),
    ]
    legend_bits = [
        Paragraph(f'{code} = {meaning}', legend_style)
        for code, meaning in TABULATION_ABBREVIATIONS
    ]
    legend_inner = Table([[bit] for bit in legend_bits], colWidths=[148])
    legend_inner.setStyle(
        TableStyle(
            [
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]
        )
    )

    logo_w, legend_w = 68, 152
    title_w = max(200.0, available_width - logo_w - legend_w)
    banner = Table(
        [[logo_cell, titles, legend_inner]],
        colWidths=[logo_w, title_w, legend_w],
    )
    banner.setStyle(
        TableStyle(
            [
                ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
                ('VALIGN', (1, 0), (1, 0), 'MIDDLE'),
                ('VALIGN', (2, 0), (2, 0), 'TOP'),
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
                ('LEFTPADDING', (0, 0), (0, 0), 0),
                ('RIGHTPADDING', (2, 0), (2, 0), 0),
                ('LEFTPADDING', (1, 0), (2, 0), 6),
                ('RIGHTPADDING', (0, 0), (1, 0), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]
        )
    )

    semester = payload['semester']
    centre_text = _centre_label(payload['centre'])

    def kv_pair(label, value):
        return (
            Paragraph(label, info_label_style),
            Paragraph(f': {value or ""}', info_value_style),
        )

    info_data = [
        kv_pair('Program', PROGRAM_NAME)
        + kv_pair('Session', payload['session_label']),
        kv_pair('SC Code &amp; Name', centre_text)
        + kv_pair('Year &amp; Semester', _semester_year_label(semester)),
        kv_pair('EC Code &amp; Name', centre_text)
        + kv_pair('Term', semester.term or ''),
    ]
    half = available_width / 2.0
    left_label_w, right_label_w = 102, 92
    info_tbl = Table(
        info_data,
        colWidths=[left_label_w, half - left_label_w, right_label_w, half - right_label_w],
    )
    info_tbl.setStyle(
        TableStyle(
            [
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('BOX', (0, 0), (-1, -1), 0.8, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]
        )
    )
    return [banner, Spacer(1, 8), info_tbl, Spacer(1, 6)]


class _VerticalHeader(Flowable):
    """90° counter-clockwise text for the Components row (SF, CA, Total, GP)."""

    def __init__(self, text, font_name='Helvetica-Bold', font_size=7):
        super().__init__()
        self.text = text
        self.font_name = font_name
        self.font_size = font_size
        self._text_w = stringWidth(text, font_name, font_size)
        self.width = font_size + 3
        self.height = self._text_w + 8

    def wrap(self, availWidth, availHeight):
        if availWidth:
            self.width = min(max(self.width, 10), availWidth)
        return self.width, self.height

    def draw(self):
        canv = self.canv
        canv.saveState()
        canv.setFont(self.font_name, self.font_size)
        canv.translate(self.width / 2.0 + self.font_size * 0.32, 4)
        canv.rotate(90)
        canv.drawString(0, 0, self.text)
        canv.restoreState()


def _tabulation_table_col_widths(n_courses, available_width):
    id_w, name_w = 50, 122
    rest = max(80.0, available_width - id_w - name_w)
    n_sub = max(1, n_courses * 4)
    sub_w = rest / n_sub
    return [id_w, name_w] + [sub_w] * (n_courses * 4)


def _build_tabulation_table(payload, available_width):
    courses = payload['courses']
    maxima = payload['course_maxima']
    hdr = ParagraphStyle(
        'TabHdr',
        fontName='Helvetica-Bold',
        fontSize=6.5,
        alignment=TA_CENTER,
        leading=8,
        spaceBefore=0,
        spaceAfter=0,
    )
    hdr_small = ParagraphStyle(
        'TabHdrSm',
        parent=hdr,
        fontSize=6,
        leading=7.5,
    )
    name_style = ParagraphStyle(
        'TabName',
        fontName='Helvetica',
        fontSize=6.5,
        alignment=TA_LEFT,
        leading=8,
        spaceBefore=0,
        spaceAfter=0,
    )
    id_style = ParagraphStyle(
        'TabId',
        fontName='Helvetica-Bold',
        fontSize=7,
        alignment=TA_CENTER,
        leading=8.5,
    )
    cell_style = ParagraphStyle(
        'TabCell',
        fontName='Helvetica',
        fontSize=6.5,
        alignment=TA_CENTER,
        leading=8,
    )
    label_style = ParagraphStyle(
        'TabStub',
        fontName='Helvetica-Bold',
        fontSize=6.5,
        alignment=TA_CENTER,
        leading=8,
        spaceBefore=0,
        spaceAfter=0,
    )

    n_courses = len(courses)
    row0 = [Paragraph('Course Code &amp; Title', label_style), '']
    row1 = [Paragraph('Credit', label_style), '']
    row2 = [Paragraph('Components', label_style), '']
    row3 = [Paragraph('Weightage', label_style), '']
    row4 = [Paragraph("Student's ID", hdr), Paragraph('Name', hdr)]
    for course, (sf_max, ca_max, total_max) in zip(courses, maxima):
        row0.extend([Paragraph(course.code, hdr), '', '', ''])
        row1.extend([Paragraph(format_course_credits(course.credits), hdr), '', '', ''])
        row2.extend(
            [
                _VerticalHeader('SF'),
                _VerticalHeader('CA'),
                _VerticalHeader('Total'),
                _VerticalHeader('GP'),
            ]
        )
        row3.extend(
            [
                Paragraph(str(sf_max), hdr_small),
                Paragraph(str(ca_max), hdr_small),
                Paragraph(str(total_max), hdr_small),
                Paragraph('4.00', hdr_small),
            ]
        )
        row4.extend(['', '', '', ''])

    table_data = [row0, row1, row2, row3, row4]
    for row in payload['rows']:
        student = row['student']
        data_row = [
            Paragraph(str(student.id), id_style),
            Paragraph((student.name or '').upper(), name_style),
        ]
        for cell in row['cells']:
            data_row.extend(
                [
                    Paragraph(str(cell['sf']), cell_style),
                    Paragraph(str(cell['ca']), cell_style),
                    Paragraph(str(cell['total']), cell_style),
                    Paragraph(str(cell['gp']), cell_style),
                ]
            )
        table_data.append(data_row)

    col_widths = _tabulation_table_col_widths(n_courses, available_width)
    spans = [
        ('SPAN', (0, 0), (1, 0)),
        ('SPAN', (0, 1), (1, 1)),
        ('SPAN', (0, 2), (1, 2)),
        ('SPAN', (0, 3), (1, 3)),
    ]
    for i in range(n_courses):
        c = 2 + i * 4
        spans.append(('SPAN', (c, 0), (c + 3, 0)))
        spans.append(('SPAN', (c, 1), (c + 3, 1)))

    style_cmds = list(spans) + [
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
        ('FONTNAME', (0, 0), (-1, 4), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, 4), 2),
        ('BOTTOMPADDING', (0, 0), (-1, 4), 2),
        ('TOPPADDING', (0, 2), (-1, 2), 3),
        ('BOTTOMPADDING', (0, 2), (-1, 2), 3),
        ('TOPPADDING', (0, 5), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 5), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 1.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1.5),
        ('ALIGN', (1, 5), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 5), (0, -1), 'Helvetica-Bold'),
    ]
    tbl = Table(table_data, colWidths=col_widths, repeatRows=5)
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _draw_tabulation_pdf_footer(left_margin, right_margin):
    def _draw(cnv, page_num, total_pages):
        pw, _ph = landscape(A4)
        footer_y_line = 50
        footer_y_text = 36
        cnv.saveState()
        cnv.setFillColor(colors.black)
        cnv.setStrokeColor(colors.black)
        cnv.setLineWidth(0.8)
        cnv.setFont('Helvetica', 8)
        cnv.drawCentredString(pw / 2.0, footer_y_text, f'Page {page_num} of {total_pages}')
        sig_w = 150
        right_x = pw - right_margin
        cnv.line(right_x - sig_w, footer_y_line, right_x, footer_y_line)
        cnv.setFont('Helvetica-Bold', 8)
        cnv.drawCentredString(right_x - sig_w / 2.0, footer_y_text, 'Chairman')
        cnv.setFont('Helvetica', 8)
        cnv.drawCentredString(
            right_x - sig_w / 2.0, footer_y_text - 11, 'Examination Committee'
        )
        cnv.restoreState()

    return _draw


@login_required
def export_tabulation_pdf(request):
    try:
        payload = _load_tabulation_context(request)
        if payload is None:
            return _tabulation_query_redirect()

        left_m, right_m, top_m, bottom_m = 18, 18, 16, 78
        page_width, _page_height = landscape(A4)
        available_width = page_width - left_m - right_m

        elements = []
        elements.extend(_tabulation_header_flowables(payload, available_width))
        elements.append(_build_tabulation_table(payload, available_width))

        canvas_cls = _make_deferred_footer_canvas_class(
            _draw_tabulation_pdf_footer(left_m, right_m)
        )
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=left_m,
            rightMargin=right_m,
            topMargin=top_m,
            bottomMargin=bottom_m,
        )
        doc.build(elements, canvasmaker=canvas_cls)

        semester = payload['semester']
        centre = payload['centre']
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        fname = f'Tabulation_Sheet_{semester.name}_{centre.code}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response
    except Exception as e:
        return HttpResponse(f'Error generating Tabulation Sheet PDF: {str(e)}', status=500)


def _excel_tabulation_header_rows(payload):
    """Return (rows, merge_ranges) matching the official 5-row sample header."""
    courses = payload['courses']
    maxima = payload['course_maxima']
    row0 = ['Course Code & Title', '']
    row1 = ['Credit', '']
    row2 = ['Components', '']
    row3 = ['Weightage', '']
    row4 = ["Student's ID", 'Name']
    for course, (sf_max, ca_max, total_max) in zip(courses, maxima):
        row0.extend([course.code, '', '', ''])
        row1.extend([format_course_credits(course.credits), '', '', ''])
        row2.extend(['SF', 'CA', 'Total', 'GP'])
        row3.extend([str(sf_max), str(ca_max), str(total_max), '4.00'])
        row4.extend(['', '', '', ''])
    merges = [(0, 0, 0, 1), (1, 0, 1, 1), (2, 0, 2, 1), (3, 0, 3, 1)]
    for i in range(len(courses)):
        c = 2 + i * 4
        merges.append((0, c, 0, c + 3))
        merges.append((1, c, 1, c + 3))
    return [row0, row1, row2, row3, row4], merges


@login_required
def export_tabulation_excel(request):
    try:
        payload = _load_tabulation_context(request)
        if payload is None:
            return _tabulation_query_redirect()

        semester = payload['semester']
        centre = payload['centre']
        courses = payload['courses']
        n_cols = 2 + len(courses) * 4
        last_col = n_cols - 1

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Tabulation Sheet')

        title_format = workbook.add_format(
            {
                'bold': True,
                'font_size': 18,
                'align': 'center',
                'valign': 'vcenter',
                'font_name': 'Times New Roman',
            }
        )
        addr_format = workbook.add_format(
            {
                'font_size': 11,
                'align': 'center',
                'valign': 'vcenter',
                'font_name': 'Times New Roman',
            }
        )
        sheet_format = workbook.add_format(
            {
                'bold': True,
                'font_size': 14,
                'align': 'center',
                'valign': 'vcenter',
                'font_name': 'Times New Roman',
                'underline': True,
            }
        )
        legend_format = workbook.add_format({'font_size': 8, 'align': 'left', 'valign': 'top'})
        header_format = workbook.add_format(
            {
                'bold': True,
                'font_size': 8,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'text_wrap': True,
            }
        )
        stub_format = workbook.add_format(
            {
                'bold': True,
                'font_size': 8,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'text_wrap': True,
            }
        )
        rot_header_format = workbook.add_format(
            {
                'bold': True,
                'font_size': 8,
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'rotation': 90,
            }
        )
        cell_format = workbook.add_format(
            {'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 8}
        )
        id_format = workbook.add_format(
            {
                'align': 'center',
                'valign': 'vcenter',
                'border': 1,
                'font_size': 9,
                'bold': True,
            }
        )
        name_format = workbook.add_format(
            {
                'align': 'left',
                'valign': 'vcenter',
                'border': 1,
                'font_size': 8,
            }
        )

        row = 0
        if TABULATION_LOGO_PATH.exists():
            worksheet.set_row(row, 40)
            worksheet.insert_image(
                row,
                0,
                str(TABULATION_LOGO_PATH),
                {'x_scale': 0.28, 'y_scale': 0.28, 'x_offset': 4, 'y_offset': 2},
            )

        title_last = max(1, last_col - 1)
        worksheet.merge_range(row, 1, row, title_last, 'Bangladesh Open University', title_format)
        row += 1
        worksheet.merge_range(row, 1, row, title_last, 'Gazipur-1705, Bangladesh', addr_format)
        row += 1
        worksheet.merge_range(row, 1, row, title_last, 'Tabulation Sheet', sheet_format)

        legend_col = last_col
        for legend_row, (code, meaning) in enumerate(TABULATION_ABBREVIATIONS):
            worksheet.write(legend_row, legend_col, f'{code} = {meaning}', legend_format)

        row = max(row + 2, len(TABULATION_ABBREVIATIONS) + 1)
        centre_text = _centre_label(centre)
        info_left_last = max(1, last_col // 2)
        info_right_first = info_left_last + 1
        left_lines = [
            f'Program : {PROGRAM_NAME}',
            f'SC Code & Name : {centre_text}',
            f'EC Code & Name : {centre_text}',
        ]
        right_lines = [
            f'Session : {payload["session_label"]}',
            f'Year & Semester : {_semester_year_label(semester)}',
            f'Term : {semester.term or ""}',
        ]
        info_start = row
        for offset, (left_text, right_text) in enumerate(zip(left_lines, right_lines)):
            r = info_start + offset
            box_edges = {
                'font_size': 9,
                'align': 'left',
                'valign': 'vcenter',
                'top': 1 if offset == 0 else 0,
                'bottom': 1 if offset == 2 else 0,
            }
            left_fmt = workbook.add_format({**box_edges, 'left': 1, 'right': 0})
            right_fmt = workbook.add_format({**box_edges, 'left': 0, 'right': 1})
            if info_left_last > 0:
                worksheet.merge_range(r, 0, r, info_left_last, left_text, left_fmt)
            else:
                worksheet.write(r, 0, left_text, left_fmt)
            if info_right_first < last_col:
                worksheet.merge_range(r, info_right_first, r, last_col, right_text, right_fmt)
            else:
                worksheet.write(r, last_col, right_text, right_fmt)
        row = info_start + 4

        header_rows, merges = _excel_tabulation_header_rows(payload)
        table_start = row
        merged_cells = set()
        for r1, c1, r2, c2 in merges:
            text = header_rows[r1][c1]
            fmt = stub_format if c1 == 0 and r1 <= 3 else header_format
            worksheet.merge_range(
                table_start + r1, c1, table_start + r2, c2, text, fmt
            )
            for rr in range(r1, r2 + 1):
                for cc in range(c1, c2 + 1):
                    merged_cells.add((rr, cc))
        for r_off, header_row in enumerate(header_rows):
            for col, val in enumerate(header_row):
                if (r_off, col) in merged_cells:
                    continue
                if r_off <= 3 and col <= 1:
                    fmt = stub_format
                elif r_off == 2 and col >= 2:
                    fmt = rot_header_format
                else:
                    fmt = header_format
                if val:
                    worksheet.write(table_start + r_off, col, val, fmt)
                else:
                    worksheet.write_blank(table_start + r_off, col, None, fmt)

        data_start = table_start + 5
        for i, data_row in enumerate(payload['rows']):
            excel_row = data_start + i
            student = data_row['student']
            worksheet.write(excel_row, 0, str(student.id), id_format)
            worksheet.write(excel_row, 1, (student.name or '').upper(), name_format)
            col = 2
            for cell in data_row['cells']:
                worksheet.write(excel_row, col, cell['sf'], cell_format)
                worksheet.write(excel_row, col + 1, cell['ca'], cell_format)
                worksheet.write(excel_row, col + 2, cell['total'], cell_format)
                worksheet.write(excel_row, col + 3, cell['gp'], cell_format)
                col += 4

        last_data_row = data_start + max(len(payload['rows']) - 1, 0)
        worksheet.set_column(0, 0, 12)
        worksheet.set_column(1, 1, 24)
        if n_cols > 2:
            worksheet.set_column(2, last_col, 5)
        worksheet.set_row(table_start, 16)
        worksheet.set_row(table_start + 1, 14)
        worksheet.set_row(table_start + 2, 28)
        worksheet.set_row(table_start + 4, 16)
        worksheet.freeze_panes(data_start, 2)

        footer_row = last_data_row + 3
        worksheet.merge_range(
            footer_row, max(last_col - 3, 0), footer_row, last_col,
            '________________________',
            workbook.add_format({'align': 'center'}),
        )
        worksheet.merge_range(
            footer_row + 1, max(last_col - 3, 0), footer_row + 1, last_col,
            'Chairman',
            workbook.add_format({'align': 'center', 'bold': True, 'font_size': 9}),
        )
        worksheet.merge_range(
            footer_row + 2, max(last_col - 3, 0), footer_row + 2, last_col,
            'Examination Committee',
            workbook.add_format({'align': 'center', 'font_size': 9}),
        )

        _excel_apply_landscape_a4_print_setup(worksheet, footer_row + 2, last_col)
        workbook.close()
        output.seek(0)

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        fname = f'Tabulation_Sheet_{semester.name}_{centre.code}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response
    except Exception as e:
        return HttpResponse(f'Error generating Tabulation Sheet Excel: {str(e)}', status=500)
