from django.urls import path
from ai_chatbot.views import AIChatView

urlpatterns = [
    path('chat/', AIChatView.as_view(), name='ai_chat_api'),
]
