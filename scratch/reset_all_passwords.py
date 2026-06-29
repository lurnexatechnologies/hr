import os, sys, django, bcrypt
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()
from core.dynamodb_service import UsersTable

emails_to_reset = ['superadmin@lurnexa.com', 'hr@lurnexa.com', 'manager@lurnexa.com', 'employee@lurnexa.com']
new_hash = bcrypt.hashpw(b'Password@123', bcrypt.gensalt(12)).decode('utf-8')

for email in emails_to_reset:
    user_recs = [u for u in UsersTable.scan() if u.get('Email') == email]
    if user_recs:
        for user_rec in user_recs:
            user_rec['PasswordHash'] = new_hash
            UsersTable.put_item(user_rec)
            print(f"Updated password for {email} ({user_rec.get('UserID')}) to Password@123 successfully")
    else:
        print(f"User {email} not found")
