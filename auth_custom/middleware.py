from .models import DynamoUser, DynamoAnonymousUser
from core.dynamodb_service import UsersTable, EmployeesTable
import logging
import time
from django.shortcuts import redirect
from django.contrib import messages


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
                    session_token = request.session.get('session_token')
                    db_token = user_data.get('ActiveSessionToken')
                    
                    if db_token and session_token != db_token:
                        if 'user_id' in request.session:
                            del request.session['user_id']
                        if 'session_token' in request.session:
                            del request.session['session_token']
                        
                        path = request.path
                        if not (path.endswith('/notifications/poll/') or 
                                path.endswith('/api/register-device/') or 
                                path.endswith('/api/unregister-device/')):
                            messages.warning(request, "Your session has been terminated because you logged in on another device.")
                            return redirect('login')
                        
                        request.user = DynamoAnonymousUser()
                    else:
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
                            
                            # Update LastActivityTime in the database for non-polling page requests
                            path = request.path
                            if not (path.endswith('/notifications/poll/') or 
                                    path.endswith('/api/register-device/') or 
                                    path.endswith('/api/unregister-device/')):
                                import time
                                try:
                                    UsersTable.update_item(
                                        Key={'UserID': user_id},
                                        UpdateExpression="SET LastActivityTime = :act_time",
                                        ExpressionAttributeValues={":act_time": int(time.time())}
                                    )
                                except Exception as e:
                                    logger.error(f"Error updating LastActivityTime: {e}")
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


class SessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            from core.utils import is_mobile_app
            if not is_mobile_app(request):
                # Skip checking for programmatic background/polling requests
                path = request.path
                if not (path.endswith('/notifications/poll/') or 
                        path.endswith('/api/register-device/') or 
                        path.endswith('/api/unregister-device/')):
                    
                    last_activity = request.session.get('last_activity')
                    now = time.time()
                    TIMEOUT_SECONDS = 3600  # 1 hour
                    
                    if last_activity:
                        elapsed = now - last_activity
                        if elapsed > TIMEOUT_SECONDS:
                            # Flush the session
                            if 'user_id' in request.session:
                                del request.session['user_id']
                            if 'last_activity' in request.session:
                                del request.session['last_activity']
                            
                            messages.warning(request, "Your session has expired due to inactivity. Please log in again.")
                            return redirect('login')
                    
                    request.session['last_activity'] = now
                
        response = self.get_response(request)
        return response

