import sys
import os
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock Django settings and DynamoDB tables before importing
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
import django
django.setup()

from payroll.views import process_payroll_logic

def test_payroll_logic():
    # Mock data
    attendance = {
        "total_days": 30,
        "paid_days": 30,
        "lop_days": 0
    }
    
    # 1. Permanent Employee with PF/ESI
    permanent_emp = {
        'EmployeeID': 'EMP001',
        'SalaryPA': 600000,
        'EmploymentType': 'Permanent',
        'pf_enabled': True,
        'EPS_Eligible': True,
        'EDLI_Applicable': True,
        'EmployeePFContribution': 12,
        'EmployerPFContribution': 12
    }
    
    res_perm = process_payroll_logic(permanent_emp, attendance, 5, 2026)
    print(f"Permanent Employee PF: {res_perm['PF']}, ESI: {res_perm['ESI']}")
    assert res_perm['PF'] > 0, "Permanent employee should have PF deduction"
    assert res_perm['ESI'] > 0, "Permanent employee should have ESI deduction"

    # 2. Intern Employee (Should have 0 PF/ESI)
    intern_emp = {
        'EmployeeID': 'INT001',
        'SalaryPA': 240000, # 20k per month
        'EmploymentType': 'Intern',
        'pf_enabled': True, # Even if enabled, should be 0
        'EPS_Eligible': True,
        'EDLI_Applicable': True,
        'EmployeePFContribution': 12,
        'EmployerPFContribution': 12
    }
    
    res_intern = process_payroll_logic(intern_emp, attendance, 5, 2026)
    print(f"Intern Employee PF: {res_intern['PF']}, ESI: {res_intern['ESI']}")
    assert res_intern['PF'] == 0, "Intern employee should have 0 PF deduction"
    assert res_intern['ESI'] == 0, "Intern employee should have 0 ESI deduction"

    print("Test passed successfully!")

if __name__ == "__main__":
    try:
        test_payroll_logic()
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
