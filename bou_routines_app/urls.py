from django.urls import path
from . import views

urlpatterns = [
    path('', views.generate_routine, name='generate-routine'),
    path('generate/', views.generate_routine, name='generate-routine'),
    path('semester-courses/', views.update_semester_courses, name='update-semester-courses'),
    path('download-routines/', views.download_routines, name='download-routines'),
    path('get-semester-courses/', views.get_semester_courses, name='get-semester-courses'),
    path('check-time-overlap/', views.check_time_overlap, name='check-time-overlap'),
    path('export-to-excel/<int:semester_id>/', views.export_to_excel, name='export-to-excel'),
    path('export-to-pdf/<int:semester_id>/', views.export_to_pdf, name='export-to-pdf'),
]
