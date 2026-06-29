import os
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from django.core.mail import send_mail
from django.conf import settings

def test_email():
    subject = "Lurnexa HR Admin - Test Email"
    message = "This is a test email from Lurnexa HR Admin to verify SMTP settings."
    recipient = "lurnexasolution@gmail.com" # Using the one I found in DB
    
    print(f"Attempting to send email from {settings.EMAIL_HOST_USER} to {recipient}...")
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
        import traceback
        traceback.print_exc()

test_email()
