class PayrollSecurityMiddleware:
    """
    Ensures that payroll authentication remains valid while navigating within payroll,
    and doesn't expire during background polling, AJAX calls, or page navigation.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.session.get('payroll_authenticated'):
            path = request.path
            
            # Explicit logout is the trigger to clear secondary authentication within valid sessions
            if path.startswith('/payroll/logout/'):
                request.session.pop('payroll_authenticated', None)

        response = self.get_response(request)
        return response

