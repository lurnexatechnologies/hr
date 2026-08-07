import os
import glob

dirs_to_check = [
    r"C:\Users\ADMIN\Downloads",
    r"C:\Users\ADMIN\Desktop",
    r"C:\Users\ADMIN\Pictures",
    r"C:\Users\ADMIN\Documents\Lurnexa\HRMS\static\img"
]

print("--- Searching for images ---")
for d in dirs_to_check:
    if os.path.exists(d):
        for ext in ['*.png', '*.jpg', '*.jpeg', '*.svg', '*.webp']:
            for f in glob.glob(os.path.join(d, ext)):
                print(f)
