from django.shortcuts import redirect
from django.contrib import messages

class LoginRequiredMixin:
    """Verify that the current user is authenticated."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        return super().dispatch(request, *args, **kwargs)

class RoleRequiredMixin:
    """Verify that the current user has one of the allowed roles."""
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.role not in self.allowed_roles:
            return redirect('forbidden_403')
        return super().dispatch(request, *args, **kwargs)

class HRRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['HR ADMIN', 'Super admin']

class SuperAdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['Super admin']

class HRAdminOnlyMixin(RoleRequiredMixin):
    allowed_roles = ['HR ADMIN']

class ManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['HR ADMIN', 'Super admin', 'Manager']

class AnyRoleRequiredMixin(RoleRequiredMixin):
    allowed_roles = ['HR ADMIN', 'Super admin', 'Manager', 'Employee']

class ApprovedOnboardingMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.role == 'Employee' and request.user.onboarding_status not in ['Approved', 'Accepted Resignation']:
            return redirect('onboarding_status')
        return super().dispatch(request, *args, **kwargs)
