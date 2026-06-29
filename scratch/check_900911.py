import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable, UsersTable
from boto3.dynamodb.conditions import Key

def check_emp(emp_id):
    emp = EmployeesTable.get_item({'EmployeeID': emp_id})
    print(f"--- Checking Employee ID: {emp_id} ---")
    print(f"Employee Record: {emp}")
    
    users = UsersTable.scan(
        FilterExpression="EmployeeID = :eid",
        ExpressionAttributeValues={":eid": emp_id}
    )
    print(f"Users found by EmployeeID scan: {users}")

check_emp('900911')
