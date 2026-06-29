import os
import sys
import django

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lurnexa_hrms.settings")
django.setup()

from attendance.views import HRAttendanceView
from django.test import RequestFactory
import datetime

today = datetime.date.today().isoformat()
factory = RequestFactory()
request = factory.get(f'/attendance/hr/?leave_type=Sick+Leave&date={today}&tab=onleave')

from django.contrib.auth import get_user_model
User = get_user_model()
request.user = User.objects.first()

view = HRAttendanceView()
view.request = request

context = view.get_context_data()
print("All count:", context.get('all_count'))
print("Leave count:", context.get('leave_count'))
print("On leave employees:", list(context.get('on_leave_employees', [])))

