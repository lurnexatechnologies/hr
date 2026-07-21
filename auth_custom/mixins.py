from django.shortcuts import redirect, render
from django.contrib import messages

class FeatureRequiredMixin:
    required_feature = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if getattr(request.user, 'role', '') == 'Platform Admin':
            return super().dispatch(request, *args, **kwargs)
        if self.required_feature:
            if self.required_feature not in getattr(request.user, 'features', []):
                from core.features import FEATURE_REGISTRY
                return render(request, 'errors/feature_locked.html', {
                    'feature_name': FEATURE_REGISTRY.get(self.required_feature, (self.required_feature,))[0],
                    'current_plan': getattr(request.user, 'plan', 'basic'),
                })
        return super().dispatch(request, *args, **kwargs)

class LoginRequiredMixin:
    """Verify that the current user is authenticated."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        return super().dispatch(request, *args, **kwargs)

class PermissionRequiredMixin:
    required_permission = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if getattr(request.user, 'role', '') == 'Platform Admin':
            return super().dispatch(request, *args, **kwargs)
        
        is_super_admin = getattr(request.user, 'role', '') == 'Super admin'
        if self.required_permission:
            user_permissions = getattr(request.user, 'permissions', [])
            if not is_super_admin and self.required_permission not in user_permissions:
                return redirect('forbidden_403')
                
        return super().dispatch(request, *args, **kwargs)

class RoleRequiredMixin:
    """Verify that the current user has one of the allowed roles."""
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        user_role = (request.user.role or '').strip().upper()
        allowed_roles_upper = [r.strip().upper() for r in self.allowed_roles]
        if user_role not in allowed_roles_upper:
            return redirect('forbidden_403')
        return super().dispatch(request, *args, **kwargs)

class HRRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['HR ADMIN', 'HR', 'Super admin']

class SuperAdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['Super admin']

class HRAdminOnlyMixin(RoleRequiredMixin):
    allowed_roles = ['HR ADMIN', 'HR']

class ManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['HR ADMIN', 'HR', 'Super admin', 'Manager']

class AnyRoleRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['HR ADMIN', 'HR', 'Super admin', 'Manager', 'Employee']

class ApprovedOnboardingMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        user_role = (request.user.role or '').strip().upper()
        if user_role == 'EMPLOYEE' and request.user.onboarding_status not in ['Approved', 'Accepted Resignation']:
            return redirect('onboarding_status')
        return super().dispatch(request, *args, **kwargs)
