from django.shortcuts import redirect
from django.contrib import messages
from .models import Teacher


class TeacherAccessMiddleware:
    """
    Middleware to restrict admin access for teacher-only users
    (users with teacher profile but not staff/superuser)
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if user is trying to access admin
        if request.path.startswith('/admin/'):
            if request.user.is_authenticated:
                try:
                    teacher = request.user.teacher
                    # If user has teacher profile but is not superuser, block admin access
                    if teacher is not None and not request.user.is_superuser:
                        messages.error(request, "You don't have permission to access the admin panel. Teachers can only access Download Routines, Attendance, and Marks pages.")
                        return redirect('download-routines')
                except (Teacher.DoesNotExist, AttributeError):
                    # User doesn't have teacher profile, allow access if they're staff/superuser
                    pass

        response = self.get_response(request)
        return response

