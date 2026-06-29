import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
import django
django.setup()

from core.dynamodb_service import EmployeesTable

employees = EmployeesTable.scan()
print(f"Total employees: {len(employees)}")
for emp in employees:
    print(f"ID: {emp.get('EmployeeID')}, Name: {emp.get('FirstName')} {emp.get('LastName')}, Experienced: {emp.get('IsExperienced')}, ExperienceLetter: {emp.get('ExperienceLetter')}, RelievingLetter: {emp.get('RelievingLetter')}, PFLetter: {emp.get('PFLetter')}")
