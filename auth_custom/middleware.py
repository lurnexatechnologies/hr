from .models import DynamoUser, DynamoAnonymousUser
from core.dynamodb_service import UsersTable, EmployeesTable
import logging

logger = logging.getLogger(__name__)

class DynamoDBAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.session.get('user_id')
        if user_id:
            try:
                user_data = UsersTable.get_item({'UserID': user_id})
                if user_data:
                    # optionally fetch employee details to enrich user object
                    emp_id = user_data.get('EmployeeID')
                    if emp_id:
                        emp_data = EmployeesTable.get_item({'EmployeeID': emp_id})
                        if emp_data:
                            user_data['FirstName'] = emp_data.get('FirstName', '')
                            user_data['LastName'] = emp_data.get('LastName', '')
                            user_data['PassportPhoto'] = emp_data.get('PassportPhoto')
                            user_data['OnboardingStatus'] = emp_data.get('OnboardingStatus', 'Approved')
                            user_data['RejectionReason'] = emp_data.get('RejectionReason', '')
                    if not user_data.get('IsActive', True):
                        if 'user_id' in request.session:
                            del request.session['user_id']
                            from django.contrib import messages
                            messages.error(request, "This profile is deactivated. Please contact HR to reactivate.")
                        request.user = DynamoAnonymousUser()
                    else:
                        request.user = DynamoUser(user_data)
                else:
                    request.user = DynamoAnonymousUser()
            except Exception as e:
                logger.error(f"Error fetching user from dynamodb: {e}")
                request.user = DynamoAnonymousUser()
        else:
            request.user = DynamoAnonymousUser()
        
        response = self.get_response(request)
        
        # Prevent caching of all pages to secure browser history (Back/Forward)
        # This ensures that 'Back' clicks always hit the server to trigger session checks.
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
            
        return response
