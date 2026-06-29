import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from django.core.mail import send_mail
from django.conf import settings

def test_email_hr():
    subject = "Lurnexa HR Admin - HR Test Email"
    message = "Testing if HR receives emails from the system."
    recipient = "lurnexahrms@gmail.com"
    
    print(f"Attempting to send email to {recipient}...")
    try:
        sent = send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False
        )
        print(f"Email sent successfully! Status: {sent}")
    except Exception as e:
        print(f"FAILED to send email: {e}")

test_email_hr()
