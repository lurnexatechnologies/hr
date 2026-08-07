import shutil
import os

base_dir = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS"
static_dir = os.path.join(base_dir, "static")
staticfiles_dir = os.path.join(base_dir, "staticfiles")

if os.path.exists(staticfiles_dir):
    print("Syncing static -> staticfiles...")
    for root, dirs, files in os.walk(static_dir):
        rel_path = os.path.relpath(root, static_dir)
        target_root = os.path.join(staticfiles_dir, rel_path)
        os.makedirs(target_root, exist_ok=True)
        for f in files:
            src_file = os.path.join(root, f)
            dst_file = os.path.join(target_root, f)
            shutil.copy2(src_file, dst_file)
    print("Static files synced successfully!")
