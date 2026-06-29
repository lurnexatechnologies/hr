import sys
import os
import datetime

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
import django
django.setup()

from core.dynamodb_service import EmployeesTable, PayslipsTable

def generate_sample_payroll():
    all_employees = EmployeesTable.scan()
    month_year = datetime.date.today().strftime("%b_%Y").lower()
    
    print(f"Generating sample payroll for {month_year}...")
    
    count = 0
    for emp in all_employees:
        emp_id = emp.get('EmployeeID')
        if not emp_id: continue
        
        # Check if already exists
        if PayslipsTable.get_item({'EmployeeID': emp_id, 'MonthYear': month_year}):
            print(f"  - Payslip already exists for {emp_id}")
            continue
            
        salary_pa_raw = emp.get('SalaryPA', 0)
        try:
            salary_pa = float(salary_pa_raw)
        except:
            salary_pa = 0
            
        if salary_pa <= 0:
            print(f"  - Skipping {emp_id} (No SalaryPA set)")
            continue
            
        from decimal import Decimal
        monthly_gross = Decimal(str(salary_pa / 12))
        tax = monthly_gross * Decimal('0.1')
        allowances = Decimal('500')
        net_pay = monthly_gross + allowances - tax
        
        payslip_item = {
            'EmployeeID': emp_id,
            'MonthYear': month_year,
            'Basic': round(monthly_gross, 2),
            'Tax': round(tax, 2),
            'Allowances': allowances,
            'NetPay': round(net_pay, 2),
            'GeneratedAt': datetime.datetime.now().isoformat()
        }
        
        PayslipsTable.put_item(payslip_item)
        print(f"  + Generated payslip for {emp_id} (Net: Rs.{round(net_pay, 2)})")
        count += 1
        
    print(f"\nDone! Successfully generated {count} sample payslips.")

if __name__ == "__main__":
    generate_sample_payroll()
