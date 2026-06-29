import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import AttendanceTable, WFHRequestsTable
from boto3.dynamodb.conditions import Key

def check_attendance_wfh(emp_id):
    print(f"--- Attendance for {emp_id} ---")
    recs = AttendanceTable.query(KeyConditionExpression=Key('EmployeeID').eq(emp_id))
    for r in recs:
        print(r)
        
    print(f"\n--- WFH Requests for {emp_id} ---")
    wfhs = WFHRequestsTable.query(KeyConditionExpression=Key('EmployeeID').eq(emp_id))
    for w in wfhs:
        print(w)

check_attendance_wfh('900911')
