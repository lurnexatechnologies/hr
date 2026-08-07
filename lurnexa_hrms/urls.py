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

favicon_src = os.path.join(img_dir, "namelesslogolurnexa.png")
if os.path.exists(favicon_src):
    try:
        shutil.copy(favicon_src, os.path.join(img_dir, "favicon.ico"))
        shutil.copy(favicon_src, os.path.join(settings.BASE_DIR, "static", "favicon.ico"))
    except Exception:
        pass

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
            
    from core.utils import is_mobile_app
    if is_mobile_app(request):
        return redirect('login')
        
    return render(request, 'landing_page.html')

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.generic.base import RedirectView
from core.sitemaps import LurnexaStaticSitemap
from core.seo import robots_txt, serve_favicon

sitemaps = {
    'static': LurnexaStaticSitemap,
}

from django.views.generic import TemplateView
from core import sales_views

urlpatterns = [
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('sitemap/', TemplateView.as_view(template_name="sitemap.html"), name='sitemap_html'),
    path('site-map/', RedirectView.as_view(pattern_name='sitemap_html', permanent=True)),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('favicon.ico', serve_favicon, name='favicon'),
    path('favicon.png', serve_favicon, name='favicon_png'),
    path('apple-touch-icon.png', serve_favicon, name='apple_touch_icon'),
    path('apple-touch-icon-precomposed.png', serve_favicon, name='apple_touch_icon_precomposed'),
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
    path('tickets/', include('tickets.urls')),
    
    # Sales Live Tracking Routes
    path('sales/live-tracking/', sales_views.sales_live_tracking_dashboard, name='sales_live_tracking_dashboard'),
    path('api/sales/location/update/', sales_views.update_sales_location_api, name='update_sales_location_api'),
    path('api/sales/live-locations/', sales_views.get_sales_live_locations_api, name='sales_live_locations_api'),
    path('api/sales/location-history/<str:employee_id>/', sales_views.get_sales_location_history_api, name='sales_location_history_api'),
]

from django.urls import re_path
from django.views.static import serve
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
