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

from core.dynamodb_service import EmployeesTable, PayslipsTable
from payroll.views import process_payroll_logic

def generate_db_intern_payslip():
    emp_id = "LT20260001"
    employee = EmployeesTable.get_item({'EmployeeID': emp_id})
    
    if not employee:
        print(f"Employee {emp_id} not found.")
        return

    # Period: April 2026
    month, year = 4, 2026
    month_year = "apr_2026"
    
    print(f"Generating DB Payslip for {employee.get('FirstName')} (Intern) for {month_year}...")
    
    attendance = {
        "total_days": 30,
        "lop_days": 1,
        "paid_days": 29
    }
    
    try:
        # 1. Calculate
        results = process_payroll_logic(employee, attendance, month, year)
        
        # 2. Enrich for DB
        results.update({
            'EmployeeID': emp_id,
            'MonthYear': month_year,
            'TotalDays': Decimal(str(attendance['total_days'])),
            'PaidDays': Decimal(str(attendance['paid_days'])),
            'LOPDays': Decimal(str(attendance['lop_days'])),
            'GeneratedAt': datetime.datetime.now().isoformat(),
            'PaymentStatus': 'SUCCESS',
            'KotakTransactionID': 'MOCK-INTERN-TRANSFER-001',
            'PaymentMethod': 'NEFT'
        })
        
        # 3. Save to DynamoDB
        PayslipsTable.put_item(results)
        
        print("\nSUCCESS: Payslip generated and saved to database.")
        print(f"Check the My Payslips or Payroll History for {emp_id} and {month_year}.")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    generate_db_intern_payslip()
