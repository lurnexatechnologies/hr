import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from django.template.loader import render_to_string
from workflows.views import html_to_pdf_bytes
from core.utils import get_lurnexa_logo_base64

# Mock data
employee = {
    'FirstName': 'John',
    'LastName': 'Doe',
    'EmployeeID': 'EMP1001',
    'Designation': 'Senior Software Engineer',
    'Department': 'Engineering',
    'JoinedDate': '2023-01-15',
    'PFNumber': 'MH/BAN/1234567/000/7654321',
    'UANNumber': '100987654321',
}

resignation = {
    'LastWorkingDay': '2026-05-20',
}

exp_context = {
    'employee': employee,
    'resignation': resignation,
    'today': 'May 20, 2026',
    'joined_date_fmt': 'January 15, 2023',
    'lwd_fmt': 'May 20, 2026',
    'is_pdf': True,
    'logo_base64': get_lurnexa_logo_base64(),
}

# 1. Generate Experience Letter PDF
exp_html = render_to_string('workflows/experience_letter.html', exp_context)
exp_pdf = html_to_pdf_bytes(exp_html)
if exp_pdf:
    with open('scratch/test_experience_letter.pdf', 'wb') as f:
        f.write(exp_pdf)
    print("Experience Letter PDF generated successfully!")
else:
    print("Failed to generate Experience Letter PDF.")

# 2. Generate PF Letter PDF
pf_context = {
    'employee': employee,
    'resignation': resignation,
    'today': 'May 20, 2026',
    'lwd_fmt': 'May 20, 2026',
    'is_pdf': True,
    'logo_base64': get_lurnexa_logo_base64(),
}
pf_html = render_to_string('workflows/pf_letter.html', pf_context)
pf_pdf = html_to_pdf_bytes(pf_html)
if pf_pdf:
    with open('scratch/test_pf_letter.pdf', 'wb') as f:
        f.write(pf_pdf)
    print("PF Letter PDF generated successfully!")
else:
    print("Failed to generate PF Letter PDF.")
