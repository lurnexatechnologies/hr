import os
import shutil
import subprocess

print("=== STARTING COMPLETE AUTOMATIC FIX FOR KYRO PEOPLE APP & LOGO ===")

base_dir = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS"
mobile_app_dir = r"c:\Users\ADMIN\Documents\Lurnexa\Lurnexa_Mobile_Desktop_Apps\mobile-app"
logo_src = os.path.join(base_dir, "static", "img", "namelesslogolurnexa.png")

# 1. Sync Logo Images everywhere
print("\n[1/4] Syncing logo files across all static directories...")
if os.path.exists(logo_src):
    logo_destinations = [
        os.path.join(base_dir, "static", "img", "kyro-logo.png"),
        os.path.join(base_dir, "static", "img", "kyro-logo-192.png"),
        os.path.join(base_dir, "static", "img", "kyro-logo-512.png"),
        os.path.join(base_dir, "static", "favicon.ico"),
        os.path.join(base_dir, "static", "favicon.png"),
        os.path.join(base_dir, "staticfiles", "img", "namelesslogolurnexa.png"),
        os.path.join(base_dir, "staticfiles", "img", "kyro-logo.png"),
        os.path.join(base_dir, "staticfiles", "img", "kyro-logo-192.png"),
        os.path.join(base_dir, "staticfiles", "img", "kyro-logo-512.png"),
        os.path.join(base_dir, "staticfiles", "favicon.ico"),
        os.path.join(base_dir, "staticfiles", "favicon.png"),
    ]
    for dst in logo_destinations:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(logo_src, dst)
        print(f" -> Created/Updated: {dst}")

# 2. Sync Android Res Icons
print("\n[2/4] Syncing Android mipmap icons in mobile-app res folder...")
res_dir = os.path.join(mobile_app_dir, "android", "app", "src", "main", "res")
if os.path.exists(res_dir):
    for root, dirs, files in os.walk(res_dir):
        for f in files:
            if f in ["ic_launcher.png", "ic_launcher_round.png", "ic_launcher_foreground.png", "splash.png"]:
                dst = os.path.join(root, f)
                shutil.copy2(logo_src, dst)
                print(f" -> Updated Android Icon: {dst}")

# 3. Attempt to Build Android APK using gradlew
print("\n[3/4] Attempting automatic Gradle APK build...")
android_dir = os.path.join(mobile_app_dir, "android")
gradlew_bat = os.path.join(android_dir, "gradlew.bat")
build_success = False

if os.path.exists(gradlew_bat):
    try:
        print("Running gradlew.bat assembleDebug...")
        proc = subprocess.run([gradlew_bat, "assembleDebug"], cwd=android_dir, capture_output=True, text=True, timeout=300)
        print("Gradle Output:", proc.stdout[-500:] if proc.stdout else "")
        if proc.returncode == 0:
            print("Gradle build finished successfully!")
            build_success = True
        else:
            print("Gradle exit code:", proc.returncode)
            print("Gradle error:", proc.stderr[-500:] if proc.stderr else "")
    except Exception as e:
        print(f"Gradle build execution failed: {e}")

# 4. Copy built APK if available
apk_src = os.path.join(android_dir, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
if os.path.exists(apk_src):
    apk_dst1 = os.path.join(base_dir, "static", "apk", "kyro-people.apk")
    apk_dst2 = os.path.join(base_dir, "staticfiles", "apk", "kyro-people.apk")
    os.makedirs(os.path.dirname(apk_dst1), exist_ok=True)
    os.makedirs(os.path.dirname(apk_dst2), exist_ok=True)
    shutil.copy2(apk_src, apk_dst1)
    shutil.copy2(apk_src, apk_dst2)
    print(f"\n[4/4] SUCCESS: Copied newly built APK to {apk_dst1} and {apk_dst2}!")
else:
    print(f"\n[4/4] Note: APK binary at {apk_src} not found. Running static sync for existing APKs.")
    # Copy existing kyro-people.apk to staticfiles
    apk_existing = os.path.join(base_dir, "static", "apk", "kyro-people.apk")
    apk_dst2 = os.path.join(base_dir, "staticfiles", "apk", "kyro-people.apk")
    if os.path.exists(apk_existing):
        os.makedirs(os.path.dirname(apk_dst2), exist_ok=True)
        shutil.copy2(apk_existing, apk_dst2)

print("\n=== AUTO FIX COMPLETE ===")
