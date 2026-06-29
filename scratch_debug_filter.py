import os
import sys
import django

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lurnexa_hrms.settings")
django.setup()

from attendance.views import HRAttendanceView
from django.test import RequestFactory
from core.dynamodb_service import UsersTable, EmployeesTable, LeaveRequestsTable
import datetime

# Let's create a fake leave for today to ensure there's at least one
today = datetime.date.today().isoformat()
emp = EmployeesTable.scan()[0] # Get first employee
eid = emp.get('EmployeeID')

print(f"Creating test leave for {eid} on {today}")
LeaveRequestsTable.put_item({
    'EmployeeID': eid,
    'LeaveDate': today,
    'EndDate': today,
    'Status': 'Approved',
    'Type': 'Sick Leave (SL)'
})

factory = RequestFactory()
request = factory.get(f'/attendance/hr/?leave_type=Sick+Leave&date={today}')
from django.contrib.auth import get_user_model
User = get_user_model()
request.user = User.objects.first()

view = HRAttendanceView()
view.request = request

context = view.get_context_data()
print("All count:", context.get('all_count'))
for member in context.get('all_members_list', []):
    print("MEMBER:", member)
