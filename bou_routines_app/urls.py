from django.urls import path
from . import views

urlpatterns = [
    path('', views.attendance_calendar, name='home'),
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
    path('attendance/export-pdf/', views.export_attendance_pdf, name='export-attendance-pdf'),
    path('attendance/export-blank-pdf/', views.export_blank_attendance_pdf, name='export-blank-attendance-pdf'),
    path('attendance/export-excel/', views.export_attendance_excel, name='export-attendance-excel'),
    path('attendance/courses/', views.get_courses_for_semester, name='get-courses-for-semester'),
    path('attendance/semesters/', views.get_semesters_for_curriculum, name='get-semesters-for-curriculum'),
    path('attendance/mark-individual/', views.mark_individual_attendance, name='mark-individual-attendance'),
    path('attendance/midterm-override/', views.set_attendance_midterm_override_dates, name='set-attendance-midterm-override-dates'),
    
    # Teacher Management URLs
    path('teacher/register/', views.teacher_register, name='teacher-register'),
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher-dashboard'),
    
    # Marks Management URLs
    path('marks/', views.ca_management, name='ca-management'),
    path('marks/save/', views.save_ca_marks, name='save-ca-marks'),
    path('marks/save-midterm/', views.save_midterm_marks, name='save-midterm-marks'),
    path('marks/save-final-exam/', views.save_final_exam_marks, name='save-final-exam-marks'),
    path('marks/save-semester-final-attendance/', views.save_semester_final_attendance, name='save-semester-final-attendance'),
    path('marks/export-ca-pdf/', views.export_ca_marks_pdf, name='export-ca-marks-pdf'),
    path('marks/export-blank-ca-pdf/', views.export_blank_ca_marks_pdf, name='export-blank-ca-marks-pdf'),
    path('marks/export-ca-excel/', views.export_ca_marks_excel, name='export-ca-marks-excel'),
    path('marks/export-final-exam-pdf/', views.export_final_exam_pdf, name='export-final-exam-pdf'),
    path('marks/export-blank-final-exam-pdf/', views.export_blank_final_exam_pdf, name='export-blank-final-exam-pdf'),
    path('marks/export-final-exam-excel/', views.export_final_exam_excel, name='export-final-exam-excel'),
    path('marks/export-final-exam-summary-pdf/', views.export_final_exam_summary_pdf, name='export-final-exam-summary-pdf'),
    path('marks/export-final-exam-summary-excel/', views.export_final_exam_summary_excel, name='export-final-exam-summary-excel'),
    path('marks/assign-evaluator/', views.assign_evaluator, name='assign-evaluator'),
]
