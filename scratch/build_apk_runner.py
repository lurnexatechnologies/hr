import os
import subprocess
import shutil

log_file = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS\scratch\build.log"
android_dir = r"c:\Users\ADMIN\Documents\Lurnexa\Lurnexa_Mobile_Desktop_Apps\mobile-app\android"
mobile_app_dir = r"c:\Users\ADMIN\Documents\Lurnexa\Lurnexa_Mobile_Desktop_Apps\mobile-app"
hrms_dir = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS"

with open(log_file, "w") as log:
    log.write("=== STARTING APK REBUILD PROCESS ===\n")
    
    # Step 1: npx cap sync android
    log.write("Step 1: Running npx cap sync android...\n")
    log.flush()
    try:
        res1 = subprocess.run(["npx.cmd", "cap", "sync", "android"], cwd=mobile_app_dir, capture_output=True, text=True)
        log.write(f"STDOUT:\n{res1.stdout}\nSTDERR:\n{res1.stderr}\n")
    except Exception as e:
        log.write(f"npx cap sync error: {e}\n")

    # Step 2: gradlew.bat assembleDebug
    log.write("Step 2: Running gradlew.bat assembleDebug...\n")
    log.flush()
    try:
        res2 = subprocess.run(["cmd.exe", "/c", "gradlew.bat", "assembleDebug"], cwd=android_dir, capture_output=True, text=True)
        log.write(f"STDOUT:\n{res2.stdout}\nSTDERR:\n{res2.stderr}\n")
    except Exception as e:
        log.write(f"gradlew assembleDebug error: {e}\n")

    # Step 3: Copy generated APK
    apk_src = os.path.join(android_dir, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
    log.write(f"Step 3: Checking for built APK at {apk_src}...\n")
    if os.path.exists(apk_src):
        log.write(f"SUCCESS: Built APK found! Size: {os.path.getsize(apk_src)} bytes\n")
        dst1 = os.path.join(hrms_dir, "static", "apk", "kyro-people.apk")
        dst2 = os.path.join(hrms_dir, "staticfiles", "apk", "kyro-people.apk")
        os.makedirs(os.path.dirname(dst1), exist_ok=True)
        os.makedirs(os.path.dirname(dst2), exist_ok=True)
        shutil.copy2(apk_src, dst1)
        shutil.copy2(apk_src, dst2)
        log.write(f"Copied to {dst1}\nCopied to {dst2}\n")
        log.write("=== APK REBUILD COMPLETE & SUCCESSFUL! ===\n")
    else:
        log.write("ERROR: Built APK file was not found.\n")

print("Build script executed. Check scratch/build.log for results.")
