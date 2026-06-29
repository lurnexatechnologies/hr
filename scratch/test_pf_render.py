import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from django.test import Client
from core.dynamodb_service import UsersTable

c = Client()
user_items = UsersTable.scan()
user = next((u for u in user_items if u.get('Email') == 'hr@lurnexa.com'), None)

if user:
    login_response = c.post('/auth/login/', {'username': 'hr@lurnexa.com', 'password': 'Password@123'})
    print("LOGIN STATUS CODE:", login_response.status_code)
    
    response = c.get('/payroll/pf/management/?page=2')
    print("STATUS CODE:", response.status_code)
    if response.status_code == 302:
        print("Redirected to:", response.url)
    html = response.content.decode('utf-8')
    print("HTML Length:", len(html))
    
    # Search for pagination div
    import re
    footer_match = re.search(r'<div class="card-footer.*?</nav>\s*</div>', html, re.DOTALL)
    if footer_match:
        print("FOOTER HTML:")
        print(footer_match.group(0))
    else:
        print("Footer not found")
else:
    print("User not found")
