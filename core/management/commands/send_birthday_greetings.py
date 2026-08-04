import datetime
from core.utils import get_local_date, send_birthday_wish_email
from django.core.management.base import BaseCommand
from core.dynamodb_service import EmployeesTable, OrganizationsTable

class Command(BaseCommand):
    help = 'Sends professional birthday greetings email to active employees celebrating their birthday today.'

    def handle(self, *args, **options):
        today = get_local_date()
        today_str = today.strftime('%m-%d')
        
        self.stdout.write(self.style.NOTICE(f"Checking birthdays for today ({today_str})..."))

        # Fetch all active employees
        employees = EmployeesTable.scan()
        active_employees = [e for e in employees if e.get('OnboardingStatus') == 'Approved' and e.get('IsActive', True) != False]

        success_count = 0
        error_count = 0

        # Cache organization objects
        org_cache = {}

        for emp in active_employees:
            dob = emp.get('DOB')
            if not dob or len(dob) < 10:
                continue

            dob_md = dob[5:10] # MM-DD
            if dob_md == today_str:
                org_id = emp.get('OrgID')
                org = None
                if org_id:
                    if org_id not in org_cache:
                        org_cache[org_id] = OrganizationsTable.get_item({'OrgID': org_id})
                    org = org_cache.get(org_id)

                self.stdout.write(self.style.NOTICE(f"Sending birthday wish email to {emp.get('FirstName')} {emp.get('LastName')} ({emp.get('Email')})..."))
                result = send_birthday_wish_email(emp, org)
                if result:
                    success_count += 1
                else:
                    error_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully processed birthday emails. Sent: {success_count}, Errors/Skipped: {error_count}"))
