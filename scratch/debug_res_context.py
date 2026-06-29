import os
import sys
import django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from django.test import RequestFactory
from workflows.views import ResignationApprovalsView
from core.dynamodb_service import UsersTable

factory = RequestFactory()
request = factory.get('/workflows/resignation/approvals/?tab=history')

# Mock user
class MockUser:
    def __init__(self):
        self.role = 'Super admin'
        self.is_authenticated = True
request.user = MockUser()

view = ResignationApprovalsView()
view.request = request
view.kwargs = {}
context = view.get_context_data()

print(f"Pending count: {context['pending_count']}")
print(f"Processed count: {context['processed_count']}")
for r in context['processed_resignations'].object_list:
    print(f"History: {r['EmployeeID']} - Status: {r['Status']}")
