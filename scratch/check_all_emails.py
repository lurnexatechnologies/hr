import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable

all_emps = EmployeesTable.scan()
missing_email = []
for emp in all_emps:
    if not emp.get('Email'):
        missing_email.append(emp.get('EmployeeID', 'Unknown'))

print(f"Total Employees: {len(all_emps)}")
print(f"Employees missing Email field: {missing_email}")
