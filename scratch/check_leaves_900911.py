import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import LeaveRequestsTable
from boto3.dynamodb.conditions import Key

def check_leaves(emp_id):
    print(f"--- Leave Requests for {emp_id} ---")
    leaves = LeaveRequestsTable.query(
        KeyConditionExpression=Key('EmployeeID').eq(emp_id)
    )
    for l in leaves:
        print(f"Date: {l.get('LeaveDate')} | Type: {l.get('Type')} | Status: {l.get('Status')}")

check_leaves('900911')
