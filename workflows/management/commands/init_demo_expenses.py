from django.core.management.base import BaseCommand
from core.dynamodb_service import ExpensesTable
import uuid
import datetime

class Command(BaseCommand):
    help = 'Initialize Demo Expenses'

    def handle(self, *args, **kwargs):
        self.stdout.write('Generating demo expenses...')
        
        expenses = [
            {
                'EmployeeID': 'LT-26003', # Charlie Worker
                'RequestID': str(uuid.uuid4()),
                'Amount': '150.00',
                'Category': 'Travel',
                'Description': 'Flight to conference in San Francisco',
                'Status': 'Pending',
                'Date': datetime.date.today().isoformat(),
                'ReceiptImage': 'https://picsum.photos/seed/flight/600/800'
            },
            {
                'EmployeeID': 'LT-26003',
                'RequestID': str(uuid.uuid4()),
                'Amount': '45.50',
                'Category': 'Meals',
                'Description': 'Client dinner at Blue Bayou',
                'Status': 'Pending',
                'Date': datetime.date.today().isoformat(),
                'ReceiptImage': 'https://picsum.photos/seed/meal/600/800'
            },
            {
                'EmployeeID': 'LT-26001', # Alice Admin
                'RequestID': str(uuid.uuid4()),
                'Amount': '25.00',
                'Category': 'Office Supplies',
                'Description': 'New keyboard for desk',
                'Status': 'Pending',
                'Date': datetime.date.today().isoformat(),
                'ReceiptImage': 'https://picsum.photos/seed/supplies/600/800'
            }
        ]

        for exp in expenses:
            ExpensesTable.put_item(exp)
            self.stdout.write(f"Generated expense for {exp['EmployeeID']} - ${exp['Amount']}")

        self.stdout.write(self.style.SUCCESS('Done generating demo expenses.'))
