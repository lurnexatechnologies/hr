from django.core.management.base import BaseCommand
from core.dynamodb_service import EmployeesTable, PayslipsTable
from core.utils import get_local_now
import datetime

class Command(BaseCommand):
    help = 'Generate monthly payslips for all employees'

    def handle(self, *args, **kwargs):
        self.stdout.write('Generating payslips for current month...')
        
        now = get_local_now()
        month_year = now.strftime('%Y-%m') # e.g. 2026-04
        
        employees = EmployeesTable.scan()
        count = 0
        
        for emp in employees:
            emp_id = emp.get('EmployeeID')
            
            # Check if payslip already exists for this month to avoid duplicates
            existing = PayslipsTable.get_item({'EmployeeID': emp_id, 'MonthYear': month_year})
            if existing:
                continue
                
            # Demo calculation - random/static based on role
            base = 5000 if emp.get('Designation') == 'HR ADMIN' else 4000
            if emp.get('Designation') == 'Manager': base = 6500
            
            allow = base * 0.20
            tax = (base + allow) * 0.15
            net = (base + allow) - tax
            
            payslip_item = {
                'EmployeeID': emp_id,
                'MonthYear': month_year,
                'Basic': str(base),
                'Allowances': str(allow),
                'Tax': str(tax),
                'NetPay': str(net)
            }
            PayslipsTable.put_item(payslip_item)
            count += 1
            
        self.stdout.write(self.style.SUCCESS(f'Successfully generated {count} payslips for {month_year}'))
