import os
import sys
import django

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable
for emp in EmployeesTable.scan():
    print(f"ID: {emp.get('EmployeeID')}, Joined: {emp.get('JoinedDate')}, SL: {emp.get('Balance_SL')}, CL: {emp.get('Balance_CL')}, LastRefresh: {emp.get('LastLeaveRefresh')}")
