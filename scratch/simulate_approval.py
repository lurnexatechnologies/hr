import os
import django
import time
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.utils import send_notification
from core.dynamodb_service import EmployeesTable

def simulate_approval(emp_id, leave_date):
    print(f"Simulating approval for {emp_id} on {leave_date}")
    employee = EmployeesTable.get_item({'EmployeeID': emp_id})
    if not employee:
        print(f"ERROR: Employee {emp_id} not found")
        return
    
    send_notification(
        employee_id=emp_id,
        title="Leave Approved (Simulated)",
        message=f"Your leave from {leave_date} has been approved.",
        n_type='Leave',
        icon='fa-calendar-check',
        color='success',
        email_subject="Leave Request Approved (Test Wait)",
        email_body=f"Hi {employee.get('FirstName')},\n\nYour leave request has been APPROVED."
    )
    print("Notification call made, waiting for thread...")
    time.sleep(10) # Wait for email thread to finish
    print("Simulation finished.")

simulate_approval('900911', '2026-05-13')
