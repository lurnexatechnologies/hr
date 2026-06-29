import os
import sys
import django
import datetime

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable

selected_month = 'may'
selected_year = '2026'
period_end_date = datetime.date(2026, 5, 31)

all_employees = EmployeesTable.scan()
pf_employees = []

print("Total employees in DB:", len(all_employees))
for e in all_employees:
    emp_type = e.get('EmploymentType')
    joined_str = e.get('JoinedDate')
    
    print(f"ID: {e.get('EmployeeID')}, Name: {e.get('FirstName')}, Type: {emp_type}, Joined: {joined_str}")
    
    if emp_type != 'Permanent':
        continue
    if not joined_str:
        continue
    try:
        joined_date = datetime.datetime.strptime(joined_str, '%Y-%m-%d').date()
        if joined_date <= period_end_date:
            pf_employees.append(e)
    except Exception as ex:
        print("Error parsing date:", ex)

print("\nMatching PF Employees:")
for e in pf_employees:
    print(f"ID: {e.get('EmployeeID')}, Name: {e.get('FirstName')}")
