import os, django, sys
sys.path.append(r'c:\Users\ADMIN\Documents\Lurnexa\HRMS')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()
from core.dynamodb_service import EmployeesTable

# Scan all employees to find the one with Email 'employee@lurnexa.com'
employees = EmployeesTable.scan()
for e in employees:
    print(f"Employee: {e.get('Email')}, ID: {e.get('EmployeeID')}, IsExperienced: {e.get('IsExperienced')}")

