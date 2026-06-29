from django.urls import path
from . import views

urlpatterns = [
    path('apply/', views.ApplyLeaveView.as_view(), name='apply_leave'),
    path('history/', views.LeaveHistoryView.as_view(), name='leave_history'),
    path('approvals/', views.LeaveApprovalsView.as_view(), name='leave_approvals'),
    path('approve/<str:emp_id>/<str:leave_date>/', views.ApproveLeaveView.as_view(), name='approve_leave'),
    path('reject/<str:emp_id>/<str:leave_date>/', views.RejectLeaveView.as_view(), name='reject_leave'),
    
    # Holidays Management
    path('holidays/add/', views.AddHolidayView.as_view(), name='add_holiday'),
    path('holidays/edit/<str:holiday_id>/', views.EditHolidayView.as_view(), name='edit_holiday'),
    path('holidays/delete/<str:holiday_id>/', views.DeleteHolidayView.as_view(), name='delete_holiday'),
    path('calendar/', views.GlobalCalendarView.as_view(), name='company_calendar'),
    path('adjust-balance/<str:emp_id>/', views.AdjustLeaveBalanceView.as_view(), name='adjust_leave_balance'),
    path('encash-el/<str:emp_id>/', views.EncashEarnedLeaveView.as_view(), name='encash_earned_leave'),
]
