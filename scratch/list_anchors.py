import re

with open('templates/employees/profile.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '<a ' in line or 'View Draft' in line:
        print(f"Line {i+1}: {line.strip()}")
