import os
import sys
import django
import datetime

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable, LeaveRequestsTable
from core.utils import get_initial_leave_balance, get_days_count

current_month_str = datetime.date.today().strftime('%Y-%m')

print("Starting Leave Balance Migration (with used leaves subtraction)...")

# 1. Scan all leave requests to group by employee
all_leaves = LeaveRequestsTable.scan()
leaves_by_emp = {}
for leave in all_leaves:
    emp_id = leave.get('EmployeeID')
    if emp_id not in leaves_by_emp:
        leaves_by_emp[emp_id] = []
    leaves_by_emp[emp_id].append(leave)

# 2. Iterate employees and update balances
for emp in EmployeesTable.scan():
    emp_id = emp.get('EmployeeID')
    if not emp_id or emp.get('EmploymentType') == 'Intern':
        if emp.get('EmploymentType') == 'Intern':
            EmployeesTable.update_item(
                Key={'EmployeeID': emp_id},
                UpdateExpression="SET Balance_SL = :sl, Balance_CL = :cl, LastLeaveRefresh = :lr",
                ExpressionAttributeValues={':sl': '0.0', ':cl': '0.0', ':lr': current_month_str}
            )
            print(f"ID: {emp_id} (Intern) -> SL/CL reset to 0.0")
        continue

    # Get initial balance under the new annual/prorated policy
    initial_sl = get_initial_leave_balance(emp, 'SL')
    initial_cl = get_initial_leave_balance(emp, 'CL')

    # Get employee's leaves
    emp_leaves = leaves_by_emp.get(emp_id, [])

    # Calculate spent SL/CL in 2026 (current year)
    spent_sl = 0.0
    spent_cl = 0.0
    for l in emp_leaves:
        if l.get('Status') == 'Approved':
            l_date_str = l.get('LeaveDate')
            # Check if leave is in current year
            if l_date_str and l_date_str.startswith('2026'):
                l_type = l.get('Type', '')
                days = get_days_count(l)
                if 'Sick Leave' in l_type:
                    spent_sl += days
                elif 'Casual Leave' in l_type:
                    spent_cl += days

    # Remaining balance = initial - spent (bounded by 0.0)
    rem_sl = max(0.0, initial_sl - spent_sl)
    rem_cl = max(0.0, initial_cl - spent_cl)

    # Update DynamoDB
    EmployeesTable.update_item(
        Key={'EmployeeID': emp_id},
        UpdateExpression="SET Balance_SL = :sl, Balance_CL = :cl, LastLeaveRefresh = :lr",
        ExpressionAttributeValues={
            ':sl': str(float(rem_sl)),
            ':cl': str(float(rem_cl)),
            ':lr': current_month_str
        }
    )
    print(f"ID: {emp_id} | Initial SL/CL: {initial_sl}/{initial_cl} | Spent SL/CL: {spent_sl}/{spent_cl} | New Remaining SL/CL: {rem_sl}/{rem_cl}")

print("Migration completed successfully!")
