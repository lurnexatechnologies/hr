import os, sys, django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable, UsersTable

emp_id = 'EMP-D41727'
employee = EmployeesTable.get_item({'EmployeeID': emp_id})
if employee:
    employee['OnboardingStatus'] = 'Approved'
    employee['LastWorkingDate'] = None
    employee['IsActive'] = True
    EmployeesTable.put_item(employee)
    print(f"Restored employee record for {emp_id}")
    
    user_id = employee.get('UserID')
    if user_id:
        user = UsersTable.get_item({'UserID': user_id})
        if user:
            user['IsActive'] = True
            UsersTable.put_item(user)
            print(f"Restored user record for {user_id}")
else:
    print(f"Employee {emp_id} not found")
