from django.urls import path, include
from django.shortcuts import redirect, render
from django.conf import settings
import os, shutil

# Ensure distinct generated mockup images exist in static/img
img_dir = os.path.join(settings.BASE_DIR, "static", "img")
os.makedirs(img_dir, exist_ok=True)
src1 = r"C:\Users\ADMIN\.gemini\antigravity-ide\brain\582e381b-984f-42b1-9e17-8119c390c528\lurnexa_dashboard_mockup_1785136171876.png"
dst1 = os.path.join(img_dir, "lurnexa_dashboard_mockup.png")
src2 = r"C:\Users\ADMIN\.gemini\antigravity-ide\brain\582e381b-984f-42b1-9e17-8119c390c528\lurnexa_customization_mockup_1785136593371.png"
dst2 = os.path.join(img_dir, "lurnexa_customization_mockup.png")

if os.path.exists(src1):
    try: shutil.copy(src1, dst1)
    except Exception as e: pass
if os.path.exists(src2):
    try: shutil.copy(src2, dst2)
    except Exception as e: pass

def index_redirect(request):
    if request.user.is_authenticated:
        if request.user.role == 'Platform Admin':
            return redirect('platform_dashboard')
        elif request.user.role == 'Super admin':
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

from django.views.generic import TemplateView

urlpatterns = [
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('favicon.ico', RedirectView.as_view(url='/static/img/namelesslogolurnexa.png?v=2'), name='favicon'),
    path('manifest.json', TemplateView.as_view(template_name="manifest.json", content_type="application/json"), name='manifest_json'),
    path('service-worker.js', TemplateView.as_view(template_name="service-worker.js", content_type="application/javascript"), name='service_worker_js'),
    path('offline/', TemplateView.as_view(template_name="offline.html"), name='offline'),
    path('', index_redirect, name='index'),
    path('dashboard/', index_redirect, name='dashboard_redirect'),
    path('auth/', include('auth_custom.urls')),
    path('core/', include('core.urls')),
    path('employees/', include('employees.urls')),
    path('leave/', include('leave.urls')),
    path('attendance/', include('attendance.urls')),
    path('payroll/', include('payroll.urls')),
    path('workflows/', include('workflows.urls')),
    path('api/chatbot/', include('ai_chatbot.urls')),
    

]

from django.views.static import serve
urlpatterns += [
    path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
]
