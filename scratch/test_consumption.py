import os
import django
import datetime
from core.dynamodb_service import EmployeesTable, LeaveRequestsTable
from boto3.dynamodb.conditions import Key

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

emp_id = 'LT20265006' # Yesh Raj
leave_type = 'Maternity Leave'

print(f"Simulating application for {emp_id}...")

# 1. Fetch employee
employee = EmployeesTable.get_item({'EmployeeID': emp_id})
print(f"Initial AllowSecondParental: {employee.get('AllowSecondParental')}")

# 2. Consume (Simulation of ApplyLeaveView.post logic)
if 'Maternity' in leave_type or 'Paternity' in leave_type:
    if employee.get('AllowSecondParental'):
        print("Consuming parental override...")
        EmployeesTable.update_item(
            Key={'EmployeeID': emp_id},
            UpdateExpression="SET #asp = :f",
            ExpressionAttributeNames={'#asp': 'AllowSecondParental'},
            ExpressionAttributeValues={':f': False}
        )

# 3. Verify
updated_emp = EmployeesTable.get_item({'EmployeeID': emp_id})
print(f"Final AllowSecondParental: {updated_emp.get('AllowSecondParental')}")
