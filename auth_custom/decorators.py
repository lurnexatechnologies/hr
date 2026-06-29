from django.shortcuts import redirect
from functools import wraps

def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.role not in allowed_roles:
                return redirect('forbidden_403')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def login_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

hr_required = role_required(['HR', 'HR ADMIN'])
hr_admin_required = role_required(['HR ADMIN'])
manager_required = role_required(['HR', 'HR ADMIN', 'Manager'])
any_role_required = role_required(['HR', 'HR ADMIN', 'Manager', 'Employee'])
