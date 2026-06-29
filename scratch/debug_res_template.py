import os
import sys
import django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from django.test import Client
from core.dynamodb_service import UsersTable
import re

client = Client()
sa_users = [u for u in UsersTable.scan() if u.get('Role') == 'Super admin']
if sa_users:
    sa = sa_users[0]
    engine = django.utils.module_loading.import_string(django.conf.settings.SESSION_ENGINE)
    store = engine.SessionStore()
    store['user_id'] = sa['UserID']
    store.save()
    client.cookies[django.conf.settings.SESSION_COOKIE_NAME] = store.session_key
    
    response = client.get('/workflows/resignation/approvals/?tab=history')
    print("Response status:", response.status_code)
    html = response.content.decode('utf-8')
    history_items = re.findall(r'<div class="fw-bold text-main">(.*?)</div>', html)
    print("Items found in HTML (both pending and history):")
    for item in history_items:
        print(item)
else:
    print("No Super admin found")
