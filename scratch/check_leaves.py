import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import LeaveRequestsTable

print("Scanning Leave Requests...")
for leave in LeaveRequestsTable.scan():
    print(f"EmpID: {leave.get('EmployeeID')}, Date: {leave.get('LeaveDate')}, Days: {leave.get('DaysCount')}, Type: {leave.get('Type')}, Status: {leave.get('Status')}")
