import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable, LeaveRequestsTable

def find_dangling_leaves():
    all_emps = EmployeesTable.scan()
    emp_ids = {e.get('EmployeeID') for e in all_emps if e.get('EmployeeID')}
    
    all_leaves = LeaveRequestsTable.scan()
    dangling = []
    for l in all_leaves:
        eid = l.get('EmployeeID')
        if eid and eid not in emp_ids:
            dangling.append(eid)
            
    print(f"Dangling IDs in LeaveRequestsTable: {set(dangling)}")

find_dangling_leaves()
