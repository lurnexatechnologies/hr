import os
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import initialize_dynamodb_tables, UsersTable
from core.management.commands.init_demo_users import Command as InitDemoUsers

def main():
    print("Initializing Tables...")
    try:
        initialize_dynamodb_tables()
    except Exception as e:
        print(f"Init Tables Error: {e}")
        
    print("Running Demo Users Init...")
    try:
        cmd = InitDemoUsers()
        cmd.handle()
    except Exception as e:
        print(f"Init Demo Users Error: {e}")
        
    print("Verifying Users Table...")
    try:
        users = UsersTable.scan()
        print(f"Users found: {len(users)}")
        for u in users:
            print(f"- {u.get('Email')} ({u.get('Role')})")
    except Exception as e:
        print(f"Verify Error: {e}")

if __name__ == "__main__":
    main()
