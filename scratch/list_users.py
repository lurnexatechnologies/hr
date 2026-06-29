import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import UsersTable
for user in UsersTable.scan():
    print(f"UserID: {user.get('UserID')}, Email: {user.get('Email')}, Role: {user.get('Role')}, EmployeeID: {user.get('EmployeeID')}")
