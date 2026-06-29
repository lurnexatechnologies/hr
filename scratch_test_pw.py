import os, django, bcrypt
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()
from core.dynamodb_service import UsersTable

user_rec = next((u for u in UsersTable.scan() if u.get('Email') == 'hr@lurnexa.com'), None)
if user_rec:
    new_hash = bcrypt.hashpw(b'Password@123', bcrypt.gensalt(12)).decode('utf-8')
    user_rec['PasswordHash'] = new_hash
    UsersTable.put_item(user_rec)
    print("Updated password for hr@lurnexa.com to Password@123 successfully")
else:
    print("User hr@lurnexa.com not found")

