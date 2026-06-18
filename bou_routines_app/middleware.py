from django.shortcuts import redirect
from django.contrib import messages
from .models import Teacher
from .views import user_is_office_staff


def _path_allowed_for_office_staff(path):
  allowed_prefixes = (
      '/assign/',
      '/marks/assign-evaluator/',
      '/marks/assign-chairman/',
      '/logout',
      '/accounts/logout',
      '/login',
      '/accounts/login',
      '/accounts/exit-impersonation/',
      '/static/',
      '/media/',
      '/attendance/courses/',
      '/attendance/semesters/',
  )
  return any(path.startswith(prefix) for prefix in allowed_prefixes)


class TeacherAccessMiddleware:
    """
    Middleware to restrict admin access for teacher-only users
    (users with teacher profile but not staff/superuser)
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/'):
            if request.user.is_authenticated:
                if user_is_office_staff(request.user):
                    messages.error(
                        request,
                        "You don't have permission to access the admin panel. "
                        "Office staff can only use the Assign pages.",
                    )
                    return redirect('assign-home')
                try:
                    teacher = request.user.teacher
                    if teacher is not None and not request.user.is_superuser:
                        messages.error(
                            request,
                            "You don't have permission to access the admin panel. "
                            "Teachers can only access Download Routines, Attendance, and Marks pages.",
                        )
                        return redirect('download-routines')
                except (Teacher.DoesNotExist, AttributeError):
                    pass

        response = self.get_response(request)
        return response


class OfficeStaffAccessMiddleware:
    """Restrict office staff to assignment pages and related APIs only."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and user_is_office_staff(request.user):
            if request.path == '/':
                return redirect('assign-home')
            if not _path_allowed_for_office_staff(request.path):
                return redirect('assign-home')
        return self.get_response(request)
