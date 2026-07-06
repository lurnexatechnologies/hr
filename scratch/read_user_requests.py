import os, django, sys
sys.path.append(r"C:\Users\ADMIN\Documents\Lurnexa\HRMS")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()
from core.dynamodb_service import UsersTable

if __name__ == '__main__':
    users = UsersTable.scan()
    for u in users[:2]:
        print(u)
