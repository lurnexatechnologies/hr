class PayrollSecurityMiddleware:
    """
    Ensures that payroll authentication is ephemeral.
    If the user navigates away from the payroll management area, 
    their secondary authentication is automatically cleared.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # List of paths that are allowed to keep the payroll session active
        allowed_paths = [
            '/payroll/manage/',
            '/payroll/login/',
            '/payroll/logout/',
            '/payroll/download/',
            '/payroll/esi-config/',
        ]
        
        # If user is authenticated for payroll but navigates to a non-payroll path
        if request.session.get('payroll_authenticated'):
            is_allowed = False
            for path in allowed_paths:
                if request.path.startswith(path):
                    is_allowed = True
                    break
            
            # If not an allowed path and not a static/media file (simple check)
            if not is_allowed and not request.path.startswith('/static/') and not request.path.startswith('/media/'):
                del request.session['payroll_authenticated']
        
        response = self.get_response(request)
        return response
