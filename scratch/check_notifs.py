import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import NotificationsTable
from boto3.dynamodb.conditions import Key

def check_notifications(emp_id):
    print(f"--- Notifications for {emp_id} ---")
    notifs = NotificationsTable.query(
        KeyConditionExpression=Key('EmployeeID').eq(emp_id)
    )
    # Sort by timestamp
    sorted_notifs = sorted(notifs, key=lambda x: x.get('Timestamp', ''), reverse=True)
    for n in sorted_notifs[:5]:
        print(f"[{n.get('Timestamp')}] {n.get('Title')}: {n.get('Message')}")

check_notifications('900911')
