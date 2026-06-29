import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable

emp = EmployeesTable.get_item({'EmployeeID': 'LT20265006'})
print(f"Employee LT20265006: {emp}")
