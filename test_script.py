import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()
from django.test import Client
from core.dynamodb_service import UsersTable, EmployeesTable

if __name__ == '__main__':
    c = Client()
    session = c.session

    user_items = UsersTable.scan()
    user = next((u for u in user_items if u.get('EmployeeID') == 'EMP-4C832A'), None)
    if user:
        session['user_id'] = user.get('UserID')
        session.save()
        response = c.get('/employees/documents/letters/')
        letters_context = response.context['letters']
        print('Context length:', len(letters_context))
        html = response.content.decode('utf-8')
        import re
        matches = re.findall(r'data-type="(.*?)"', html)
        print('Rendered types:', matches)

