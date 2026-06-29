import os
import sys
import django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import ResignationsTable, UsersTable
all_res = ResignationsTable.scan()
all_users = UsersTable.scan()
user_role_map = {u.get('EmployeeID'): u.get('Role') for u in all_users if u.get('EmployeeID')}

for r in all_res:
    emp_id = r.get('EmployeeID')
    res_role = user_role_map.get(emp_id)
    status = r.get('Status')
    print(f"Emp: {emp_id}, Role: {res_role}, Status: {status}")
    
    # simulate super admin filter
    if res_role != 'HR ADMIN':
        pass
    else:
        print(f"--> Super admin sees: {emp_id} ({status})")
