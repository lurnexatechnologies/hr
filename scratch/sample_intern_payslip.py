import os
import sys
import django
import datetime
from decimal import Decimal

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable
from payroll.views import process_payroll_logic

def generate_sample_intern_payslip():
    emp_id = "LT20260001"
    employee = EmployeesTable.get_item({'EmployeeID': emp_id})
    
    if not employee:
        print(f"Employee {emp_id} not found.")
        return

    print(f"--- Sample Payslip for {employee.get('FirstName')} {employee.get('LastName')} ({employee.get('EmploymentType')}) ---")
    
    # Mock Attendance (May 2026: 31 days, 3 days LOP)
    month, year = 5, 2026
    attendance_mock = {
        "total_days": 31,
        "lop_days": 3,
        "paid_days": 28
    }
    
    print(f"Annual Salary: Rs.{employee.get('SalaryPA', 0)}")
    print(f"Attendance: {attendance_mock['total_days']} total days, {attendance_mock['lop_days']} LOP days")
    
    # Run Logic
    try:
        results = process_payroll_logic(employee, attendance_mock, month, year)
        
        print("\n--- Results ---")
        print(f"Gross Salary: Rs.{results.get('GrossSalary', 0):.2f}")
        print(f"Basic Salary: Rs.{results.get('Basic', 0):.2f}")
        print(f"LOP Deduction: Rs.{results.get('LOPDeduction', 0):.2f}")
        print(f"PF Deduction: Rs.{results.get('PF', 0):.2f}")
        print(f"ESI Deduction: Rs.{results.get('ESI', 0):.2f}")
        print(f"PT Deduction: Rs.{results.get('PT', 0):.2f}")
        print(f"TDS Deduction: Rs.{results.get('TDS', 0):.2f}")
        print(f"Total Deductions: Rs.{results.get('TotalDeductions', 0):.2f}")
        print(f"Net Salary: Rs.{results.get('NetPay', 0):.2f}")
        
        # Validation
        if results.get('PF', 0) == 0 and results.get('ESI', 0) == 0 and results.get('PT', 0) == 0 and results.get('TDS', 0) == 0:
            print("\nSUCCESS: All statutory deductions are 0 for the intern.")
        else:
            print("\nFAILURE: Statutory deductions were found for the intern.")
            
        if results.get('LOPDeduction', 0) > 0:
            print("SUCCESS: LOP was correctly deducted.")
            
    except Exception as e:
        print(f"Error processing payroll: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    generate_sample_intern_payslip()
