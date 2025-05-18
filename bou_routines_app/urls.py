from django.urls import path
from . import views

urlpatterns = [
    path('', views.routine_entry, name='routine-entry'),
    path('generate/', views.generate_routine, name='generate-routine'),
    path('semester-courses/', views.update_semester_courses, name='update-semester-courses'),
    path('get-semester-courses/', views.get_semester_courses, name='get-semester-courses'),
    path('check-time-overlap/', views.check_time_overlap, name='check-time-overlap'),
]
