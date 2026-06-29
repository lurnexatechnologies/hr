import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable, UsersTable

def check_all_sync():
    all_emps = EmployeesTable.scan()
    all_users = UsersTable.scan()
    
    user_map = {u.get('EmployeeID'): u.get('Email') for u in all_users if u.get('EmployeeID')}
    
    print(f"{'EmpID':<15} | {'EmpTable Email':<30} | {'UserTable Email':<30} | Match")
    print("-" * 85)
    
    for emp in all_emps:
        eid = emp.get('EmployeeID')
        emp_email = emp.get('Email')
        user_email = user_map.get(eid)
        match = "YES" if emp_email == user_email else "NO"
        print(f"{str(eid):<15} | {str(emp_email):<30} | {str(user_email):<30} | {match}")

check_all_sync()
