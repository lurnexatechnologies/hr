import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import LeaveRequestsTable

print("Scanning None Days Count Leaves:")
for leave in LeaveRequestsTable.scan():
    if leave.get('DaysCount') is None:
        print(leave)
