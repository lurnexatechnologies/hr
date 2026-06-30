from django.core.management.base import BaseCommand
import datetime
from core.dynamodb_service import HolidaysTable, EmployeesTable
from core.utils import send_notification, get_local_date

class Command(BaseCommand):
    help = 'Send notifications to all employees about upcoming holidays (runs daily)'

    def handle(self, *args, **options):
        # We check for holidays occurring tomorrow
        tomorrow_date = get_local_date() + datetime.timedelta(days=1)
        tomorrow_str = tomorrow_date.isoformat()
        
        self.stdout.write(f"Checking for holidays on {tomorrow_str}...")
        
        holidays = HolidaysTable.scan()
        tomorrow_holidays = [h for h in holidays if h.get('HolidayDate') == tomorrow_str]
        
        if not tomorrow_holidays:
            self.stdout.write("No holidays tomorrow. Skipping reminders.")
            return

        all_employees = EmployeesTable.scan()
        
        for holiday in tomorrow_holidays:
            h_name = holiday.get('Name', 'Holiday')
            h_type = holiday.get('Type', 'National')
            
            self.stdout.write(f"Found Holiday: {h_name}. Sending reminders to {len(all_employees)} employees...")
            
            for emp in all_employees:
                emp_id = emp.get('EmployeeID')
                if not emp_id:
                    continue
                    
                emp_first_name = emp.get('FirstName', 'Team Member')
                
                # Send both In-App and Email notifications
                send_notification(
                    employee_id=emp_id,
                    title="Upcoming Holiday! 🏖️",
                    message=f"Reminder: Tomorrow ({tomorrow_str}) is a {h_type} Holiday for '{h_name}'. Enjoy your day off!",
                    n_type='Holiday',
                    icon='fa-umbrella-beach',
                    color='primary',
                    email_subject=f"Upcoming Holiday Reminder: {h_name}",
                    email_body=f"Hi {emp_first_name},\n\nJust a friendly reminder that tomorrow, {tomorrow_str}, is a scheduled holiday for '{h_name}'.\n\nThe office will be closed. We wish you a wonderful and relaxing day off!\n\nBest regards,\nLurnexa HR Admin"
                )
        
        self.stdout.write(self.style.SUCCESS(f'Successfully sent holiday reminders for {len(tomorrow_holidays)} holidays.'))
