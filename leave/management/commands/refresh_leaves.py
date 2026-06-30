from django.core.management.base import BaseCommand
from core.dynamodb_service import EmployeesTable
from core.utils import refresh_monthly_leaves, get_local_date
import datetime

class Command(BaseCommand):
    help = 'Refresh employee leave balances on the 1st of the month'

    def handle(self, *args, **kwargs):
        today = get_local_date()
        if today.day != 1:
            self.stdout.write(self.style.WARNING(f"Today is not the 1st (it's the {today.day}). Refresh skipped."))
            # In a real scenario, you might want a --force flag.
            return

        self.stdout.write(f"Starting monthly leave refresh for {today.strftime('%B %Y')}...")
        
        employees = EmployeesTable.scan()
        count = 0
        refreshed_count = 0
        
        for emp in employees:
            count += 1
            if refresh_monthly_leaves(emp):
                refreshed_count += 1
        
        self.stdout.write(self.style.SUCCESS(
            f"Done! Processed {count} employees. Refreshed {refreshed_count} employees."
        ))
