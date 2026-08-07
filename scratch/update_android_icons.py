import shutil
import os

src_logo = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS\static\img\namelesslogolurnexa.png"
res_dir = r"c:\Users\ADMIN\Documents\Lurnexa\Lurnexa_Mobile_Desktop_Apps\mobile-app\android\app\src\main\res"

if os.path.exists(src_logo) and os.path.exists(res_dir):
    for root, dirs, files in os.walk(res_dir):
        for f in files:
            if f in ["ic_launcher.png", "ic_launcher_round.png", "ic_launcher_foreground.png", "splash.png"]:
                dst = os.path.join(root, f)
                try:
                    shutil.copyfile(src_logo, dst)
                    print(f"Updated: {dst}")
                except Exception as e:
                    print(f"Error copying to {dst}: {e}")
print("Icon sync finished.")
