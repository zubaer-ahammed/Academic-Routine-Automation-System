from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .models import Centre, Course, Curriculum, Semester, SemesterCourse, Teacher
from .views import (
    _default_new_curriculum,
    _pick_default_term_for_curriculum,
    user_can_assign_chairman,
    user_can_assign_course_teacher,
    user_can_assign_examiners,
    user_is_office_staff,
)


def _assign_permission_denied_redirect(request):
    if user_is_office_staff(request.user):
        return redirect('assign-home')
    return redirect('home')


def _assign_courses_queryset(semester, centre=None, lab_only=False):
    """Courses offered in the selected semester (and study centre, if given)."""
    if not semester:
        return Course.objects.none()
    sc_qs = SemesterCourse.objects.filter(semester=semester)
    if centre:
        sc_qs = sc_qs.filter(centre=centre)
    if lab_only:
        sc_qs = sc_qs.filter(course__is_lab=True)
    course_ids = sc_qs.values_list('course_id', flat=True).distinct()
    return Course.objects.filter(id__in=course_ids).order_by('code')


def _assign_filter_context(request):
    curricula = Curriculum.objects.filter(is_active=True).order_by('name')
    centres = Centre.objects.filter(is_active=True).order_by('name')

    selected_curriculum_id = request.GET.get('curriculum') or request.POST.get('curriculum')
    selected_curriculum = None
    if selected_curriculum_id:
        try:
            selected_curriculum_id = int(selected_curriculum_id)
            selected_curriculum = Curriculum.objects.get(id=selected_curriculum_id)
        except (Curriculum.DoesNotExist, ValueError, TypeError):
            selected_curriculum = None
            selected_curriculum_id = None

    if not selected_curriculum and curricula.exists():
        selected_curriculum, selected_curriculum_id = _default_new_curriculum(curricula)

    selected_term = (request.GET.get('term') or request.POST.get('term') or '').strip()
    if not selected_term and selected_curriculum:
        selected_term = _pick_default_term_for_curriculum(selected_curriculum)

    selected_centre_id = request.GET.get('centre') or request.POST.get('centre')
    selected_centre = None
    if selected_centre_id:
        try:
            selected_centre_id = int(selected_centre_id)
            selected_centre = Centre.objects.get(id=selected_centre_id)
        except (Centre.DoesNotExist, ValueError, TypeError):
            selected_centre = None
            selected_centre_id = None

    if not selected_centre:
        try:
            selected_centre = Centre.objects.get(code='DRC')
            selected_centre_id = selected_centre.id
        except Centre.DoesNotExist:
            selected_centre = None
            selected_centre_id = None

    semesters = Semester.objects.all()
    if selected_curriculum:
        semesters = semesters.filter(curriculum=selected_curriculum)
    if selected_term:
        semesters = semesters.filter(term=selected_term)
    semesters = semesters.order_by('name')

    selected_semester_id = request.GET.get('semester') or request.POST.get('semester')
    selected_semester = None
    if selected_semester_id:
        try:
            selected_semester_id = int(selected_semester_id)
            selected_semester = Semester.objects.get(id=selected_semester_id)
        except (Semester.DoesNotExist, ValueError, TypeError):
            selected_semester = None
            selected_semester_id = None

    terms = []
    if selected_curriculum:
        terms = sorted(
            {
                (t or '').strip()
                for t in Semester.objects.filter(curriculum=selected_curriculum)
                .exclude(term__isnull=True)
                .exclude(term='')
                .values_list('term', flat=True)
            },
            reverse=True,
        )

    teachers = Teacher.objects.all().order_by('name')
    if selected_centre:
        teachers = teachers.filter(centre=selected_centre)

    return {
        'curricula': curricula,
        'centres': centres,
        'semesters': semesters,
        'terms': terms,
        'teachers': teachers,
        'selected_curriculum': selected_curriculum,
        'selected_curriculum_id': selected_curriculum_id,
        'selected_term': selected_term,
        'selected_centre': selected_centre,
        'selected_centre_id': selected_centre_id,
        'selected_semester': selected_semester,
        'selected_semester_id': selected_semester_id,
        'is_office_staff': user_is_office_staff(request.user),
    }


@login_required
def assign_home(request):
    if user_can_assign_course_teacher(request.user):
        return redirect('assign-course-teacher')
    if user_can_assign_examiners(request.user):
        return redirect('assign-examiners')
    if user_can_assign_chairman(request.user):
        return redirect('assign-chairman')
    messages.error(request, "You don't have permission to access assignment pages.")
    return redirect('logout')


@login_required
@require_http_methods(['GET', 'POST'])
def assign_course_teacher(request):
    if not user_can_assign_course_teacher(request.user):
        messages.error(request, "You don't have permission to assign course teachers.")
        return _assign_permission_denied_redirect(request)

    context = _assign_filter_context(request)

    semester_courses = []
    if context['selected_semester'] and context['selected_centre']:
        semester_courses = (
            SemesterCourse.objects.filter(
                semester=context['selected_semester'],
                centre=context['selected_centre'],
            )
            .select_related('course', 'teacher', 'course__curriculum')
            .order_by('course__code')
        )

    if request.method == 'POST' and semester_courses:
        updated = 0
        for sc in semester_courses:
            field_name = f'teacher_{sc.id}'
            teacher_id = request.POST.get(field_name, '').strip()
            if not teacher_id:
                continue
            try:
                teacher = Teacher.objects.get(id=int(teacher_id))
                if sc.teacher_id != teacher.id:
                    sc.teacher = teacher
                    sc.save(update_fields=['teacher'])
                    updated += 1
            except (Teacher.DoesNotExist, ValueError, TypeError):
                continue
        if updated:
            messages.success(request, f'Updated course teacher for {updated} course(s).')
        else:
            messages.info(request, 'No course teacher changes were saved.')

        query = request.GET.copy()
        for key in ('curriculum', 'term', 'semester', 'centre'):
            val = request.POST.get(key)
            if val:
                query[key] = val
        return redirect(f"{request.path}?{query.urlencode()}")

    context['semester_courses'] = semester_courses
    return render(request, 'bou_routines_app/assign/course_teacher.html', context)


@login_required
@require_http_methods(['GET'])
def assign_examiners(request):
    if not user_can_assign_examiners(request.user):
        messages.error(request, "You don't have permission to assign examiners.")
        return _assign_permission_denied_redirect(request)

    context = _assign_filter_context(request)

    courses = _assign_courses_queryset(
        context['selected_semester'],
        centre=context['selected_centre'],
    )

    selected_course_id = request.GET.get('course')
    selected_course = None
    semester_course = None
    if selected_course_id and context['selected_semester'] and context['selected_centre']:
        try:
            selected_course_id = int(selected_course_id)
            selected_course = courses.filter(id=selected_course_id).first()
            if not selected_course:
                selected_course_id = None
            else:
                semester_course = SemesterCourse.objects.filter(
                    semester=context['selected_semester'],
                    course=selected_course,
                    centre=context['selected_centre'],
                ).select_related(
                    'final_exam_evaluator1',
                    'final_exam_evaluator2',
                    'final_exam_evaluator3',
                ).first()
        except (ValueError, TypeError):
            selected_course = None
            selected_course_id = None

    context.update({
        'courses': courses,
        'selected_course': selected_course,
        'selected_course_id': selected_course_id,
        'semester_course': semester_course,
        'all_teachers': context['teachers'],
    })
    return render(request, 'bou_routines_app/assign/examiners.html', context)


@login_required
@require_http_methods(['GET'])
def assign_chairman(request):
    if not user_can_assign_chairman(request.user):
        messages.error(request, "You don't have permission to assign chairman.")
        return _assign_permission_denied_redirect(request)

    context = _assign_filter_context(request)

    courses = _assign_courses_queryset(
        context['selected_semester'],
        centre=context['selected_centre'],
        lab_only=True,
    )

    selected_course_id = request.GET.get('course')
    selected_course = None
    semester_course = None
    if selected_course_id and context['selected_semester'] and context['selected_centre']:
        try:
            selected_course_id = int(selected_course_id)
            selected_course = courses.filter(id=selected_course_id).first()
            if not selected_course:
                selected_course_id = None
            else:
                semester_course = SemesterCourse.objects.filter(
                    semester=context['selected_semester'],
                    course=selected_course,
                    centre=context['selected_centre'],
                ).select_related(
                    'lab_examination_chairman',
                    'lab_examination_member1',
                    'lab_examination_member2',
                    'lab_examination_member3',
                    'lab_examination_member4',
                ).first()
        except (ValueError, TypeError):
            selected_course = None
            selected_course_id = None

    context.update({
        'courses': courses,
        'selected_course': selected_course,
        'selected_course_id': selected_course_id,
        'semester_course': semester_course,
        'all_teachers': context['teachers'],
    })
    return render(request, 'bou_routines_app/assign/chairman.html', context)
