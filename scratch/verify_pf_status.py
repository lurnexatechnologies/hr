import sys
import os
import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
import django
django.setup()

from core.dynamodb_service import PayslipsTable

def verify_mark_paid_logic():
    # Find a payslip to test with
    payslips = PayslipsTable.scan()
    if not payslips:
        print("No payslips found in DB. Skipping test.")
        return
    
    ps = payslips[0]
    emp_id = ps['EmployeeID']
    month_year = ps['MonthYear']
    
    print(f"Testing with Employee: {emp_id}, MonthYear: {month_year}")
    print(f"Initial Status: {ps.get('PF_Paid')}")
    
    # Toggle status
    new_status = not ps.get('PF_Paid', False)
    ps['PF_Paid'] = new_status
    PayslipsTable.put_item(ps)
    
    # Verify
    updated_ps = PayslipsTable.get_item({'EmployeeID': emp_id, 'MonthYear': month_year})
    print(f"Updated Status: {updated_ps.get('PF_Paid')}")
    assert updated_ps.get('PF_Paid') == new_status
    
    print("Toggle status logic verified successfully.")

if __name__ == "__main__":
    verify_mark_paid_logic()
