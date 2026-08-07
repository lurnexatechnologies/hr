import os
from PIL import Image

img_path = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS\static\img\namelesslogolurnexa.png"

if os.path.exists(img_path):
    print(f"File exists: {img_path}")
    print(f"File size: {os.path.getsize(img_path)} bytes")
    try:
        with Image.open(img_path) as im:
            print(f"Format: {im.format}")
            print(f"Mode: {im.mode}")
            print(f"Size (width x height): {im.size}")
    except Exception as e:
        print(f"Error opening with PIL: {e}")
else:
    print("File does not exist!")
