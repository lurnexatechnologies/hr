from django.shortcuts import redirect
from django.contrib import messages

class MaxUploadSizeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.FILES:
            for file_name, file_obj in request.FILES.items():
                if file_obj.size > 2 * 1024 * 1024:  # 2MB
                    messages.error(request, f"Upload rejected. The file '{file_obj.name}' exceeds the maximum allowed size of 2MB.")
                    referer = request.META.get('HTTP_REFERER')
                    if referer:
                        return redirect(referer)
                    else:
                        return redirect('/')  # Fallback to root if referer is missing
        return self.get_response(request)
