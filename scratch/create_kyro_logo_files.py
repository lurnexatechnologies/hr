import os
import shutil

base_dir = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS"
src = os.path.join(base_dir, "static", "img", "namelesslogolurnexa.png")

targets = [
    os.path.join(base_dir, "static", "img", "kyro-logo.png"),
    os.path.join(base_dir, "static", "img", "kyro-logo-192.png"),
    os.path.join(base_dir, "static", "img", "kyro-logo-512.png"),
    os.path.join(base_dir, "static", "favicon.ico"),
    os.path.join(base_dir, "staticfiles", "img", "kyro-logo.png"),
    os.path.join(base_dir, "staticfiles", "img", "kyro-logo-192.png"),
    os.path.join(base_dir, "staticfiles", "img", "kyro-logo-512.png"),
    os.path.join(base_dir, "staticfiles", "img", "namelesslogolurnexa.png"),
    os.path.join(base_dir, "staticfiles", "favicon.ico"),
]

if os.path.exists(src):
    for t in targets:
        os.makedirs(os.path.dirname(t), exist_ok=True)
        shutil.copy2(src, t)
        print(f"Copied to: {t}")
print("Kyro logo files created successfully!")
