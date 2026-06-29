import os
import sys
import django
import bcrypt

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import UsersTable

# Find hr@lurnexa.com
users = UsersTable.query(
    IndexName='EmailIndex',
    KeyConditionExpression='Email = :e',
    ExpressionAttributeValues={':e': 'hr@lurnexa.com'}
)

if users:
    user = users[0]
    hashed_pw = bcrypt.hashpw(b"Lurnexa@123", bcrypt.gensalt()).decode('utf-8')
    UsersTable.update_item(
        Key={'UserID': user['UserID']},
        UpdateExpression="SET PasswordHash = :p",
        ExpressionAttributeValues={':p': hashed_pw}
    )
    print("Password updated successfully for hr@lurnexa.com to 'Lurnexa@123'")
else:
    print("User hr@lurnexa.com not found")
