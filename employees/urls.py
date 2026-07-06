from django.urls import path
from . import views

urlpatterns = [
    path('', views.EmployeeDirectoryView.as_view(), name='employee_directory'),
    path('ex-employees/', views.ExEmployeeDirectoryView.as_view(), name='ex_employee_directory'),
    path('my-team/', views.MyTeamView.as_view(), name='my_team'),
    path('profile/<str:emp_id>/', views.EmployeeProfileView.as_view(), name='employee_profile'),
    path('add/', views.AddEmployeeView.as_view(), name='add_employee'),
    path('edit/<str:emp_id>/', views.EditEmployeeView.as_view(), name='edit_employee'),
    path('generate-link/', views.GenerateOnboardingLinkView.as_view(), name='generate_onboarding_link'),
    path('bulk-onboarding/', views.BulkOnboardingLinkView.as_view(), name='bulk_onboarding_link'),
    path('bulk-onboarding/template/', views.DownloadSampleCSVView.as_view(), name='download_sample_csv'),
    path('onboarding-requests/', views.OnboardingRequestsView.as_view(), name='onboarding_requests'),
    path('review-onboarding/<str:emp_id>/', views.ReviewOnboardingView.as_view(), name='review_onboarding'),
    path('approve-onboarding/<str:emp_id>/', views.ApproveOnboardingActionView.as_view(), name='approve_onboarding_action'),
    path('onboarding-status/', views.OnboardingStatusView.as_view(), name='onboarding_status'),
    path('reupload-docs/', views.ReuploadDocumentsView.as_view(), name='reupload_docs'),
    path('self-onboarding/<str:token>/', views.SelfOnboardingView.as_view(), name='self_onboarding'),
    path('toggle-active/<str:emp_id>/', views.ToggleActiveStatusView.as_view(), name='toggle_active_status'),
    path('move-to-ex/<str:emp_id>/', views.MoveToExEmployeeView.as_view(), name='move_to_ex_employee'),
    path('delete/<str:emp_id>/', views.DeleteEmployeeView.as_view(), name='delete_employee'),
    path('documents/letters/', views.EmployeeLettersView.as_view(), name='employee_letters'),
    path('documents/letters/<str:letter_id>/print/', views.PrintLetterView.as_view(), name='print_letter'),
    path('verify-password/', views.VerifyPasswordView.as_view(), name='verify_password'),
    path('profile/<str:emp_id>/certificates/upload/', views.UploadCertificateView.as_view(), name='upload_certificate'),
    path('certificates/approvals/', views.CertificateApprovalsView.as_view(), name='certificate_approvals'),
    path('certificates/<str:emp_id>/<str:cert_id>/action/', views.CertificateActionView.as_view(), name='certificate_action'),
    path('certificates/<str:emp_id>/<str:cert_id>/delete/', views.DeleteCertificateView.as_view(), name='delete_certificate'),
    
    # Asset Management Module
    path('assets/', views.AssetManagementView.as_view(), name='asset_management'),
    path('assets/add/', views.AddAssetView.as_view(), name='add_asset'),
    path('assets/allocate/<str:asset_id>/', views.AllocateAssetView.as_view(), name='allocate_asset'),
    path('assets/return/<str:asset_id>/', views.ReturnAssetView.as_view(), name='return_asset'),
    path('assets/update-condition/<str:asset_id>/', views.UpdateAssetConditionView.as_view(), name='update_asset_condition'),
    path('assets/delete/<str:asset_id>/', views.DeleteAssetView.as_view(), name='delete_asset'),
    path('my-assets/', views.MyAssetsView.as_view(), name='my_assets'),
    path('my-assets/request/', views.RaiseAssetRequestView.as_view(), name='raise_asset_request'),
    path('assets/requests/handle/<str:request_id>/', views.HandleAssetRequestView.as_view(), name='handle_asset_request'),
]

