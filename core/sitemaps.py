import os
import datetime
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.conf import settings

class LurnexaStaticSitemap(Sitemap):
    def items(self):
        # Publicly accessible pages to be indexed by search engines
        return ['index', 'login', 'forgot_password', 'sitemap_html', 'privacy_policy', 'terms_of_service']

    def location(self, item):
        return reverse(item)

    def lastmod(self, item):
        # Dynamically check template modification time to give search crawlers accurate information
        template_map = {
            'index': 'landing_page.html',
            'login': 'base_auth.html',
            'forgot_password': 'base_auth.html',
            'sitemap_html': 'sitemap.html',
            'privacy_policy': 'core/privacy_policy.html',
            'terms_of_service': 'core/terms_of_service.html',
        }
        template_name = template_map.get(item)
        if template_name:
            for template_dir in settings.TEMPLATES[0]['DIRS']:
                path = os.path.join(template_dir, template_name)
                if os.path.exists(path):
                    mtime = os.path.getmtime(path)
                    return datetime.date.fromtimestamp(mtime)
        return datetime.date.today()

    def priority(self, item):
        priorities = {
            'index': 1.0,
            'sitemap_html': 0.9,
            'login': 0.8,
            'privacy_policy': 0.5,
            'terms_of_service': 0.5,
            'forgot_password': 0.5,
        }
        return priorities.get(item, 0.5)

    def changefreq(self, item):
        freqs = {
            'index': 'daily',
            'sitemap_html': 'weekly',
            'login': 'monthly',
            'privacy_policy': 'monthly',
            'terms_of_service': 'monthly',
            'forgot_password': 'monthly',
        }
        return freqs.get(item, 'monthly')
