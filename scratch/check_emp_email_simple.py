import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable

emp = EmployeesTable.get_item({'EmployeeID': '900911'})
print(f"Employee ID: 900911")
if emp:
    print(f"Email in EmployeesTable: |{emp.get('Email')}|")
else:
    print("Employee NOT FOUND")
