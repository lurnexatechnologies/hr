import os
import django
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lurnexa_hrms.settings")
django.setup()

from core.dynamodb_service import LeaveRequestsTable

leaves = LeaveRequestsTable.scan()
for l in leaves:
    print(l)
