import json
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from auth_custom.mixins import LoginRequiredMixin
from ai_chatbot.services import process_ai_chat

@method_decorator(csrf_exempt, name='dispatch')
class AIChatView(LoginRequiredMixin, View):
    """API endpoint for text & voice AI chatbot interaction."""
    
    def post(self, request):
        if getattr(request.user, 'role', None) == 'Platform Admin':
            return JsonResponse({'error': 'AI Chatbot is disabled for Platform Admin.'}, status=403)
            
        try:
            body = json.loads(request.body.decode('utf-8'))
            user_message = body.get('message', '').strip()
            history = body.get('history', [])
            language = body.get('language', 'en-US')
            language_name = body.get('language_name', 'English')
            
            if not user_message:
                return JsonResponse({'error': 'Message is required'}, status=400)
                
            response_data = process_ai_chat(
                user=request.user,
                user_message=user_message,
                conversation_history=history,
                language=language,
                language_name=language_name
            )
            
            return JsonResponse({
                'success': True,
                'reply': response_data.get('text', ''),
                'actions': response_data.get('actions', [])
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
