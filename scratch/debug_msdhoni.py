import os
import sys
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable, UsersTable
from boto3.dynamodb.conditions import Key

def check_employee(emp_id):
    print(f"--- Checking Employee ID: {emp_id} ---")
    emp = EmployeesTable.get_item({'EmployeeID': emp_id})
    print(f"Employee Record: {emp}")
    
    if emp:
        user_id = emp.get('UserID')
        print(f"Associated UserID from Emp Record: {user_id}")
        if user_id:
            user = UsersTable.get_item({'UserID': user_id})
            print(f"User Record by UserID: {user}")
    
    # Also search UsersTable by EmployeeID
    users_by_eid = UsersTable.scan(
        FilterExpression="EmployeeID = :eid",
        ExpressionAttributeValues={":eid": emp_id}
    )
    print(f"Users found by EmployeeID scan: {users_by_eid}")

if __name__ == "__main__":
    check_employee('msdhoni')
    # Maybe the ID is LT-26... or something else, let's scan for msdhoni in FirstName
    all_emps = EmployeesTable.scan()
    for e in all_emps:
        if 'msdhoni' in str(e).lower():
            print(f"Found related employee: {e.get('EmployeeID')} - {e.get('FirstName')} {e.get('LastName')}")
            check_employee(e.get('EmployeeID'))
