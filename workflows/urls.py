from django.urls import path
from . import views

urlpatterns = [
    path('expenses/', views.ExpensesView.as_view(), name='expenses_view'),
    path('expenses/approvals/', views.ExpenseApprovalsView.as_view(), name='expense_approvals'),
    path('expenses/approve/<str:emp_id>/<str:req_id>/', views.ApproveExpenseView.as_view(), name='approve_expense'),
    path('expenses/reject/<str:emp_id>/<str:req_id>/', views.RejectExpenseView.as_view(), name='reject_expense'),
    path('expenses/pay/<str:emp_id>/<str:req_id>/', views.ProcessPaymentView.as_view(), name='process_payment'),
    path('resignation/', views.ResignationView.as_view(), name='resignation_view'),
    path('resignation/approvals/', views.ResignationApprovalsView.as_view(), name='resignation_approvals'),
    path('resignation/process/<str:emp_id>/<str:action>/', views.ProcessResignationView.as_view(), name='process_resignation'),
    path('resignation/delete/<str:emp_id>/', views.DeleteEmployeeView.as_view(), name='delete_employee'),
    path('wfh/approvals/', views.WFHApprovalsView.as_view(), name='wfh_approvals'),
    path('wfh/approve/<str:emp_id>/<str:req_id>/', views.ApproveWFHView.as_view(), name='approve_wfh'),
    path('wfh/reject/<str:emp_id>/<str:req_id>/', views.RejectWFHView.as_view(), name='reject_wfh'),
    path('resignation/experience-letter/<str:emp_id>/', views.GenerateExperienceLetterView.as_view(), name='generate_experience_letter'),
    path('resignation/pf-letter/<str:emp_id>/', views.GeneratePFLetterView.as_view(), name='generate_pf_letter'),
    
    # PF Onboarding Workflow (Deprecated)
    # path('pf/dashboard/', pf_views.PFWorkflowDashboardView.as_view(), name='pf_dashboard'),
    # path('pf/tracker/', pf_views.PFWorkflowTrackerView.as_view(), name='pf_tracker'),
]
