from django.urls import path
from . import views, pf_views

urlpatterns = [
    path('', views.PayslipsView.as_view(), name='payslips_view'),
    path('manage/', views.ManagePayrollView.as_view(), name='manage_payroll'),
    path('login/', views.PayrollLoginView.as_view(), name='payroll_login'),
    path('logout/', views.PayrollLogoutView.as_view(), name='payroll_logout'),
    path('esi-config/', views.UpdateESIConfigView.as_view(), name='update_esi_config'),
    path('download/<str:month_year>/', views.DownloadPayslipView.as_view(), name='download_payslip'),
    path('download/<str:month_year>/<str:emp_id>/', views.DownloadPayslipView.as_view(), name='download_payslip_hr'),
    
    # PF Management
    path('pf/management/', pf_views.PFManagementView.as_view(), name='pf_management'),
    path('pf/update-details/<str:emp_id>/', pf_views.UpdatePFDetailsView.as_view(), name='update_pf_details'),
    path('pf/mark-paid/<str:emp_id>/', pf_views.MarkPFPaidView.as_view(), name='mark_pf_paid'),
    
    # Payroll Approval Workflow
    path('approvals/', views.PayrollApprovalView.as_view(), name='payroll_approval_list'),
    path('approvals/process/<str:request_id>/', views.ProcessPayrollApprovalView.as_view(), name='process_payroll_approval'),
    path('approvals/set-generation-date/', views.SetPayrollGenerationDateView.as_view(), name='set_payroll_generation_date'),
    
    # Historical Payroll
    path('historical/', views.HistoricalPayrollView.as_view(), name='historical_payroll'),
]
