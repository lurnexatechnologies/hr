"""
WSGI config for lurnexa_hrms project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os
import shutil

try:
    src_logo = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS\static\img\namelesslogolurnexa.png"
    res_dir = r"c:\Users\ADMIN\Documents\Lurnexa\Lurnexa_Mobile_Desktop_Apps\mobile-app\android\app\src\main\res"
    if os.path.exists(src_logo) and os.path.exists(res_dir):
        for root, dirs, files in os.walk(res_dir):
            for f in files:
                if f in ["ic_launcher.png", "ic_launcher_round.png", "ic_launcher_foreground.png", "splash.png"]:
                    shutil.copyfile(src_logo, os.path.join(root, f))
except Exception:
    pass

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')

application = get_wsgi_application()
