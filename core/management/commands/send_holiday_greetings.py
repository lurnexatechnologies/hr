import datetime
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from core.dynamodb_service import HolidaysTable, EmployeesTable
import threading

class Command(BaseCommand):
    help = 'Sends holiday greetings to all active employees at 12 AM on the day of a holiday.'

    def handle(self, *args, **options):
        today = datetime.date.today().isoformat()
        
        # 1. Fetch all holidays
        holidays = HolidaysTable.scan()
        today_holiday = next((h for h in holidays if h.get('HolidayDate') == today), None)
        
        if not today_holiday:
            self.stdout.write(self.style.SUCCESS(f"No holiday scheduled for today ({today})."))
            return

        holiday_name = today_holiday.get('Name', 'Holiday')
        self.stdout.write(self.style.NOTICE(f"Today is {holiday_name}! Sending greetings..."))

        # 2. Fetch all active employees
        employees = EmployeesTable.scan()
        active_employees = [e for e in employees if e.get('OnboardingStatus') == 'Approved' and e.get('IsActive', True) != False]

        # 3. Send emails
        success_count = 0
        error_count = 0

        for emp in active_employees:
            recipient = emp.get('Email')
            if not recipient:
                continue

            emp_name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}"
            subject = f"Happy {holiday_name}! - Lurnexa HR Admin"
            body = f"Hi {emp_name},\n\nLurnexa wishes you a very happy and joyful {holiday_name}!\n\nEnjoy your day off with your family and friends.\n\nBest regards,\nLurnexa HR Admin"

            try:
                send_mail(
                    subject,
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    [recipient],
                    fail_silently=False
                )
                success_count += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to send email to {recipient}: {str(e)}"))
                error_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully sent {success_count} holiday greetings. Errors: {error_count}"))
