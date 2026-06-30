from django.urls import path, include
from django.shortcuts import redirect, render

def index_redirect(request):
    if request.user.is_authenticated:
        if request.user.role == 'Super admin':
            return redirect('super_admin_dashboard')
        elif request.user.role == 'HR ADMIN':
            return redirect('hr_dashboard')
        elif request.user.role == 'Manager':
            return redirect('manager_dashboard')
        else:
            return redirect('employee_dashboard')
    return render(request, 'landing_page.html')

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.generic.base import RedirectView
from core.sitemaps import LurnexaStaticSitemap
from core.seo import robots_txt

sitemaps = {
    'static': LurnexaStaticSitemap,
}

urlpatterns = [
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('favicon.ico', RedirectView.as_view(url='/static/img/namelesslogolurnexa.png?v=2'), name='favicon'),
    path('', index_redirect, name='index'),
    path('dashboard/', index_redirect, name='dashboard_redirect'),
    path('auth/', include('auth_custom.urls')),
    path('core/', include('core.urls')),
    path('employees/', include('employees.urls')),
    path('leave/', include('leave.urls')),
    path('attendance/', include('attendance.urls')),
    path('payroll/', include('payroll.urls')),
    path('workflows/', include('workflows.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
