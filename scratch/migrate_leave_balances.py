import os
import sys
import django
import datetime

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable
from core.utils import get_initial_leave_balance

current_month_str = datetime.date.today().strftime('%Y-%m')

print("Starting Leave Balance Migration...")
for emp in EmployeesTable.scan():
    emp_id = emp.get('EmployeeID')
    if not emp_id or emp.get('EmploymentType') == 'Intern':
        # Interns or invalid IDs skip or get reset to 0.0
        if emp.get('EmploymentType') == 'Intern':
            EmployeesTable.update_item(
                Key={'EmployeeID': emp_id},
                UpdateExpression="SET Balance_SL = :sl, Balance_CL = :cl, LastLeaveRefresh = :lr",
                ExpressionAttributeValues={':sl': '0.0', ':cl': '0.0', ':lr': current_month_str}
            )
            print(f"ID: {emp_id} (Intern) -> SL/CL reset to 0.0")
        continue

    # Calculate new correct initial leaves under the annual/prorated policy
    new_sl = get_initial_leave_balance(emp, 'SL')
    new_cl = get_initial_leave_balance(emp, 'CL')
    
    # Update employee item in the database
    EmployeesTable.update_item(
        Key={'EmployeeID': emp_id},
        UpdateExpression="SET Balance_SL = :sl, Balance_CL = :cl, LastLeaveRefresh = :lr",
        ExpressionAttributeValues={
            ':sl': str(float(new_sl)),
            ':cl': str(float(new_cl)),
            ':lr': current_month_str
        }
    )
    print(f"Migrated ID: {emp_id} | Joined: {emp.get('JoinedDate')} | New SL: {new_sl} | New CL: {new_cl}")

print("Migration completed successfully!")
