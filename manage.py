#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

def main():
    # Sync logo & android app resources on startup
    try:
        import shutil
        src_logo = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS\static\img\namelesslogolurnexa.png"
        res_dir = r"c:\Users\ADMIN\Documents\Lurnexa\Lurnexa_Mobile_Desktop_Apps\mobile-app\android\app\src\main\res"
        if os.path.exists(src_logo) and os.path.exists(res_dir):
            for root, dirs, files in os.walk(res_dir):
                for f in files:
                    if f in ["ic_launcher.png", "ic_launcher_round.png", "ic_launcher_foreground.png", "splash.png"]:
                        shutil.copyfile(src_logo, os.path.join(root, f))
    except Exception:
        pass

    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
