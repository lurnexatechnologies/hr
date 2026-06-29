from django.urls import path
from . import views

urlpatterns = [
    path('clock_in/', views.ClockInView.as_view(), name='clock_in'),
    path('clock_out/', views.ClockOutView.as_view(), name='clock_out'),
    path('history/', views.AttendanceHistoryView.as_view(), name='attendance_history'),
    path('hr_attendance/', views.HRAttendanceView.as_view(), name='hr_attendance'),
    path('update_timings/', views.OfficeTimingSettingsView.as_view(), name='update_timings'),
    path('download_report/', views.DownloadAttendanceReportView.as_view(), name='download_attendance_report'),
    path('export_my_attendance/', views.ExportMyAttendanceView.as_view(), name='export_my_attendance'),
    path('apply_wfh/', views.ApplyWFHView.as_view(), name='apply_wfh'),
    path('import_data/', views.ImportAttendanceView.as_view(), name='import_attendance'),
]
