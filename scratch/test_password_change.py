import os
import sys
import django
import bcrypt
from django.contrib.auth.hashers import check_password

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import UsersTable
from django.test import RequestFactory
from core.views import SettingsView
from django.contrib.messages.storage.fallback import FallbackStorage
from auth_custom.models import DynamoUser

def test_password_change_flow():
    print("Starting test_password_change_flow...")

    # Find the user
    from boto3.dynamodb.conditions import Key
    users = UsersTable.query(
        IndexName='EmailIndex',
        KeyConditionExpression=Key('Email').eq('hr@lurnexa.com')
    )
    if not users:
        print("Error: User hr@lurnexa.com not found in DynamoDB.")
        return
    user_rec = users[0]

    # Store initial password hash or plaintext password
    initial_hash = user_rec.get('PasswordHash', '')
    if not initial_hash:
        initial_hash = user_rec.get('Password', '')

    print(f"Initial Password Hash/Val: {initial_hash}")

    # Set password to a known initial state 'Password@123'
    from django.contrib.auth.hashers import make_password
    user_rec['PasswordHash'] = make_password('Password@123')
    if 'Password' in user_rec:
        del user_rec['Password']
    UsersTable.put_item(user_rec)
    print("Reset password of hr@lurnexa.com to 'Password@123'")

    # Set up RequestFactory
    factory = RequestFactory()
    
    # 1. Test Incorrect Current Password
    print("\n--- Submitting Password Change with Incorrect Current Password ---")
    request = factory.post('/settings/', {
        'first_name': 'HR',
        'last_name': 'Admin',
        'current_password': 'WrongPassword123',
        'new_password': 'NewPassword@123',
        'confirm_password': 'NewPassword@123'
    })
    # Add session and messages support
    request.session = {}
    request.user = DynamoUser(user_rec)
    
    # Add messages middleware support
    messages = FallbackStorage(request)
    setattr(request, '_messages', messages)

    view = SettingsView.as_view()
    response = view(request)
    
    # Check messages
    msg_texts = [m.message for m in messages]
    print(f"Messages: {msg_texts}")
    assert "Incorrect current password." in msg_texts, "Should reject incorrect current password"
    print("[OK] Incorrect Current Password rejected successfully.")

    # 2. Test Correct Password Change
    print("\n--- Submitting Password Change with Correct Credentials ---")
    request = factory.post('/settings/', {
        'first_name': 'HR',
        'last_name': 'Admin',
        'current_password': 'Password@123',
        'new_password': 'NewPassword@123',
        'confirm_password': 'NewPassword@123'
    })
    request.session = {}
    request.user = DynamoUser(user_rec)
    
    messages = FallbackStorage(request)
    setattr(request, '_messages', messages)
    
    response = view(request)
    
    msg_texts = [m.message for m in messages]
    print(f"Messages: {msg_texts}")
    assert "Account settings and password updated successfully." in msg_texts, "Should report successful password change"
    print("[OK] Password changed successfully in SettingsView.")

    # Retrieve updated user record and verify
    updated_user = UsersTable.get_item({'UserID': user_rec['UserID']})
    new_hash = updated_user.get('PasswordHash')
    print(f"New Password Hash: {new_hash}")
    
    # Verify we can authenticate with the new password
    assert check_password('NewPassword@123', new_hash), "Should authenticate with new password"
    print("[OK] New password verified successfully.")

    # Restore initial state so we don't permanently alter DB state for tests
    updated_user['PasswordHash'] = initial_hash
    UsersTable.put_item(updated_user)
    print("\nRestored initial password state.")
    print("All tests passed successfully!")

if __name__ == '__main__':
    test_password_change_flow()
