import subprocess
import os

repo_dir = r"c:\Users\ADMIN\Documents\Lurnexa\HRMS"

try:
    res = subprocess.run(["git", "status", "-s"], cwd=repo_dir, capture_output=True, text=True)
    print("--- Git Status ---")
    print(res.stdout)
except Exception as e:
    print(f"Error: {e}")
