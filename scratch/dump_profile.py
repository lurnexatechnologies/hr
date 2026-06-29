import os
import django
import sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
sys.path.append(os.path.abspath('.'))
django.setup()

from django.test import RequestFactory
from core.dynamodb_service import EmployeesTable, UsersTable
from auth_custom.models import DynamoUser
from employees.views import DeleteCertificateView

class MockMessages:
    def __init__(self):
        self.messages = []
    def add(self, level, message, extra_tags=''):
        self.messages.append(message)
    def __iter__(self):
        return iter(self.messages)

# Print initial certificates
print("INITIAL CERTS:", EmployeesTable.get_item({'EmployeeID': 'EMP-A7A90B'}).get('Certificates'))

# Create a mock request and authenticate it
user_data = UsersTable.get_item({'UserID': 'a7a90bcb-5769-4516-8cc2-c890ff330642'})
user = DynamoUser(user_data)

factory = RequestFactory()
request = factory.post('/employees/certificates/EMP-A7A90B/9c86014d-3862-46e6-a98d-c6d0e426e51d/delete/')
request.user = user
mock_msgs = MockMessages()
setattr(request, '_messages', mock_msgs)

# Call the view directly
response = DeleteCertificateView.as_view()(request, emp_id='EMP-A7A90B', cert_id='9c86014d-3862-46e6-a98d-c6d0e426e51d')
print("STATUS CODE:", response.status_code)

# Print messages
print("MESSAGES:", mock_msgs.messages)

# Print final certificates
print("FINAL CERTS:", EmployeesTable.get_item({'EmployeeID': 'EMP-A7A90B'}).get('Certificates'))
