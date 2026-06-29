import boto3
from django.conf import settings
import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import (
    UsersTable, LeaveRequestsTable, ResignationsTable, 
    ExpensesTable, WFHRequestsTable, EmployeesTable
)

def migrate():
    print("Starting migration: HR -> HR ADMIN")
    
    # 1. Update UsersTable
    print("Updating Lurnexa_Users...")
    users = UsersTable.scan()
    for user in users:
        if user.get('Role') == 'HR':
            print(f"Updating user {user.get('UserID')}...")
            UsersTable.update_item(
                Key={'UserID': user['UserID']},
                UpdateExpression="SET #r = :val",
                ExpressionAttributeNames={'#r': 'Role'},
                ExpressionAttributeValues={':val': 'HR ADMIN'}
            )

    # 2. Update LeaveRequestsTable
    print("Updating Lurnexa_LeaveRequests...")
    leaves = LeaveRequestsTable.scan()
    for leave in leaves:
        if leave.get('ApproverRole') == 'HR':
            print(f"Updating leave for {leave.get('EmployeeID')} on {leave.get('LeaveDate')}...")
            LeaveRequestsTable.update_item(
                Key={'EmployeeID': leave['EmployeeID'], 'LeaveDate': leave['LeaveDate']},
                UpdateExpression="SET ApproverRole = :val",
                ExpressionAttributeValues={':val': 'HR ADMIN'}
            )

    # 3. Update ResignationsTable
    print("Updating Lurnexa_Resignations...")
    resignations = ResignationsTable.scan()
    for r in resignations:
        if r.get('Status') == 'Pending HR Review':
            print(f"Updating resignation for {r.get('EmployeeID')}...")
            ResignationsTable.update_item(
                Key={'EmployeeID': r['EmployeeID']},
                UpdateExpression="SET #s = :val",
                ExpressionAttributeNames={'#s': 'Status'},
                ExpressionAttributeValues={':val': 'Pending HR ADMIN Review'}
            )

    # 4. Update ExpensesTable
    print("Updating Lurnexa_Expenses...")
    expenses = ExpensesTable.scan()
    for e in expenses:
        if e.get('Status') == 'Pending HR Approval':
            print(f"Updating expense {e.get('RequestID')} for {e.get('EmployeeID')}...")
            ExpensesTable.update_item(
                Key={'EmployeeID': e['EmployeeID'], 'RequestID': e['RequestID']},
                UpdateExpression="SET #s = :val",
                ExpressionAttributeNames={'#s': 'Status'},
                ExpressionAttributeValues={':val': 'Pending HR ADMIN Approval'}
            )

    # 5. Update WFHRequestsTable
    print("Updating Lurnexa_WFHRequests...")
    wfhs = WFHRequestsTable.scan()
    for w in wfhs:
        if w.get('Status') == 'Pending HR Approval':
            print(f"Updating WFH {w.get('RequestID')} for {w.get('EmployeeID')}...")
            WFHRequestsTable.update_item(
                Key={'EmployeeID': w['EmployeeID'], 'RequestID': w['RequestID']},
                UpdateExpression="SET #s = :val",
                ExpressionAttributeNames={'#s': 'Status'},
                ExpressionAttributeValues={':val': 'Pending HR ADMIN Approval'}
            )
            
    # 6. Update EmployeesTable (Designation if it's 'HR')
    print("Updating Lurnexa_Employees (Designation)...")
    employees = EmployeesTable.scan()
    for emp in employees:
        if emp.get('Designation') == 'HR':
            print(f"Updating designation for employee {emp.get('EmployeeID')}...")
            EmployeesTable.update_item(
                Key={'EmployeeID': emp['EmployeeID']},
                UpdateExpression="SET Designation = :val",
                ExpressionAttributeValues={':val': 'HR ADMIN'}
            )

    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate()
