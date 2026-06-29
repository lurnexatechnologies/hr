with open(r"c:\Users\ADMIN\Documents\Lurnexa\HRMS\static\css\lurnexastyles.css", "r", encoding="utf-8") as f:
    lines = f.readlines()

found = False
for idx, line in enumerate(lines):
    if ".letter-" in line or "letter-container" in line:
        found = True
        for i in range(max(0, idx - 5), min(len(lines), idx + 40)):
            print(f"{i+1}: {lines[i].rstrip()}")
        print("-" * 40)
