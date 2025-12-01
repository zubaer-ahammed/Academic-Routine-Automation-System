from django.urls import path
from . import views

urlpatterns = [
    path('', views.generate_routine, name='home'),
    path('generate/', views.generate_routine, name='generate-routine'),
    path('semester-courses/', views.update_semester_courses, name='update-semester-courses'),
    path('download-routines/', views.download_routines, name='download-routines'),
    path('get-semester-courses/', views.get_semester_courses, name='get-semester-courses'),
    path('get-existing-generated-routines/', views.get_existing_generated_routines, name='get-existing-generated-routines'),
    path('check-time-overlap/', views.check_time_overlap, name='check-time-overlap'),
    path('update-routine-course/', views.update_routine_course, name='update-routine-course'),
    path('remove-routine-course/', views.remove_routine_course, name='remove-routine-course'),
    path('reset-routine/', views.reset_routine, name='reset-routine'),
    path('export-to-excel/<int:semester_id>/', views.export_to_excel, name='export-to-excel'),
    path('export-to-pdf/<int:semester_id>/', views.export_to_pdf, name='export-to-pdf'),
    path('export-academic-calendar-pdf/<int:semester_id>/', views.export_academic_calendar_pdf, name='export-academic-calendar-pdf'),
    
    # Attendance Management URLs
    path('attendance/', views.attendance_calendar, name='attendance-calendar'),
    path('attendance/mark/', views.mark_attendance, name='mark-attendance'),
    path('attendance/data/', views.get_attendance_data, name='get-attendance-data'),
    path('attendance/report/', views.attendance_report, name='attendance-report'),
    path('attendance/courses/', views.get_courses_for_semester, name='get-courses-for-semester'),
    path('attendance/semesters/', views.get_semesters_for_curriculum, name='get-semesters-for-curriculum'),
    path('attendance/mark-individual/', views.mark_individual_attendance, name='mark-individual-attendance'),
    
    # Teacher Management URLs
    path('teacher/register/', views.teacher_register, name='teacher-register'),
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher-dashboard'),
    
    # Marks Management URLs
    path('marks/', views.ca_management, name='ca-management'),
    path('marks/save/', views.save_ca_marks, name='save-ca-marks'),
    path('marks/save-final-exam/', views.save_final_exam_marks, name='save-final-exam-marks'),
]
