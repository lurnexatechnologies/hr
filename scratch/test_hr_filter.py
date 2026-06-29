import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lurnexa_hrms.settings")
django.setup()

from attendance.views import HRAttendanceView
from django.test import RequestFactory

factory = RequestFactory()
# Simulate a request with a leave_type filter for today
request = factory.get('/attendance/hr/?leave_type=Sick+Leave')
# Create a dummy user object with HR role
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    user = User.objects.get(username='hradmin') # or whatever
except:
    user = User.objects.first()
request.user = user

view = HRAttendanceView()
view.request = request

try:
    context = view.get_context_data()
    print("all_count:", context.get('all_count'))
    print("leave_count:", context.get('leave_count'))
    for emp in context.get('all_members_list', []):
        print(emp)
except Exception as e:
    print("Error:", e)
