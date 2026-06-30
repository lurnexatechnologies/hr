from django.http import HttpResponse
from django.views.decorators.http import require_GET

@require_GET
def robots_txt(request):
    """
    Serves a dynamic robots.txt file to guide search engine crawlers.
    Excludes internal portals, dashboards, and auth actions to ensure security and prevent indexing of sensitive areas.
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
        # Allow indexing of main landing and login pages
        "Allow: /",
        "Allow: /auth/login/",
        "Allow: /auth/forgot-password/",
        "",
        f"Sitemap: {sitemap_url}"
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
