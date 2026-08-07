import os

apk_path = r"c:\Users\ADMIN\Documents\Lurnexa\Lurnexa_Mobile_Desktop_Apps\mobile-app\android\app\build\outputs\apk\debug\app-debug.apk"
if os.path.exists(apk_path):
    print(f"APK exists! Size: {os.path.getsize(apk_path)} bytes")
else:
    print(f"APK does not exist at {apk_path}")

build_dir = r"c:\Users\ADMIN\Documents\Lurnexa\Lurnexa_Mobile_Desktop_Apps\mobile-app\android\app\build"
if os.path.exists(build_dir):
    print("Build dir contents:")
    for root, dirs, files in os.walk(build_dir):
        for f in files:
            if f.endswith(".apk"):
                print(" Found APK:", os.path.join(root, f))
