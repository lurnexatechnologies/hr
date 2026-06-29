import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import LeaveRequestsTable

item = LeaveRequestsTable.scan(Limit=1)
if item:
    print(f"Sample Item: {item[0]}")
    print(f"Keys: {item[0].keys()}")
