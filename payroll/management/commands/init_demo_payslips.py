from django.core.management.base import BaseCommand
from core.dynamodb_service import UsersTable, PayslipsTable
import random

class Command(BaseCommand):
    help = 'Initialize Demo Payslips for Lurnexa HR Admin'

    def handle(self, *args, **kwargs):
        self.stdout.write('Generating demo payslips...')
        
        users = UsersTable.scan()
        months = ['Jan 2026', 'Feb 2026', 'Mar 2026']

        for user in users:
            emp_id = user.get('EmployeeID')
            role = user.get('Role')
            
            base_salary = 5000 if role == 'HR ADMIN' else (4000 if role == 'Manager' else 3000)
            
            for month in months:
                basic = base_salary + random.randint(-200, 200)
                allowances = random.randint(500, 1000)
                tax = (basic + allowances) * 0.15
                net = (basic + allowances) - tax
                
                item = {
                    'EmployeeID': emp_id,
                    'MonthYear': month,
                    'Basic': str(round(basic, 2)),
                    'Allowances': str(round(allowances, 2)),
                    'Tax': str(round(tax, 2)),
                    'NetPay': str(round(net, 2)),
                    'Status': 'Paid'
                }
                PayslipsTable.put_item(item)
                self.stdout.write(f"Generated payslip for {user.get('Email')} - {month}")

        self.stdout.write(self.style.SUCCESS('Done generating demo payslips.'))
