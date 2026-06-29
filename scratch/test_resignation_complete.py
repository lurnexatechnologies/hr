import os
import sys
import django
import datetime

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from django.test import Client
from django.conf import settings
from django.contrib.messages import get_messages
from importlib import import_module
from core.dynamodb_service import (
    UsersTable, EmployeesTable, ResignationsTable, OnboardingTokensTable
)

def set_session_data(client, data):
    engine = import_module(settings.SESSION_ENGINE)
    store = engine.SessionStore()
    for k, v in data.items():
        store[k] = v
    store.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = store.session_key
    return store

def get_msg_texts(response):
    return [m.message for m in get_messages(response.wsgi_request)]

def run_resignation_tests():
    print("=== STARTING RESIGNATION WORKFLOW INTEGRATION TESTS ===")
    
    # 1. Setup client and environment
    client = Client()
    
    # Setup test identifiers
    emp_id_new = "LT-RES-NEW"
    emp_id_old = "LT-RES-OLD"
    emp_id_past = "LT-RES-PAST"
    
    user_id_new = "user-res-new"
    user_id_old = "user-res-old"
    user_id_past = "user-res-past"
    
    hr_emp_id = "LT-HR-ADMIN"
    hr_user_id = "user-hr-admin"
    
    # Clean up any existing records
    for eid in [emp_id_new, emp_id_old, emp_id_past]:
        EmployeesTable.delete_item(key={'EmployeeID': eid})
        ResignationsTable.delete_item(key={'EmployeeID': eid})
    for uid in [user_id_new, user_id_old, user_id_past, hr_user_id]:
        UsersTable.delete_item(key={'UserID': uid})
    EmployeesTable.delete_item(key={'EmployeeID': hr_emp_id})

    # Create HR Admin user for processing resignations
    UsersTable.put_item(item={'UserID': hr_user_id, 'Email': 'hr-admin@lurnexa.com', 'Role': 'HR ADMIN', 'EmployeeID': hr_emp_id, 'IsActive': True})
    EmployeesTable.put_item(item={'EmployeeID': hr_emp_id, 'UserID': hr_user_id, 'FirstName': 'HR', 'LastName': 'Admin', 'OnboardingStatus': 'Approved', 'IsActive': True})

    # Test Case 1: Employee joined < 60 days ago tries to resign
    print("\n--- Test Case 1: Tenure Check (<60 days service) ---")
    joined_recent = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
    UsersTable.put_item(item={'UserID': user_id_new, 'Email': 'res-new@lurnexa.com', 'Role': 'Employee', 'EmployeeID': emp_id_new, 'IsActive': True})
    EmployeesTable.put_item(item={'EmployeeID': emp_id_new, 'UserID': user_id_new, 'Email': 'res-new@lurnexa.com', 'FirstName': 'New', 'LastName': 'Employee', 'JoinedDate': joined_recent, 'OnboardingStatus': 'Approved', 'IsActive': True})
    
    # Authenticate as new employee
    client.cookies.clear()
    set_session_data(client, {'user_id': user_id_new})
    
    response = client.post('/workflows/resignation/', {
        'reason': 'Better Opportunity',
        'lwd': (datetime.date.today() + datetime.timedelta(days=60)).isoformat(),
        'comments': 'Leaving soon'
    }, follow=True)
    
    messages = get_msg_texts(response)
    print("Messages after attempting resignation for tenure < 60 days:")
    print(messages)
    assert any("after 60 days of service only" in m for m in messages), "Tenure check failed!"
    print("=> SUCCESS: Blocked resignation for employee with < 60 days tenure.")

    # Test Case 2: Employee joined > 60 days ago submits resignation & HR Rejects
    print("\n--- Test Case 2: HR Rejects Resignation ---")
    joined_old = (datetime.date.today() - datetime.timedelta(days=100)).isoformat()
    UsersTable.put_item(item={'UserID': user_id_old, 'Email': 'res-old@lurnexa.com', 'Role': 'Employee', 'EmployeeID': emp_id_old, 'IsActive': True})
    EmployeesTable.put_item(item={'EmployeeID': emp_id_old, 'UserID': user_id_old, 'Email': 'res-old@lurnexa.com', 'FirstName': 'Old', 'LastName': 'Employee', 'JoinedDate': joined_old, 'OnboardingStatus': 'Approved', 'IsActive': True})
    
    # Authenticate as old employee
    set_session_data(client, {'user_id': user_id_old})
    
    response = client.post('/workflows/resignation/', {
        'reason': 'Family reasons',
        'lwd': (datetime.date.today() + datetime.timedelta(days=60)).isoformat(),
        'comments': 'Applying resignation'
    }, follow=True)
    
    res_rec = ResignationsTable.get_item(key={'EmployeeID': emp_id_old})
    print(f"Resignation status after submission: {res_rec.get('Status')}")
    assert res_rec.get('Status') == 'Pending HR ADMIN Review', "Resignation status should be Pending HR ADMIN Review"

    # Authenticate as HR to Reject
    set_session_data(client, {'user_id': hr_user_id})
    
    response = client.get(f'/workflows/resignation/process/{emp_id_old}/reject/', follow=True)
    res_rec = ResignationsTable.get_item(key={'EmployeeID': emp_id_old})
    print(f"Resignation status after HR Rejection: {res_rec.get('Status')}")
    assert res_rec.get('Status') == 'Rejected', "Status should be Rejected"
    print("=> SUCCESS: Resignation successfully rejected.")

    # Test Case 3: Re-applying within 3 days cooling off period
    print("\n--- Test Case 3: Cooling Off Period Check ---")
    # Authenticate back as old employee
    set_session_data(client, {'user_id': user_id_old})
    
    response = client.post('/workflows/resignation/', {
        'reason': 'Family reasons revised',
        'lwd': (datetime.date.today() + datetime.timedelta(days=60)).isoformat(),
        'comments': 'Trying again'
    }, follow=True)
    messages = get_msg_texts(response)
    print("Messages after re-applying within cooling period:")
    print(messages)
    assert any("You can apply again in" in m for m in messages), "Cooling off check failed!"
    print("=> SUCCESS: Re-application blocked during cooling-off period.")

    # Test Case 4: Re-applying after cooling off period (Simulated) & HR Accepts (Future LWD)
    print("\n--- Test Case 4: HR Accepts Resignation (Future LWD) ---")
    # Simulate cooling off period passed by updating RejectedOn to 4 days ago
    four_days_ago = (datetime.datetime.now() - datetime.timedelta(days=4)).isoformat()
    ResignationsTable.update_item(
        Key={'EmployeeID': emp_id_old},
        UpdateExpression="SET RejectedOn = :d",
        ExpressionAttributeValues={':d': four_days_ago}
    )
    
    # Re-apply
    response = client.post('/workflows/resignation/', {
        'reason': 'Family reasons revised',
        'lwd': (datetime.date.today() + datetime.timedelta(days=60)).isoformat(),
        'comments': 'Trying again after 4 days'
    }, follow=True)
    
    res_rec = ResignationsTable.get_item(key={'EmployeeID': emp_id_old})
    assert res_rec.get('Status') == 'Pending HR ADMIN Review', "Status should be Pending Review"
    
    # HR approves
    set_session_data(client, {'user_id': hr_user_id})
    response = client.get(f'/workflows/resignation/process/{emp_id_old}/approve/', follow=True)
    
    res_rec = ResignationsTable.get_item(key={'EmployeeID': emp_id_old})
    print(f"Resignation status after HR Approval: {res_rec.get('Status')}")
    assert res_rec.get('Status') == 'Accepted Resignation', "Status should be Accepted Resignation"
    
    emp_rec = EmployeesTable.get_item(key={'EmployeeID': emp_id_old})
    print(f"Employee active status (Future LWD): {emp_rec.get('IsActive')}")
    assert emp_rec.get('IsActive') is True, "Employee should still be active for future LWD"
    print("=> SUCCESS: Resignation accepted for future LWD; employee remains active.")

    # Test Case 5: HR Accepts Resignation with Past LWD (Immediate Deactivation)
    print("\n--- Test Case 5: HR Accepts Resignation (Past LWD) ---")
    UsersTable.put_item(item={'UserID': user_id_past, 'Email': 'res-past@lurnexa.com', 'Role': 'Employee', 'EmployeeID': emp_id_past, 'IsActive': True})
    EmployeesTable.put_item(item={
        'EmployeeID': emp_id_past, 
        'UserID': user_id_past, 
        'Email': 'res-past@lurnexa.com', 
        'FirstName': 'Past', 
        'LastName': 'Employee', 
        'JoinedDate': joined_old, 
        'OnboardingStatus': 'Approved', 
        'IsActive': True,
        'Balance_SL': '10.0',
        'Balance_CL': '10.0'
    })
    
    # Submit resignation with past LWD
    set_session_data(client, {'user_id': user_id_past})
    past_lwd = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    # Bypass frontend/view min_lwd validation by putting directly or posting
    # Let's post it
    client.post('/workflows/resignation/', {
        'reason': 'Better offer',
        'lwd': past_lwd,
        'comments': 'Leaving immediately'
    }, follow=True)
    
    # HR Approves
    set_session_data(client, {'user_id': hr_user_id})
    client.get(f'/workflows/resignation/process/{emp_id_past}/approve/', follow=True)
    
    emp_rec = EmployeesTable.get_item(key={'EmployeeID': emp_id_past})
    user_rec = UsersTable.get_item(key={'UserID': user_id_past})
    print(f"Employee active status (Past LWD): {emp_rec.get('IsActive')}")
    print(f"User active status (Past LWD): {user_rec.get('IsActive')}")
    assert emp_rec.get('IsActive') is False, "Employee should be inactive"
    assert user_rec.get('IsActive') is False, "User should be inactive"
    print("=> SUCCESS: Resignation accepted for past LWD; employee/user deactivated immediately.")

    # Test Case 6: Verify Leave Refresh Protection for the deactivated employee
    print("\n--- Test Case 6: Leave Refresh Protection ---")
    from core.utils import refresh_monthly_leaves
    # Trigger leave refresh manually for the deactivated employee (LT-RES-PAST)
    # We will simulate January 1st by patching today's month/day inside refresh_monthly_leaves or just testing the check
    print("Simulating leave refresh call on deactivated employee...")
    # Modify today's date in a mock way or call refresh_monthly_leaves when today is the 1st
    # Let's check: if IsActive is False, it returns False and does not update anything
    result = refresh_monthly_leaves(emp_rec)
    print(f"Refresh monthly leaves returned: {result}")
    assert result is False, "Refresh should be skipped for inactive employee"
    
    # Clean up test records
    for eid in [emp_id_new, emp_id_old, emp_id_past]:
        EmployeesTable.delete_item(key={'EmployeeID': eid})
        ResignationsTable.delete_item(key={'EmployeeID': eid})
    for uid in [user_id_new, user_id_old, user_id_past, hr_user_id]:
        UsersTable.delete_item(key={'UserID': uid})
    EmployeesTable.delete_item(key={'EmployeeID': hr_emp_id})
    print("\n=== ALL RESIGNATION WORKFLOW INTEGRATION TESTS PASSED SUCCESSFULLY ===")

if __name__ == '__main__':
    run_resignation_tests()
