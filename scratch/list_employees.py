from core.dynamodb_service import EmployeesTable
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

employees = EmployeesTable.scan()
for emp in employees:
    print(f"ID: {emp.get('EmployeeID')}, Name: {emp.get('FirstName')} {emp.get('LastName')}")
