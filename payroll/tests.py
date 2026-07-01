from django.test import TestCase
from payroll.views import process_payroll_logic, get_attendance_summary
from decimal import Decimal
import datetime

class PayrollLogicTests(TestCase):
    def setUp(self):
        self.standard_employee = {
            'EmployeeID': 'EMP001',
            'SalaryPA': '1200000',  # 12 LPA (100k/month)
            'pf_enabled': True,
            'is_pf_applicable': True,
            'EmployeePFContribution': '12',
            'EmployerPFContribution': '12',
            'EPS_Eligible': True,
            'EDLI_Applicable': True,
            'EmploymentType': 'Full-Time'
        }
        
        self.intern_employee = {
            'EmployeeID': 'INT001',
            'SalaryPA': '300000',   # 3 LPA (25k/month)
            'EmploymentType': 'Intern'
        }
        
        self.standard_attendance = {
            'total_days': 30,
            'paid_days': 30,
            'lop_days': 0
        }

    def tearDown(self):
        from core.dynamodb_service import SettingsTable
        try:
            SettingsTable.delete_item({'SettingKey': 'Global_ESI_Amount'})
        except Exception:
            pass

    def test_standard_payroll_calculation(self):
        from core.dynamodb_service import SettingsTable
        SettingsTable.put_item({
            'SettingKey': 'Global_ESI_Amount',
            'Value': '1250.00'
        })
        result = process_payroll_logic(self.standard_employee, self.standard_attendance, 5, 2026)
        
        self.assertEqual(result['GrossSalary'], Decimal('100000.00'))
        self.assertEqual(result['LOPDeduction'], Decimal('0.00'))
        self.assertEqual(result['AdjustedGross'], Decimal('100000.00'))
        
        # PF 12% of Basic (Basic = 40% of CTC = 40,000)
        # PF = 12% of 40,000 = 4,800
        self.assertEqual(result['PF'], Decimal('4800.00'))
        
        # Professional Tax > 20k -> 200
        self.assertEqual(result['PT'], Decimal('200.00'))
        
        # ESI (Flat configured amount)
        self.assertEqual(result['ESI'], Decimal('1250.00'))
        
        self.assertTrue(result['NetPay'] > 0)

    def test_intern_payroll_bypass(self):
        result = process_payroll_logic(self.intern_employee, self.standard_attendance, 5, 2026)
        
        self.assertEqual(result['GrossSalary'], Decimal('25000.00'))
        
        # Interns should not have PF, ESI, PT, or TDS
        self.assertEqual(result['PF'], Decimal('0.00'))
        self.assertEqual(result['ESI'], Decimal('0.00'))
        self.assertEqual(result['PT'], Decimal('0.00'))
        self.assertEqual(result['TDS'], Decimal('0.00'))
        
        self.assertEqual(result['NetPay'], Decimal('25000.00'))

    def test_extreme_lop_handling(self):
        # Admin accidentally inputs 40 days LOP for a 30 day month
        heavy_lop_attendance = {
            'total_days': 30,
            'paid_days': 0,
            'lop_days': 40
        }
        result = process_payroll_logic(self.standard_employee, heavy_lop_attendance, 5, 2026)
        
        # Adjusted Gross could drop below 0 if not capped
        self.assertTrue(result['AdjustedGross'] >= 0, "Adjusted Gross should not be negative")
        
        # ESI should not be negative
        self.assertTrue(result['ESI'] >= 0, "ESI should not be negative")
        
        # NetPay should never be negative
        self.assertTrue(result['NetPay'] >= 0, "NetPay should not be negative")
