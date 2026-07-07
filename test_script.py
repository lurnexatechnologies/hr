import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()
from django.test import RequestFactory
from core.dynamodb_service import UsersTable
from employees.views import AssetManagementView
from auth_custom.middleware import DynamoDBAuthMiddleware
from django.contrib.sessions.middleware import SessionMiddleware

if __name__ == '__main__':
    factory = RequestFactory()
    request = factory.get('/employees/assets/')
    
    # Apply SessionMiddleware manually
    def dummy_get_response(req):
        from django.http import HttpResponse
        return HttpResponse("OK")
    session_mw = SessionMiddleware(dummy_get_response)
    session_mw(request)
    
    # Find HR Admin user
    user = next((u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN'), None)
    if user:
        # Set user_id in session
        request.session['user_id'] = user.get('UserID')
        request.session.save()
        
        # Apply DynamoDBAuthMiddleware manually
        auth_mw = DynamoDBAuthMiddleware(dummy_get_response)
        auth_mw(request)
        
        print("Is Authenticated:", request.user.is_authenticated)
        print("User Role:", request.user.role)
        
        # Call the view
        view = AssetManagementView.as_view()
        response = view(request)
        
        print("Response status:", response.status_code)
        if hasattr(response, 'context_data'):
            context = response.context_data
            active_employees = context.get('active_employees', [])
            print("Active employees in context count:", len(active_employees))
            for emp in active_employees:
                print(f" - {emp.get('FirstName')} {emp.get('LastName')} (ID: {emp.get('EmployeeID')})")
        else:
            print("Response does not have context_data")
