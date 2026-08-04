"""
WSGI config for lurnexa_hrms project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os
import shutil

try:
    src = r"C:\Users\ADMIN\Downloads\IMG_20260803_110623.jpg-removebg-preview.png"
    if os.path.exists(src):
        dst1 = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS\static\img\namelesslogolurnexa.png"
        dst2 = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS\staticfiles\img\namelesslogolurnexa.png"
        shutil.copyfile(src, dst1)
        shutil.copyfile(src, dst2)
        sf_dir = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS\staticfiles\img"
        if os.path.exists(sf_dir):
            for fn in os.listdir(sf_dir):
                if fn.startswith("namelesslogolurnexa.") and fn.endswith(".png"):
                    shutil.copyfile(src, os.path.join(sf_dir, fn))
except Exception:
    pass

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')

application = get_wsgi_application()
