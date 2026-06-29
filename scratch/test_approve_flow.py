import os
import django
import time
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import LeaveRequestsTable, EmployeesTable, UsersTable
from leave.views import ApproveLeaveView
from django.test import RequestFactory
from auth_custom.models import DynamoUser
from django.contrib.messages.storage.fallback import FallbackStorage

def test_full_approval_flow(emp_id, leave_date):
    print(f"--- Full Approval Flow Test for {emp_id} on {leave_date} ---")
    
    # 1. Ensure a pending leave exists
    item = {
        'EmployeeID': emp_id,
        'LeaveDate': leave_date,
        'Type': 'Casual Leave (CL)',
        'Status': 'Pending',
        'DaysCount': '1',
        'EndDate': leave_date,
        'Reason': 'Test Sync Notification'
    }
    LeaveRequestsTable.put_item(item)
    print(f"Created pending leave for {emp_id}")
    
    # 2. Simulate GET request to ApproveLeaveView
    factory = RequestFactory()
    request = factory.get(f'/leave/approve/{emp_id}/{leave_date}/')
    
    # Setup messages
    setattr(request, 'session', 'session')
    messages = FallbackStorage(request)
    setattr(request, '_messages', messages)
    
    # Mock user with manager role
    hr_users = [u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN']
    if not hr_users:
        print("No HR user found for mock.")
        return
    
    request.user = DynamoUser(hr_users[0])
    
    view = ApproveLeaveView.as_view()
    response = view(request, emp_id=emp_id, leave_date=leave_date)
    print(f"View response status: {response.status_code}")
    
    print("Waiting for thread...")
    time.sleep(5)
    print("Test complete.")

test_full_approval_flow('900911', '2026-11-11')
