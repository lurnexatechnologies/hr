from django.urls import path
from . import views

urlpatterns = [
    path('', views.TicketListView.as_view(), name='ticket_list'),
    path('create/', views.CreateTicketView.as_view(), name='create_ticket'),
    path('<str:ticket_id>/', views.TicketDetailView.as_view(), name='ticket_detail'),
    path('<str:ticket_id>/comment/', views.AddTicketCommentView.as_view(), name='add_ticket_comment'),
    path('<str:ticket_id>/update-status/', views.UpdateTicketStatusView.as_view(), name='update_ticket_status'),
    path('<str:ticket_id>/rate/', views.SubmitTicketRatingView.as_view(), name='rate_ticket'),
]
