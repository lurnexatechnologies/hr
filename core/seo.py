from django.http import HttpResponse, FileResponse, Http404
from django.views.decorators.http import require_GET
from django.conf import settings
import os

@require_GET
def serve_favicon(request):
    """
    Serves the site favicon directly with HTTP 200 OK (no 302 redirects)
    so Googlebot, Googlebot-Image, and browser tab crawlers index the logo icon.
    """
    favicon_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'favicon.ico')
    if not os.path.exists(favicon_path):
        favicon_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'namelesslogolurnexa.png')

    if os.path.exists(favicon_path):
        c_type = 'image/x-icon' if favicon_path.endswith('.ico') else 'image/png'
        response = FileResponse(open(favicon_path, 'rb'), content_type=c_type)
        response['Cache-Control'] = 'public, max-age=31536000'
        return response
    raise Http404("Favicon not found")

@require_GET
def robots_txt(request):
    """
    Serves a dynamic robots.txt file to guide search engine crawlers.
    Excludes internal portals, dashboards, and auth actions to ensure security and prevent indexing of sensitive areas.
    Allows static assets, favicons, and public landing/login pages.
    """
    scheme = 'https' if request.is_secure() else 'http'
    host = request.get_host()
    sitemap_url = f"{scheme}://{host}/sitemap.xml"
    
    lines = [
        "User-agent: *",
        # Block search engines from crawling system paths, dashboards, and personal pages
        "Disallow: /core/",
        "Disallow: /employees/",
        "Disallow: /leave/",
        "Disallow: /attendance/",
        "Disallow: /payroll/",
        "Disallow: /workflows/",
        "Disallow: /auth/logout/",
        "Disallow: /auth/reset-password/",
        "Disallow: /auth/forbidden-403/",
        "",
        # Explicitly allow favicon, static images, and public landing/sitemap pages
        "Allow: /",
        "Allow: /favicon.ico",
        "Allow: /favicon.png",
        "Allow: /apple-touch-icon.png",
        "Allow: /apple-touch-icon-precomposed.png",
        "Allow: /static/",
        "Allow: /media/",
        "Allow: /sitemap/",
        "Allow: /auth/login/",
        "Allow: /auth/forgot-password/",
        "",
        f"Sitemap: {sitemap_url}"
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
