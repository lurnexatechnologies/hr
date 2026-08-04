#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

def main():
    # Sync new logo bytes on startup if present
    try:
        import shutil
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
