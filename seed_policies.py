import os
import django
import uuid

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import PoliciesTable, initialize_dynamodb_tables

def seed_policies():
    # Ensure tables exist
    initialize_dynamodb_tables()
    
    policies = [
        {
            'PolicyID': 'conduct',
            'Title': "Code of Conduct",
            'Description': "Our fundamental principles of professional integrity, ethics, and workplace behavior standards.",
            'Icon': "fa-gavel",
            'Color': "#2b6cb0",
            'Gradient': "linear-gradient(135deg, #ebf4ff 0%, #bee3f8 100%)",
            'Content': "<h6>1. Professional Integrity</h6><p>Employees are expected to maintain the highest standards of integrity and ethics.</p><h6>2. Workplace Behavior</h6><p>Lurnexa promotes a collaborative environment. Disrespectful behavior will not be tolerated.</p><h6>3. Confidentiality</h6><p>Protecting company secrets and client data is paramount.</p>"
        },
        {
            'PolicyID': 'leave',
            'Title': "Leave Policy",
            'Description': "Detailed breakdown of leave entitlements, holiday calendars, and attendance tracking protocols.",
            'Icon': "fa-calendar-check",
            'Color': "#2f855a",
            'Gradient': "linear-gradient(135deg, #f0fff4 0%, #c6f6d5 100%)",
            'Content': "<h6>1. Working Hours</h6><p>Standard working hours are 9:00 AM to 6:00 PM. Employees are expected to be available during these core hours.</p><h6>2. Leave Entitlements</h6><ul><li><b>Earned Leave (EL):</b> Accrued based on attendance (1 day for every 20 working days). EL can be carried forward to the next year.</li><li><b>Sick Leave (SL):</b> 1 day credited on the 1st of every month. Unused SL expires at the end of the year.</li><li><b>Casual Leave (CL):</b> 1 day credited on the 1st of every month. Unused CL expires at the end of the year.</li></ul><h6>3. Public Holidays</h6><p>The company observes 10 public holidays per year. A localized holiday calendar is distributed at the start of each calendar year.</p><h6>4. Approval Process</h6><p>All planned leaves must be submitted through the HRMS at least 1 week in advance for manager approval. Sick leaves must be logged as soon as practically possible.</p>"
        },
        {
            'PolicyID': 'wfh',
            'Title': "Work From Home Policy",
            'Description': "Guidelines and expectations for remote work, equipment usage, and communication.",
            'Icon': "fa-house-laptop",
            'Color': "#805ad5",
            'Gradient': "linear-gradient(135deg, #faf5ff 0%, #e9d8fd 100%)",
            'Content': "<h6>1. Eligibility</h6><p>Employees who have successfully completed their probationary period are eligible for 2 Work from Home (WFH) days per month, subject to manager approval.</p><h6>2. Core Hours</h6><p>Remote employees must remain online and accessible via official communication channels (Slack, Email) during the core business hours of 9:30 AM to 5:00 PM.</p><h6>3. Work Environment</h6><p>Employees must ensure they have a secure, quiet, and ergonomic workspace with a stable internet connection capable of supporting video conferencing.</p><h6>4. Equipment Security</h6><p>Company-provided laptops must never be left unattended in public spaces. Use of public Wi-Fi without the company VPN is strictly prohibited.</p>"
        },
        {
            'PolicyID': 'security',
            'Title': "Data & IT Security",
            'Description': "Guidelines for safeguarding company information, password hygiene, and responsible tool usage.",
            'Icon': "fa-user-shield",
            'Color': "#c05621",
            'Gradient': "linear-gradient(135deg, #fffaf0 0%, #feebc8 100%)",
            'Content': "<h6>1. Password Hygiene</h6><p>Use strong, unique passwords.</p><h6>2. Tool Usage</h6><p>Only company-approved software may be installed.</p>"
        }
    ]
    
    for p in policies:
        PoliciesTable.put_item(p)
        print(f"Seeded policy: {p['Title']}")

if __name__ == "__main__":
    seed_policies()
