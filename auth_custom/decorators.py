from django.shortcuts import redirect, render
from functools import wraps

def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            user_role = (request.user.role or '').strip().upper()
            allowed_roles_upper = [r.strip().upper() for r in allowed_roles]
            if user_role not in allowed_roles_upper:
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

def feature_required(feature_key):
    """Block access if the user's org doesn't have this feature."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if getattr(request.user, 'role', '') == 'Platform Admin':
                return view_func(request, *args, **kwargs)
            if feature_key not in getattr(request.user, 'features', []):
                from core.features import FEATURE_REGISTRY
                return render(request, 'errors/feature_locked.html', {
                    'feature_name': FEATURE_REGISTRY.get(feature_key, (feature_key,))[0],
                    'current_plan': getattr(request.user, 'plan', 'basic'),
                })
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator

