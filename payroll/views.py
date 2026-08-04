from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import HttpResponse
from django.views import View
from django.views.generic import TemplateView
from auth_custom.mixins import LoginRequiredMixin, HRRequiredMixin, RoleRequiredMixin, SuperAdminRequiredMixin, FeatureRequiredMixin
from core.dynamodb_service import PayslipsTable, EmployeesTable, AttendanceTable, LeaveRequestsTable, HolidaysTable, PayrollApprovalsTable, UsersTable, ExpensesTable
from core.bank_service import UniversalBankService
from core.utils import safe_float, safe_decimal, get_local_date, get_local_now, send_notification, resolve_workflow_step, format_day_with_ordinal
from boto3.dynamodb.conditions import Key
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import datetime
import calendar
from decimal import Decimal
from django.urls import reverse_lazy
import os
from django.conf import settings

def check_and_release_scheduled_payslips():
    """
    Checks PayslipsTable for any payslips with ReleaseStatus == 'Scheduled'
    and releases them if current date & time >= ScheduledReleaseDate 08:00:00.
    Dispatches in-app notifications and email notifications at 8:00 AM on that day.
    """
    now = get_local_now()
    today_str = now.strftime('%Y-%m-%d')

    try:
        scheduled_payslips = PayslipsTable.scan(
            FilterExpression="ReleaseStatus = :rs",
            ExpressionAttributeValues={":rs": "Scheduled"}
        )
        for ps in scheduled_payslips:
            rel_date = ps.get('ScheduledReleaseDate', today_str)
            rel_time = ps.get('ScheduledReleaseTime', '08:00:00')
            
            try:
                target_dt = datetime.datetime.strptime(f"{rel_date} {rel_time}", "%Y-%m-%d %H:%M:%S")
                if now.tzinfo:
                    target_dt = target_dt.replace(tzinfo=now.tzinfo)
                if now >= target_dt:
                    ps['ReleaseStatus'] = 'Released'
                    ps['ReleasedAt'] = now.isoformat()
                    PayslipsTable.put_item(ps)

                    emp_id = ps.get('EmployeeID')
                    month_year = ps.get('MonthYear', '')
                    emp = EmployeesTable.get_item({'EmployeeID': emp_id})
                    if emp:
                        month_name = month_year.split('_')[0].upper() if '_' in month_year else ''
                        year_val = month_year.split('_')[1] if '_' in month_year else ''
                        email_subject = f"Payslip for {month_name} {year_val} Released"
                        email_body = f"Hi {emp.get('FirstName', 'Employee')},\n\nYour payslip for {month_name} {year_val} has been released and is now available in your Kyro People ESS portal.\n\nNet Pay: INR {ps.get('NetPay')}\n\nPlease log in to view and download your payslip.\n\nBest regards,\nKyro People HR Team"
                        send_notification(
                            employee_id=emp_id,
                            title=f"Payslip Released - {month_name} {year_val}",
                            message=f"Your payslip for {month_name} {year_val} is now available in your portal.",
                            n_type='Payroll',
                            icon='fa-file-invoice-dollar',
                            color='success',
                            email_subject=email_subject,
                            email_body=email_body
                        )
            except Exception as ex:
                print(f"Error releasing scheduled payslip for {ps.get('EmployeeID')}: {ex}")
    except Exception as e:
        print(f"Error in check_and_release_scheduled_payslips: {e}")


def get_attendance_summary(employee_id, month, year):
    """
    Calculates total days, paid days, and lop days for a given employee and month.
    The payroll cycle is from the 27th of the previous month to the 26th of the current month.
    """
    # Determine the start date (27th of previous month)
    if month == 1:
        prev_month = 12
        prev_year = year - 1
    else:
        prev_month = month - 1
        prev_year = year
    
    start_date = datetime.date(prev_year, prev_month, 27)
    end_date = datetime.date(year, month, 26)

    # Total days in this payroll period
    total_days = (end_date - start_date).days + 1
    
    # Fetch attendance data
    attendance_records = AttendanceTable.scan(
        FilterExpression="EmployeeID = :eid",
        ExpressionAttributeValues={":eid": employee_id}
    )
    
    start_date_str = start_date.isoformat()
    end_date_str = end_date.isoformat()
    
    # Fetch holidays
    holidays = HolidaysTable.scan()
    holiday_dates = {h.get('HolidayDate') for h in holidays if h.get('HolidayDate') and start_date_str <= h.get('HolidayDate') <= end_date_str}

    # Filter present/wfh dates within the period
    present_dates = {
        r['RecordDate'] for r in attendance_records 
        if r.get('Status') in ['Present', 'WFH'] and start_date_str <= r.get('RecordDate') <= end_date_str
    }
    
    # Fetch leave data
    leave_records = LeaveRequestsTable.scan(
        FilterExpression="EmployeeID = :eid AND #s = :status",
        ExpressionAttributeNames={"#s": "Status"},
        ExpressionAttributeValues={":eid": employee_id, ":status": "Approved"}
    )

    # Approved leaves are paid (excluding Unpaid Leave and handling Half-Day)
    approved_leave_map = {} # Date -> PaidValue (1.0 or 0.5)
    for l in leave_records:
        l_type = l.get('Type', '')
        if 'Unpaid Leave' in l_type:
            continue
            
        try:
            l_start = datetime.datetime.strptime(l['LeaveDate'], '%Y-%m-%d').date()
            l_end = datetime.datetime.strptime(l['EndDate'], '%Y-%m-%d').date()
            is_half = l.get('IsHalfDay', False)
            
            curr = l_start
            while curr <= l_end:
                if start_date <= curr <= end_date:
                    date_str = curr.isoformat()
                    # If it's a half day, it only counts as 0.5
                    val = 0.5 if is_half else 1.0
                    # Store the highest value if there's any overlap (though overlap is usually blocked)
                    approved_leave_map[date_str] = max(approved_leave_map.get(date_str, 0), val)
                curr += datetime.timedelta(days=1)
        except: continue

    lop_days = 0.0
    paid_days = 0.0 # Use float for half-days
    
    # Iterate through each day in the payroll period
    for i in range(total_days):
        date_obj = start_date + datetime.timedelta(days=i)
        date_str = date_obj.isoformat()
        
        # 1. Holidays are paid
        if date_str in holiday_dates:
            paid_days += 1
            continue
            
        # 2. Weekends are paid (Assume Saturday/Sunday are non-working but paid)
        if date_obj.weekday() >= 5:
            paid_days += 1
            continue
            
        # 3. Present or WFH days are paid
        if date_str in present_dates:
            paid_days += 1
        # 4. Approved leaves are paid (Weighted)
        elif date_str in approved_leave_map:
            weight = approved_leave_map[date_str]
            paid_days += weight
            # If it's a half-day leave and they aren't present, the other half is LOP
            if weight < 1.0 and date_obj <= get_local_date():
                lop_days += (1.0 - weight)
        # 5. Otherwise it's LOP (Only if the day has already passed)
        else:
            if date_obj <= get_local_date():
                lop_days += 1
            # Future days are not counted as LOP yet in the preview/calculation
            
    return {
        "total_days": total_days,
        "paid_days": paid_days,
        "lop_days": lop_days
    }

def calculate_industry_allowances_and_deductions(employee, attendance, month, year):
    """
    Multi-Industry Payroll Engine Strategy Evaluator with Super Admin Configurable Rates.
    Supports Piece-rate, Sales commissions, Till adjustments, and Shift differentials.
    """
    custom_fields = employee.get('CustomFields') or {}

    piece_rate_earnings = 0.0
    sales_commission = 0.0
    till_shortage_deduction = 0.0
    shift_differential_allowance = 0.0

    # Fetch Super Admin Payroll Config
    org_id = employee.get('OrgID')
    payroll_cfg = {}
    if org_id:
        from core.dynamodb_service import OrganizationsTable
        org = OrganizationsTable.get_item({'OrgID': org_id})
        if org:
            payroll_cfg = org.get('PayrollConfig', {}) or {}

    rate_per_unit_cfg = safe_float(payroll_cfg.get('piece_rate_unit_amount', 0))
    commission_per_unit_cfg = safe_float(payroll_cfg.get('sales_commission_per_unit', 0))
    target_bonus_cfg = safe_float(payroll_cfg.get('sales_target_bonus_flat', 0))
    till_limit_cfg = safe_float(payroll_cfg.get('till_shortage_allowance_limit', 0))
    night_allowance_cfg = safe_float(payroll_cfg.get('night_shift_allowance_per_day', 0))

    # 1. Piece-Rate Payroll (Tiles factory / Poultry processing)
    rate_per_unit = safe_float(custom_fields.get('rate_per_unit', rate_per_unit_cfg))
    if rate_per_unit > 0:
        units_produced = safe_float(custom_fields.get('monthly_units_produced', 0))
        piece_rate_earnings = units_produced * rate_per_unit

    # 2. Sales Commission & Target Bonus (Car Showrooms / Auto Retail)
    sales_target = safe_float(custom_fields.get('monthly_sales_target_units', 0))
    if sales_target > 0:
        actual_units = safe_float(custom_fields.get('actual_units_sold', sales_target))
        if actual_units >= sales_target:
            sales_commission = (actual_units * commission_per_unit_cfg) + (target_bonus_cfg if actual_units > sales_target else 0)

    # 3. Supermarket Cash Till Shortage Deduction (DMart Cashier)
    till_limit = safe_float(custom_fields.get('till_variance_allowance', till_limit_cfg))
    recorded_shortage = safe_float(custom_fields.get('recorded_till_shortage', 0))
    if recorded_shortage > till_limit:
        till_shortage_deduction = recorded_shortage - till_limit

    # 4. Shift Differential & On-Call Allowance (Hospitals / 24-7 Plants)
    if employee.get('Shift') in ['Night Shift', 'Night Emergency / ICU Shift']:
        night_days = attendance.get('paid_days', 0)
        shift_differential_allowance = night_days * night_allowance_cfg

    return {
        'piece_rate_earnings': piece_rate_earnings,
        'sales_commission': sales_commission,
        'till_shortage_deduction': till_shortage_deduction,
        'shift_differential_allowance': shift_differential_allowance
    }

def process_payroll_logic(employee, attendance, month, year, increment=0, bonus=0):
    if not attendance or not isinstance(attendance, dict):
        attendance = {"total_days": 30, "paid_days": 30, "lop_days": 0}

    # Evaluate Multi-Industry Compensation Strategies
    ind_comp = calculate_industry_allowances_and_deductions(employee, attendance, month, year)

    # =========================
    # 1. MONTHLY CTC
    # =========================
    salary_pa = safe_float(employee.get('SalaryPA'))
    
    current_annual_salary = salary_pa + increment
    monthly_ctc = current_annual_salary / 12

    # Fetch Organization Tax, PF & Salary Component Settings
    org_id = employee.get('OrgID')
    org_rec = None
    if org_id:
        try:
            from core.dynamodb_service import OrganizationsTable
            org_rec = OrganizationsTable.get_item({'OrgID': org_id})
        except Exception:
            pass

    # Extract dynamic settings with standard fallback defaults
    pf_enabled = org_rec.get('PFEnabled', True) if org_rec else True
    tds_enabled = org_rec.get('TDSEnabled', True) if org_rec else True
    emp_pf_pct = float(org_rec.get('EmployeePFPercent', 12.0) if org_rec else 12.0) / 100.0
    mgr_pf_pct = float(org_rec.get('EmployerPFPercent', 12.0) if org_rec else 12.0) / 100.0
    basic_pct = float(org_rec.get('BasicPercent', 40.0) if org_rec else 40.0) / 100.0
    hra_pct = float(org_rec.get('HRAPercent', 40.0) if org_rec else 40.0) / 100.0
    std_deduction = float(org_rec.get('TaxStandardDeduction', 75000.0) if org_rec else 75000.0)

    # =========================
    # 2. SALARY STRUCTURE (DYNAMIC)
    # =========================
    basic = basic_pct * monthly_ctc
    hra = hra_pct * monthly_ctc
    special_allowance = max(0, monthly_ctc - (basic + hra))

    gross_salary = (
        basic + hra + special_allowance + 
        ind_comp['piece_rate_earnings'] + 
        ind_comp['sales_commission'] + 
        ind_comp['shift_differential_allowance']
    )

    # =========================
    # 3. LOP (LEAVE DEDUCTION)
    # =========================
    total_days = attendance["total_days"]
    lop_days = attendance["lop_days"]

    per_day_salary = gross_salary / total_days if total_days > 0 else 0
    lop_deduction = per_day_salary * lop_days
    
    # Cap LOP Deduction so it never exceeds Gross Salary
    if lop_deduction > gross_salary:
        lop_deduction = gross_salary

    adjusted_gross = max(0, gross_salary - lop_deduction)

    # =========================
    # 4. PF CALCULATION (DYNAMIC ORG SETTINGS)
    # =========================
    pf_employee = 0
    pf_employer = 0
    eps_employer = 0
    edli_employer = 0
    
    # Check for Intern status (No PF or ESI for interns)
    is_intern = employee.get('EmploymentType') == 'Intern'
    
    # Check for Manual PF Transaction first (Manual "Cutting")
    from core.dynamodb_service import PFTransactionsTable
    month_year = datetime.date(year, month, 1).strftime("%b_%Y").lower()
    manual_pf = None
    if not is_intern and pf_enabled:
        manual_pf = PFTransactionsTable.get_item({'EmployeeID': employee.get('EmployeeID'), 'MonthYear': month_year})
    
    if not is_intern and pf_enabled and manual_pf:
        pf_employee = float(manual_pf.get('Amount', 0))
        if employee.get('EPS_Eligible', True):
            eps_wage_base = min(basic, 15000)
            eps_employer = 0.0833 * eps_wage_base
            pf_employer = pf_employee - eps_employer
        else:
            pf_employer = pf_employee
            
    elif not is_intern and pf_enabled and employee.get('is_pf_applicable', True):
        # Automated calculation using org EmployeePFPercent & EmployerPFPercent
        pf_employee = emp_pf_pct * basic
        
        if employee.get('EPS_Eligible', True):
            eps_wage_base = min(basic, 15000)
            eps_employer = 0.0833 * eps_wage_base
            pf_employer = (mgr_pf_pct * basic) - eps_employer
        else:
            pf_employer = mgr_pf_pct * basic
            
        if employee.get('EDLI_Applicable', True):
            edli_wage_base = min(basic, 15000)
            edli_employer = 0.005 * edli_wage_base

    # =========================
    # 5. ESI CALCULATION
    # =========================
    esi_employee = 0
    if not is_intern:
        from core.dynamodb_service import SettingsTable
        esi_setting = SettingsTable.get_item({'SettingKey': 'Global_ESI_Amount'})
        if esi_setting and esi_setting.get('Value'):
            esi_employee = float(esi_setting['Value'])

    # =========================
    # 6. PROFESSIONAL TAX
    # =========================
    pt = 0
    if not is_intern:
        if adjusted_gross > 20000:
            pt = 200
        elif adjusted_gross > 15000:
            pt = 150

    # =========================
    # 7. TDS CALCULATION (DYNAMIC ORG SETTINGS)
    # =========================
    tds = 0
    if not is_intern and tds_enabled:
        annual_income = current_annual_salary
        taxable_income = max(0, annual_income - std_deduction)
        
        if taxable_income > 700000:  # Rebate up to 7L taxable income
            tax = 0
            # 3L - 7L: 5%
            if taxable_income > 300000:
                tax += min(taxable_income - 300000, 400000) * 0.05
            # 7L - 10L: 10%
            if taxable_income > 700000:
                tax += min(taxable_income - 700000, 300000) * 0.10
            # 10L - 12L: 15%
            if taxable_income > 1000000:
                tax += min(taxable_income - 1000000, 200000) * 0.15
            # 12L - 15L: 20%
            if taxable_income > 1200000:
                tax += min(taxable_income - 1200000, 300000) * 0.20
            # Above 15L: 30%
            if taxable_income > 1500000:
                tax += (taxable_income - 1500000) * 0.30
                
            # Health & Education Cess (4%)
            total_tax = tax * 1.04
            tds = total_tax / 12

    # =========================
    # 8. TOTAL DEDUCTIONS
    # =========================
    till_shortage = ind_comp['till_shortage_deduction']
    total_deductions = pf_employee + esi_employee + pt + tds + till_shortage

    # =========================
    # 9. NET SALARY
    # =========================
    net_salary = (adjusted_gross - total_deductions) + bonus
    net_salary = max(0, net_salary)

    return {
        "BaseSalaryPA": Decimal(str(round(salary_pa, 2))),
        "IncrementAdded": Decimal(str(round(increment, 2))),
        "NewSalaryPA": Decimal(str(round(current_annual_salary, 2))),
        "Basic": Decimal(str(round(basic, 2))),
        "HRA": Decimal(str(round(hra, 2))),
        "SpecialAllowance": Decimal(str(round(special_allowance, 2))),
        "PieceRateEarnings": Decimal(str(round(ind_comp['piece_rate_earnings'], 2))),
        "SalesCommission": Decimal(str(round(ind_comp['sales_commission'], 2))),
        "ShiftDifferential": Decimal(str(round(ind_comp['shift_differential_allowance'], 2))),
        "TillShortageDeduction": Decimal(str(round(till_shortage, 2))),
        "GrossSalary": Decimal(str(round(gross_salary, 2))),
        "LOPDeduction": Decimal(str(round(lop_deduction, 2))),
        "AdjustedGross": Decimal(str(round(adjusted_gross, 2))),
        "PF": Decimal(str(round(pf_employee, 2))),
        "EmployerPF": Decimal(str(round(pf_employer, 2))),
        "EmployerEPS": Decimal(str(round(eps_employer, 2))),
        "EmployerEDLI": Decimal(str(round(edli_employer, 2))),
        "ESI": Decimal(str(round(esi_employee, 2))),
        "PT": Decimal(str(round(pt, 2))),
        "TDS": Decimal(str(round(tds, 2))),
        "Bonus": Decimal(str(round(bonus, 2))),
        "TotalDeductions": Decimal(str(round(total_deductions, 2))),
        "NetPay": Decimal(str(round(net_salary, 2))),
    }

class PayrollRequiredMixin(LoginRequiredMixin):
    """Verify that the user has authorized access to payroll management
    AND has completed secondary payroll authentication."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        user_role = getattr(request.user, 'role', '')
        user_permissions = getattr(request.user, 'permissions', [])
        
        if user_role not in ['Super admin', 'HR ADMIN', 'HR', 'Platform Admin'] and 'payroll_access' not in user_permissions:
            return redirect('forbidden_403')

        # Enforce secondary payroll authentication
        if not request.session.get('payroll_authenticated'):
            messages.info(request, "Please authenticate to access Payroll Management.")
            return redirect('payroll_login')
            
        return super().dispatch(request, *args, **kwargs)

class PayrollLoginView(FeatureRequiredMixin, LoginRequiredMixin, View):
    """Secure secondary authentication gate for payroll management.
    Re-verifies the user's password before granting access."""
    required_feature = 'payroll'
    MAX_ATTEMPTS = 5
    LOCKOUT_SECONDS = 300  # 5 minutes

    def get(self, request):
        # If already authenticated for payroll, go straight to manage
        if request.session.get('payroll_authenticated'):
            return redirect('manage_payroll')

        # Check role-based access first
        user_role = getattr(request.user, 'role', '')
        user_permissions = getattr(request.user, 'permissions', [])
        if user_role not in ['Super admin', 'HR ADMIN', 'HR', 'Platform Admin'] and 'payroll_access' not in user_permissions:
            return redirect('forbidden_403')

        # Check lockout
        lockout_until = request.session.get('payroll_lockout_until')
        is_locked = False
        remaining_seconds = 0
        if lockout_until:
            now_ts = get_local_now().timestamp()
            if now_ts < lockout_until:
                is_locked = True
                remaining_seconds = int(lockout_until - now_ts)
            else:
                # Lockout expired — clear
                request.session.pop('payroll_lockout_until', None)
                request.session.pop('payroll_failed_attempts', None)

        context = {
            'is_locked': is_locked,
            'remaining_seconds': remaining_seconds,
        }
        return render(request, 'payroll/login.html', context)

    def post(self, request):
        import bcrypt
        from django.contrib.auth.hashers import check_password

        # Check role-based access first
        user_role = getattr(request.user, 'role', '')
        user_permissions = getattr(request.user, 'permissions', [])
        if user_role not in ['Super admin', 'HR ADMIN', 'HR', 'Platform Admin'] and 'payroll_access' not in user_permissions:
            return redirect('forbidden_403')

        # Check lockout
        lockout_until = request.session.get('payroll_lockout_until')
        if lockout_until:
            now_ts = get_local_now().timestamp()
            if now_ts < lockout_until:
                remaining = int(lockout_until - now_ts)
                messages.error(request, f"Account locked. Try again in {remaining // 60} min {remaining % 60} sec.")
                return redirect('payroll_login')
            else:
                request.session.pop('payroll_lockout_until', None)
                request.session.pop('payroll_failed_attempts', None)

        username = (request.POST.get('payroll_username') or '').strip()
        password = (request.POST.get('payroll_password') or '').strip()

        if not username or not password:
            messages.error(request, "Please enter both Vault Username and Vault Password.")
            return redirect('payroll_login')

        # Look up the current user's stored password hash & vault username from DynamoDB
        from core.dynamodb_service import UsersTable
        user_data = UsersTable.get_item({'UserID': request.user.user_id})
        if not user_data:
            messages.error(request, "Authentication failed. User record not found.")
            return redirect('payroll_login')

        expected_username = user_data.get('PayrollVaultUsername') or user_data.get('Username') or user_data.get('Email') or request.user.email or ''
        hashed = user_data.get('PayrollVaultPasswordHash') or user_data.get('PasswordHash') or user_data.get('Password') or ''
        
        is_user_valid = (username.lower() == expected_username.strip().lower())
        is_pw_valid = False

        if is_user_valid:
            # 1. Try Django's check_password
            try:
                if check_password(password, hashed):
                    is_pw_valid = True
            except Exception:
                pass

            # 2. Fallback to raw bcrypt
            if not is_pw_valid:
                try:
                    if bcrypt.checkpw(password.encode('utf-8')[:72], hashed.encode('utf-8')):
                        is_pw_valid = True
                except Exception:
                    pass

        if is_user_valid and is_pw_valid:
            # Clear failed attempts and grant access
            request.session.pop('payroll_failed_attempts', None)
            request.session.pop('payroll_lockout_until', None)
            request.session['payroll_authenticated'] = True
            messages.success(request, "Payroll access granted. Welcome to Payroll Management.")
            return redirect('manage_payroll')
        else:
            # Increment failed attempts
            attempts = request.session.get('payroll_failed_attempts', 0) + 1
            request.session['payroll_failed_attempts'] = attempts

            remaining = self.MAX_ATTEMPTS - attempts
            if attempts >= self.MAX_ATTEMPTS:
                lockout_ts = get_local_now().timestamp() + self.LOCKOUT_SECONDS
                request.session['payroll_lockout_until'] = lockout_ts
                messages.error(request, f"Too many failed attempts. Account locked for {self.LOCKOUT_SECONDS // 60} minutes.")
            else:
                messages.error(request, f"Incorrect Vault credentials. {remaining} attempt(s) remaining.")

            return redirect('payroll_login')

class ChangePayrollVaultCredentialsView(FeatureRequiredMixin, PayrollRequiredMixin, View):
    required_feature = 'payroll'

    def post(self, request):
        import bcrypt
        from django.contrib.auth.hashers import check_password, make_password
        from core.dynamodb_service import UsersTable

        old_username = (request.POST.get('old_vault_username') or '').strip()
        old_password = (request.POST.get('old_vault_password') or '').strip()
        new_username = (request.POST.get('new_vault_username') or '').strip()
        new_password = (request.POST.get('new_vault_password') or '').strip()
        confirm_password = (request.POST.get('confirm_vault_password') or '').strip()

        if not old_username or not old_password or not new_username or not new_password:
            messages.error(request, "All fields are required to update Vault credentials.")
            return redirect('manage_payroll')

        if new_password != confirm_password:
            messages.error(request, "New Vault password and confirm password do not match.")
            return redirect('manage_payroll')

        user_data = UsersTable.get_item({'UserID': request.user.user_id})
        if not user_data:
            messages.error(request, "User record not found.")
            return redirect('manage_payroll')

        expected_username = user_data.get('PayrollVaultUsername') or user_data.get('Username') or user_data.get('Email') or request.user.email or ''
        expected_hash = user_data.get('PayrollVaultPasswordHash') or user_data.get('PasswordHash') or user_data.get('Password') or ''

        # Verify old username
        if old_username.lower() != expected_username.strip().lower():
            messages.error(request, "Incorrect old Vault Username.")
            return redirect('manage_payroll')

        # Verify old password
        is_pw_valid = False
        try:
            if check_password(old_password, expected_hash):
                is_pw_valid = True
        except Exception:
            pass

        if not is_pw_valid:
            try:
                if bcrypt.checkpw(old_password.encode('utf-8')[:72], expected_hash.encode('utf-8')):
                    is_pw_valid = True
            except Exception:
                pass

        if not is_pw_valid:
            messages.error(request, "Incorrect old Vault Password.")
            return redirect('manage_payroll')

        # Hash new vault password and update user record
        hashed_new_pw = make_password(new_password)
        UsersTable.update_item(
            Key={'UserID': request.user.user_id},
            UpdateExpression="SET PayrollVaultUsername = :u, PayrollVaultPasswordHash = :p",
            ExpressionAttributeValues={
                ':u': new_username,
                ':p': hashed_new_pw,
            }
        )

        messages.success(request, "Payroll Vault credentials updated successfully!")
        return redirect('manage_payroll')

class PayrollLogoutView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'payroll'
    def get(self, request):
        # Clear payroll session authentication
        request.session.pop('payroll_authenticated', None)
        request.session.pop('payroll_failed_attempts', None)
        request.session.pop('payroll_lockout_until', None)
        messages.success(request, "Exited Payroll Management.")
        return redirect('payroll_login')

class PayslipsView(FeatureRequiredMixin, LoginRequiredMixin, TemplateView):
    required_feature = 'payslips'
    template_name = 'payroll/payslips.html'

    def get_context_data(self, **kwargs):
        check_and_release_scheduled_payslips()
        context = super().get_context_data(**kwargs)
        user_id = self.request.user.employee_id
        
        # Static month list
        context['months'] = [
            ('jan', 'January'), ('feb', 'February'), ('mar', 'March'), ('apr', 'April'),
            ('may', 'May'), ('jun', 'June'), ('jul', 'July'), ('aug', 'August'),
            ('sep', 'September'), ('oct', 'October'), ('nov', 'November'), ('dec', 'December')
        ]
        
        # Dynamic year list (2024 to current year)
        current_year = get_local_date().year
        context['years'] = list(range(2024, current_year + 1))
        
        # Check for selected period
        selected_month = self.request.GET.get('month')
        selected_year = self.request.GET.get('year')
        
        if selected_month and selected_year:
            month_year = f"{selected_month}_{selected_year}"
            record = PayslipsTable.get_item({'EmployeeID': user_id, 'MonthYear': month_year})
            context['selected_month'] = selected_month
            context['selected_year'] = selected_year
            
            if record:
                rel_status = record.get('ReleaseStatus', 'Released')
                rel_date = record.get('ScheduledReleaseDate')
                now = get_local_now()
                
                if rel_status == 'Scheduled' and rel_date:
                    try:
                        target_dt = datetime.datetime.strptime(f"{rel_date} 08:00:00", "%Y-%m-%d %H:%M:%S")
                        if now.tzinfo:
                            target_dt = target_dt.replace(tzinfo=now.tzinfo)
                        if now < target_dt:
                            context['is_scheduled_pending'] = True
                            context['scheduled_release_date'] = rel_date
                    except Exception:
                        pass
                
                if not context.get('is_scheduled_pending'):
                    context['selected_record'] = record
            
        return context

class ManagePayrollView(FeatureRequiredMixin, PayrollRequiredMixin, View):
    required_feature = 'payroll'
    def get(self, request):
        from core.utils import apply_pending_hikes
        apply_pending_hikes()
        all_employees = EmployeesTable.scan()
        all_users = UsersTable.scan()
        all_payslips = PayslipsTable.scan()
        today = get_local_date()
        
        # Filter out Super admin from payroll processing
        active_employees_list = []
        for emp in all_employees:
            user = next((u for u in all_users if u.get('UserID') == emp.get('UserID')), None)
            if user and user.get('Role') == 'Super admin':
                continue
            active_employees_list.append(emp)
        all_employees = active_employees_list
        
        # Create a mapping for employee names (for History Tab)
        emp_map = {e['EmployeeID']: f"{e.get('FirstName', '')} {e.get('LastName', '')}" for e in all_employees}
        
        from core.dynamodb_service import EmployeeLettersTable
        all_letters = EmployeeLettersTable.scan()
        current_month_str = f"{today.year}-{today.month:02d}"
        
        payroll_data = []
        for emp in all_employees:
            emp_id = emp.get('EmployeeID')
            emp_payslips = [p for p in all_payslips if p.get('EmployeeID') == emp_id]
            latest = sorted(emp_payslips, key=lambda x: x.get('MonthYear', ''), reverse=True)
            
            # Generate a "Preview" for the current month
            attendance = get_attendance_summary(emp_id, today.month, today.year)
            preview = process_payroll_logic(emp, attendance, today.month, today.year)
            
            # Check for Bonus Letter this month
            auto_bonus = 0
            for l in all_letters:
                if l.get('EmployeeID') == emp_id and l.get('LetterType') == 'Bonus Letter' and l.get('GeneratedDate', '').startswith(current_month_str):
                    auto_bonus += float(l.get('BonusAmount', 0))
            
            # If there's an auto_bonus, recalculate preview with it
            if auto_bonus > 0:
                preview = process_payroll_logic(emp, attendance, today.month, today.year, bonus=auto_bonus)
                
            payroll_data.append({
                'employee': emp,
                'payslips': emp_payslips,
                'latest': latest[0] if latest else None,
                'preview': preview,
                'attendance': attendance,
                'auto_bonus': auto_bonus
            })
            
        # Global History Data
        global_history = []
        for ps in all_payslips:
            app_by = ps.get('ApprovedBy')
            if app_by:
                name = emp_map.get(app_by, '').strip()
                ps_approved_by = name if name else app_by
            else:
                ps_approved_by = 'System'
                
            global_history.append({
                'EmployeeID': ps.get('EmployeeID'),
                'EmployeeName': emp_map.get(ps.get('EmployeeID'), 'Unknown'),
                'MonthYear': ps.get('MonthYear'),
                'NetPay': ps.get('NetPay'),
                'GeneratedAt': ps.get('GeneratedAt', ''),
                'ApprovedBy': ps_approved_by
            })
        global_history = sorted(global_history, key=lambda x: x.get('GeneratedAt', ''), reverse=True)

        # Paginate Run List
        paginator_run = Paginator(payroll_data, 10)
        page_run = request.GET.get('page_run')
        payroll_data_page = paginator_run.get_page(page_run)
        
        # Paginate History List
        paginator_hist = Paginator(global_history, 15)
        page_hist = request.GET.get('page_hist')
        global_history_page = paginator_hist.get_page(page_hist)
        
        from core.dynamodb_service import SettingsTable, OrganizationsTable
        esi_setting = SettingsTable.get_item({'SettingKey': 'Global_ESI_Amount'})
        global_esi = esi_setting.get('Value') if esi_setting else None

        user_org_id = request.session.get('org_id')
        user_org_rec = None
        if user_org_id:
            try:
                user_org_rec = OrganizationsTable.get_item({'OrgID': user_org_id})
            except Exception:
                pass

        basic_pct_val = float(user_org_rec.get('BasicPercent', 40.0) if user_org_rec else 40.0) / 100.0
        hra_pct_val = float(user_org_rec.get('HRAPercent', 40.0) if user_org_rec else 40.0) / 100.0

        gen_date_setting = SettingsTable.get_item({'SettingKey': 'Payroll_Generation_Date'})
        gen_date_str = gen_date_setting.get('Value') if gen_date_setting else None
        formatted_gen_date = None
        if gen_date_str:
            formatted_gen_date = format_day_with_ordinal(gen_date_str)

        context = {
            'payroll_data': payroll_data_page,
            'total_run': len(payroll_data),
            'global_history': global_history_page,
            'total_hist': len(global_history),
            'global_esi': global_esi,
            'basic_pct': basic_pct_val,
            'hra_pct': hra_pct_val,
            'generation_date': formatted_gen_date,
            'active_tab': request.GET.get('active_tab', 'generate')
        }
        return render(request, 'payroll/manage.html', context)

    def post(self, request):
        import calendar
        from core.utils import apply_pending_hikes
        apply_pending_hikes()
        today = get_local_date()
        _, max_days_in_month = calendar.monthrange(today.year, today.month)
        
        # Enforce payroll generation only on the day/date set by Super Admin
        from core.dynamodb_service import SettingsTable
        gen_date_setting = SettingsTable.get_item({'SettingKey': 'Payroll_Generation_Date'})
        gen_date_str = gen_date_setting.get('Value') if gen_date_setting else None
        
        if gen_date_str:
            val_upper = str(gen_date_str).strip().upper()
            if val_upper in ('LAST', 'LAST_DAY'):
                target_day = max_days_in_month
                label = "last day of month"
            else:
                try:
                    cfg_day = int(gen_date_str)
                    target_day = min(cfg_day, max_days_in_month)
                    if cfg_day > max_days_in_month:
                        label = f"last day of month ({target_day}th)"
                    else:
                        label = format_day_with_ordinal(cfg_day)
                except ValueError:
                    try:
                        dt_obj = datetime.datetime.strptime(gen_date_str, "%Y-%m-%d")
                        target_day = min(dt_obj.day, max_days_in_month)
                        label = format_day_with_ordinal(dt_obj.day)
                    except ValueError:
                        target_day = min(30, max_days_in_month)
                        label = "30th of month"
        else:
            # Fallback to default (30th of the month, or last day if month has fewer days)
            target_day = min(30, max_days_in_month)
            if max_days_in_month < 30:
                label = f"last day of month ({target_day}th)"
            else:
                label = "30th of month"

        if today.day != target_day:
            messages.error(request, f"Payroll Run Failed: Today is the {today.day}th. Payroll can only be executed on the {label}.")
            return redirect('manage_payroll')
            
        selected_ids = request.POST.getlist('selected_employees')
        if not selected_ids:
            messages.warning(request, "No employees were selected.")
            return redirect('manage_payroll')

        month_year = today.strftime("%b_%Y").lower()
        
        # Bundle data for Super Admin Approval
        batch_data = []
        for emp_id in selected_ids:
            try:
                emp = EmployeesTable.get_item({'EmployeeID': emp_id})
                if not emp: continue
                
                # Get increment percentage
                increment_percent = float(request.POST.get(f'increment_{emp_id}', '0'))
                salary_pa = safe_float(emp.get('SalaryPA'))
                increment_amount = salary_pa * (increment_percent / 100)

                # Get bonus amount
                bonus_amount = float(request.POST.get(f'bonus_{emp_id}', '0'))
                bonus_percent = 0

                lop_mode = request.POST.get(f'lop_mode_{emp_id}', 'automatic')
                if lop_mode == 'manual':
                    manual_days = float(request.POST.get(f'manual_lop_days_{emp_id}', 0))
                    
                    if today.month == 1:
                        prev_month, prev_year = 12, today.year - 1
                    else:
                        prev_month, prev_year = today.month - 1, today.year
                    
                    start_date = datetime.date(prev_year, prev_month, 27)
                    end_date = datetime.date(today.year, today.month, 26)
                    num_days_period = (end_date - start_date).days + 1
                    
                    attendance = {
                        "total_days": num_days_period,
                        "paid_days": num_days_period - manual_days,
                        "lop_days": manual_days
                    }
                else:
                    attendance = get_attendance_summary(emp_id, today.month, today.year)

                payslip_item = process_payroll_logic(emp, attendance, today.month, today.year, increment=increment_amount, bonus=bonus_amount)
                
                # Serialize PayslipData
                serialized_payslip = {k: str(v) if isinstance(v, (Decimal, float)) else v for k, v in payslip_item.items()}
                serialized_payslip['PaidDays'] = str(attendance.get('paid_days', 0))
                
                # Bundle data
                batch_data.append({
                    'EmployeeID': emp_id,
                    'EmployeeName': f"{emp.get('FirstName')} {emp.get('LastName')}",
                    'MonthYear': month_year,
                    'PayslipData': serialized_payslip,
                    'Attendance': {k: str(v) if isinstance(v, (Decimal, float)) else v for k, v in attendance.items()},
                    'IncrementPercent': str(increment_percent),
                    'BonusPercent': str(bonus_percent)
                })
            except Exception as e:
                print(f"Error bundling payroll for {emp_id}: {e}")

        if not batch_data:
            messages.error(request, "Failed to process selected employees.")
            return redirect('manage_payroll')
        # Create Payroll Approval Request
        import uuid
        request_id = str(uuid.uuid4())
        # Resolve submitter name
        try:
            submitter_emp = EmployeesTable.get_item({'EmployeeID': request.user.employee_id})
            submitter_name = f"{submitter_emp.get('FirstName', '')} {submitter_emp.get('LastName', '')}" if submitter_emp else str(request.user.employee_id)
        except Exception:
            submitter_name = str(request.user.employee_id or 'HR Admin')
        
        # Resolve dynamic workflow step
        org_id = getattr(request.user, 'org_id', None)
        status, approver_id, is_final = resolve_workflow_step(
            employee_id=request.user.employee_id,
            org_id=org_id,
            current_status=None,
            action='submit',
            request_type='payroll_approval'
        )

        if is_final:
            # 0 Approval steps configured (Auto-Approved immediately)
            from core.dynamodb_service import PayslipsTable
            count = 0
            for item in batch_data:
                try:
                    emp_id = item['EmployeeID']
                    payslip_data = item['PayslipData']
                    attendance = item['Attendance']
                    m_year = item['MonthYear']
                    final_payslip = {k: Decimal(v) if k in ['NetPay', 'Basic', 'HRA', 'SpecialAllowance', 'PF', 'EmployerPF', 'EmployerEPS', 'EmployerEDLI', 'ESI', 'PT', 'TDS', 'Bonus', 'GrossSalary', 'TotalDeductions', 'AdjustedGross', 'LOPDeduction', 'IncrementAdded', 'BaseSalaryPA', 'NewSalaryPA'] else v for k, v in payslip_data.items()}
                    final_payslip.update({
                        'EmployeeID': emp_id,
                        'MonthYear': m_year,
                        'PaidDays': payslip_data.get('PaidDays', str(attendance.get('paid_days', 0))),
                        'GeneratedAt': get_local_now().isoformat(),
                        'ApprovedBy': request.user.employee_id,
                        'IncrementPercentage': item.get('IncrementPercent', '0'),
                        'BonusPercentage': item.get('BonusPercent', '0')
                    })
                    PayslipsTable.put_item(final_payslip)
                    count += 1
                except Exception as e:
                    print(f"Error publishing payslip for {emp_id}: {e}")

            messages.success(request, f"Payroll for {count} employees generated and approved immediately (0 Approval Steps Workflow).")
            return redirect('manage_payroll')

        approval_item = {
            'OrgID': org_id,
            'RequestID': request_id,
            'MonthYear': month_year,
            'Status': status,
            'ApproverID': approver_id,
            'SubmittedBy': submitter_name,
            'SubmittedByID': request.user.employee_id,
            'SubmittedAt': get_local_now().isoformat(),
            'BatchData': batch_data,
            'TotalNetPay': str(round(sum(float(b['PayslipData']['NetPay']) for b in batch_data), 2)),
            'EmployeeCount': len(batch_data)
        }
        
        PayrollApprovalsTable.put_item(approval_item)
        
        messages.success(request, f"Payroll for {len(batch_data)} employees submitted. Status: {status}")
        return redirect('manage_payroll')

class DownloadPayslipView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'payslips'
    def get(self, request, month_year, emp_id=None):
        target_emp_id = emp_id if (emp_id and request.user.role in ['HR ADMIN', 'Super admin', 'Platform Admin']) else request.user.employee_id
        record = PayslipsTable.get_item({'EmployeeID': target_emp_id, 'MonthYear': month_year})
        if not record: return HttpResponse("Payslip not found.", status=404)
            
        employee = EmployeesTable.get_item({'EmployeeID': target_emp_id})
        emp_name = f"{employee.get('FirstName', '')} {employee.get('LastName', '')}"
        
        org_id = employee.get('OrgID') if employee else None
        org_name = "Kyro People"
        if org_id:
            from core.dynamodb_service import OrganizationsTable
            org = OrganizationsTable.get_item({'OrgID': org_id})
            if org:
                org_name = org.get('Name', 'Kyro People')
        
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # Register Fonts (Windows Support for Rupee Symbol)
        font_regular = "Helvetica"
        font_bold = "Helvetica-Bold"
        font_italic = "Helvetica-Oblique"
        currency_symbol = "Rs."
        
        try:
            arial_path = "C:/Windows/Fonts/arial.ttf"
            arial_bold_path = "C:/Windows/Fonts/arialbd.ttf"
            if os.path.exists(arial_path):
                pdfmetrics.registerFont(TTFont('Arial', arial_path))
                font_regular = "Arial"
                currency_symbol = "₹"
            if os.path.exists(arial_bold_path):
                pdfmetrics.registerFont(TTFont('Arial-Bold', arial_bold_path))
                font_bold = "Arial-Bold"
            
            arial_italic_path = "C:/Windows/Fonts/ariali.ttf"
            if os.path.exists(arial_italic_path):
                pdfmetrics.registerFont(TTFont('Arial-Italic', arial_italic_path))
                font_italic = "Arial-Italic"
        except: pass

        # 1. Header (Centered without logo)
        header_text = org_name.upper()
        header_font_size = 26
        while header_font_size > 14 and p.stringWidth(header_text, font_bold, header_font_size) > (width - 100):
            header_font_size -= 2
        p.setFont(font_bold, header_font_size)
        p.setFillColorRGB(0.07, 0.2, 0.45) # Corporate Blue
        p.drawCentredString(width / 2, height - 75, header_text)
        
        p.setStrokeColorRGB(0.07, 0.2, 0.45)
        p.setLineWidth(1.5)
        p.line(50, height - 100, width - 50, height - 100)
        
        p.setFont(font_bold, 12)
        p.setFillColorRGB(0.3, 0.3, 0.3)
        p.drawCentredString(width / 2, height - 125, f"PAYROLL STATEMENT - {month_year.upper()}")

        # 2. Employee Details Box (Rounded with subtle fill)
        p.setStrokeColorRGB(0.85, 0.85, 0.85)
        p.roundRect(50, height - 255, width - 100, 115, 5, fill=0, stroke=1)
        
        p.setFont(font_bold, 10)
        p.setFillColorRGB(0, 0, 0)
        p.drawString(70, height - 165, "Employee Name:")
        p.drawString(70, height - 185, "Employee ID:")
        p.drawString(70, height - 205, "Joining Date:")
        p.drawString(70, height - 225, "PF Number:")
        
        p.drawString(330, height - 165, "Designation:")
        p.drawString(330, height - 185, "Department:")
        p.drawString(330, height - 205, "Working Days:")
        p.drawString(330, height - 225, "UAN Number:")
        
        p.setFont(font_regular, 10)
        p.setFillColorRGB(0, 0, 0)
        
        # Calculate dynamic font size for name to prevent overlap
        name_font_size = 10.0
        available_width = 330 - 165 - 10 # 155 points
        while name_font_size > 7.0 and p.stringWidth(emp_name, font_regular, name_font_size) > available_width:
            name_font_size -= 0.5
            
        p.setFont(font_regular, name_font_size)
        p.drawString(165, height - 165, emp_name)
        
        # Reset font to regular 10 for other details
        p.setFont(font_regular, 10)
        p.drawString(165, height - 185, target_emp_id)
        p.drawString(165, height - 205, employee.get('JoinedDate') or 'N/A')
        p.drawString(165, height - 225, employee.get('PFNumber') or 'N/A')
        
        p.drawString(420, height - 165, employee.get('Designation', 'N/A'))
        p.drawString(420, height - 185, employee.get('Department', 'Engineering'))
        
        # Working Days with fallback for old records
        working_days = record.get('PaidDays')
        if working_days is None:
            try:
                parts = month_year.split('_')
                m_idx = datetime.datetime.strptime(parts[0], "%b").month
                y_idx = int(parts[1])
                summary = get_attendance_summary(target_emp_id, m_idx, y_idx)
                working_days = summary['paid_days']
            except:
                working_days = 'N/A'
        
        p.drawString(420, height - 205, str(working_days))
        p.drawString(420, height - 225, employee.get('UANNumber') or 'N/A')

        # 3. Salary Table (Earnings & Deductions)
        y = height - 270
        
        # Table Headers
        p.setStrokeColorRGB(0, 0, 0)
        p.rect(50, y - 20, 250, 20, fill=0, stroke=1) # Earnings Header
        p.rect(310, y - 20, 250, 20, fill=0, stroke=1) # Deductions Header
        
        p.setFont(font_bold, 10)
        p.setFillColorRGB(0, 0, 0) # Black text for headers
        p.drawString(60, y - 13, "Earnings")
        p.drawRightString(290, y - 13, "Amount")
        p.drawString(320, y - 13, "Deductions")
        p.drawRightString(550, y - 13, "Amount")
        
        y -= 20
        p.setFont(font_regular, 10)
        p.setFillColorRGB(0, 0, 0)

        # Helper for row drawing
        def draw_row(p, label_e, val_e, label_d, val_d, curr_y, is_tint=False):
            p.setFillColorRGB(0, 0, 0)
            
            p.drawString(60, curr_y - 12, label_e)
            if val_e is not None:
                p.drawRightString(290, curr_y - 12, f"{currency_symbol} {float(val_e):,.2f}")
            
            if label_d:
                p.drawString(320, curr_y - 12, label_d)
                if val_d is not None:
                    p.drawRightString(550, curr_y - 12, f"{currency_symbol} {float(val_d):,.2f}")
            return curr_y - 18

        y = draw_row(p, "Basic Salary", record.get('Basic', 0), "Income Tax (TDS)", record.get('TDS', 0), y, True)
        y = draw_row(p, "HRA", record.get('HRA', 0), "Provident Fund (PF)", record.get('PF', 0), y, False)
        y = draw_row(p, "Special Allowance", record.get('SpecialAllowance', 0), "ESI", record.get('ESI', 0), y, True)
        
        # Professional Tax (only deduction side)
        y = draw_row(p, "", None, "Professional Tax (PT)", record.get('PT', 0), y, False)

        # Increment Row (Conditional)
        if float(record.get('IncrementAdded', 0)) > 0:
            inc_pct = record.get('IncrementPercentage', 0)
            monthly_inc = float(record.get('IncrementAdded', 0)) / 12
            p.setFillColorRGB(0, 0, 0)
            p.setFont(font_bold, 9)
            p.drawString(60, y - 12, f"Salary Increment ({inc_pct}%)")
            p.drawRightString(290, y - 12, f"+ {currency_symbol} {monthly_inc:,.2f}")
            y -= 18

        # Bonus Row (Conditional)
        if float(record.get('Bonus', 0)) > 0:
            bonus_pct = record.get('BonusPercentage', 0)
            p.setFillColorRGB(0, 0, 0)
            p.setFont(font_bold, 9)
            p.drawString(60, y - 12, f"Performance Bonus ({bonus_pct}%)")
            p.drawRightString(290, y - 12, f"+ {currency_symbol} {float(record.get('Bonus', 0)):,.2f}")
            y -= 18

        # LOP Row (Deduction on Earnings Side)
        if float(record.get('LOPDeduction', 0)) > 0:
            p.setFillColorRGB(0, 0, 0)
            p.setFont(font_italic, 9)
            p.drawString(60, y - 12, "LOP Deduction")
            p.drawRightString(290, y - 12, f"- {currency_symbol} {float(record.get('LOPDeduction', 0)):,.2f}")
            y -= 18

        # Table Totals
        y -= 10
        p.setStrokeColorRGB(0, 0, 0)
        p.line(50, y, 290, y)
        p.line(320, y, 550, y)
        
        y -= 15
        p.setFont(font_bold, 10)
        p.setFillColorRGB(0, 0, 0)
        p.drawString(60, y, "Adjusted Gross")
        p.drawRightString(290, y, f"{currency_symbol} {float(record.get('AdjustedGross', 0)):,.2f}")
        p.drawString(320, y, "Total Deductions")
        p.drawRightString(550, y, f"{currency_symbol} {float(record.get('TotalDeductions', 0)):,.2f}")

        # 4. NET PAYABLE (Highlight Box)
        y -= 70
        p.setStrokeColorRGB(0, 0, 0)
        p.roundRect(50, y - 15, width - 100, 50, 8, fill=0, stroke=1)
        
        p.setFont(font_bold, 16)
        p.setFillColorRGB(0, 0, 0)
        p.drawString(75, y + 5, "NET PAYABLE")
        p.setFont(font_bold, 20)
        p.drawRightString(width - 75, y + 5, f"{currency_symbol} {float(record.get('NetPay', 0)):,.2f}")
        
        # 5. Footer
        p.setFont(font_italic, 8)
        p.setFillColorRGB(0, 0, 0)
        p.drawCentredString(width / 2, 40, "This is a computer-generated document and does not require a physical signature.")
        
        p.showPage()
        p.save()
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        disposition = 'inline' if request.GET.get('inline') == '1' else 'attachment'
        response['Content-Disposition'] = f'{disposition}; filename="Payslip_{month_year}.pdf"'
        return response

class PayrollApprovalView(FeatureRequiredMixin, LoginRequiredMixin, TemplateView):
    required_feature = 'payroll'
    template_name = 'payroll/approvals.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_requests = PayrollApprovalsTable.scan()
        
        filter_month = self.request.GET.get('month', '')
        filter_year = self.request.GET.get('year', '')

        user_emp_id = self.request.user.employee_id
        user_role = self.request.user.role

        if user_role == 'Super admin':
            pending = [r for r in all_requests if r.get('Status', '').startswith('Pending')]
            history = [r for r in all_requests if not r.get('Status', '').startswith('Pending')]
        else:
            pending = [r for r in all_requests if r.get('Status', '').startswith('Pending') and r.get('ApproverID') == user_emp_id]
            history = [r for r in all_requests if not r.get('Status', '').startswith('Pending') and (r.get('SubmittedByID') == user_emp_id or r.get('ProcessedBy') == user_emp_id)]
        
        if filter_month:
            history = [r for r in history if r.get('MonthYear', '').startswith(f"{filter_month}_")]
        if filter_year:
            history = [r for r in history if r.get('MonthYear', '').endswith(f"_{filter_year}")]
        
        # Map Processor Names
        all_emps = EmployeesTable.scan()
        emp_obj_map = {e['EmployeeID']: f"{e.get('FirstName', '')} {e.get('LastName', '')}" for e in all_emps}
        
        for r in history:
            pb_id = r.get('ProcessedBy')
            if pb_id:
                name = emp_obj_map.get(pb_id, '').strip()
                r['ProcessorName'] = name if name else pb_id
            else:
                r['ProcessorName'] = 'System'

        context['pending_requests'] = sorted(pending, key=lambda x: x.get('SubmittedAt', ''), reverse=True)
        
        history_sorted = sorted(history, key=lambda x: x.get('SubmittedAt', ''), reverse=True)
        context['history_requests'] = history_sorted
        
        paginator_hist = Paginator(history_sorted, 10)
        page_hist = self.request.GET.get('page')
        context['history_page_obj'] = paginator_hist.get_page(page_hist)
        
        context['pending_count'] = len(pending)
        
        requested_tab = self.request.GET.get('tab', 'pending')
        details_id = self.request.GET.get('details')
        if details_id:
            details_req = next((r for r in all_requests if r.get('RequestID') == details_id), None)
            if details_req:
                pb_id = details_req.get('ProcessedBy')
                if pb_id:
                    name = emp_obj_map.get(pb_id, '').strip()
                    details_req['ProcessorName'] = name if name else pb_id
                else:
                    details_req['ProcessorName'] = 'System'
                context['selected_details'] = details_req
                
                batch_data = details_req.get('BatchData', [])
                paginator_batch = Paginator(batch_data, 10)
                page_batch = self.request.GET.get('batch_page')
                context['batch_page_obj'] = paginator_batch.get_page(page_batch)
                requested_tab = 'details'
            else:
                if requested_tab == 'details':
                    requested_tab = 'history'
        else:
            if requested_tab == 'details':
                requested_tab = 'history'
                
        context['active_tab'] = requested_tab
        
        # Filters context
        context['months'] = [
            ('jan', 'January'), ('feb', 'February'), ('mar', 'March'), ('apr', 'April'),
            ('may', 'May'), ('jun', 'June'), ('jul', 'July'), ('aug', 'August'),
            ('sep', 'September'), ('oct', 'October'), ('nov', 'November'), ('dec', 'December')
        ]
        context['years'] = list(range(2024, get_local_date().year + 1))
        context['filter_month'] = filter_month
        context['filter_year'] = filter_year
        context['is_active'] = False

        # Get payroll generation date setting
        from core.dynamodb_service import SettingsTable
        gen_date_setting = SettingsTable.get_item({'SettingKey': 'Payroll_Generation_Date'})
        gen_val = gen_date_setting.get('Value') if gen_date_setting else ''
        if gen_val:
            try:
                day_str = str(int(gen_val))
            except ValueError:
                try:
                    dt_obj = datetime.datetime.strptime(str(gen_val), "%Y-%m-%d")
                    day_str = str(dt_obj.day)
                except ValueError:
                    day_str = str(gen_val)
        else:
            day_str = ''

        context['payroll_generation_date'] = day_str
        context['payroll_generation_date_formatted'] = format_day_with_ordinal(day_str) if day_str else '30th of month'

        days_list = []
        for d in range(1, 32):
            if 11 <= (d % 100) <= 13:
                suf = 'th'
            else:
                suf = {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')
            days_list.append({'value': str(d), 'label': f"{d}{suf} of month"})
        days_list.append({'value': 'LAST', 'label': 'Last day of month'})
        context['days_list'] = days_list

        tomorrow_dt = get_local_date() + datetime.timedelta(days=1)
        context['tomorrow_date'] = tomorrow_dt.strftime('%Y-%m-%d')
        context['tomorrow_formatted'] = tomorrow_dt.strftime('%d %B, %Y')

        return context

class SetPayrollGenerationDateView(FeatureRequiredMixin, SuperAdminRequiredMixin, View):
    required_feature = 'payroll'
    def post(self, request):
        from core.dynamodb_service import SettingsTable
        
        # Check if they clicked the clear button
        if request.POST.get('clear') == 'true':
            SettingsTable.delete_item({'SettingKey': 'Payroll_Generation_Date'})
            messages.success(request, 'Payroll generation date cleared. Reverted to default (30th of month).')
        else:
            generation_date = request.POST.get('generation_date', '').strip()
            if generation_date:
                if generation_date.upper() in ('LAST', 'LAST_DAY'):
                    SettingsTable.put_item({
                        'SettingKey': 'Payroll_Generation_Date',
                        'Value': 'LAST'
                    })
                    messages.success(request, 'Payroll generation day successfully set to Last day of month.')
                else:
                    try:
                        day_num = int(generation_date)
                        if 1 <= day_num <= 31:
                            SettingsTable.put_item({
                                'SettingKey': 'Payroll_Generation_Date',
                                'Value': str(day_num)
                            })
                            formatted_label = format_day_with_ordinal(day_num)
                            messages.success(request, f'Payroll generation day successfully set to {formatted_label}.')
                        else:
                            messages.error(request, 'Invalid day selected. Please select a day between 1 and 31.')
                    except ValueError:
                        try:
                            dt_obj = datetime.datetime.strptime(generation_date, "%Y-%m-%d")
                            day_num = dt_obj.day
                            SettingsTable.put_item({
                                'SettingKey': 'Payroll_Generation_Date',
                                'Value': str(day_num)
                            })
                            formatted_label = format_day_with_ordinal(day_num)
                            messages.success(request, f'Payroll generation day successfully set to {formatted_label}.')
                        except ValueError:
                            messages.error(request, 'Invalid day selected. Please select a valid day of the month.')
            else:
                messages.error(request, 'Please select a day of the month.')
                
        return redirect('payroll_approval_list')

class UpdateESIConfigView(FeatureRequiredMixin, PayrollRequiredMixin, View):
    required_feature = 'payroll'
    def post(self, request):
        from core.dynamodb_service import SettingsTable
        esi_amount = request.POST.get('esi_amount', '').strip()
        try:
            if esi_amount:
                amount = float(esi_amount)
                if amount < 0:
                    messages.error(request, 'ESI amount cannot be negative.')
                    return redirect('manage_payroll')
                SettingsTable.put_item({
                    'SettingKey': 'Global_ESI_Amount',
                    'Value': str(amount)
                })
                messages.success(request, f'Global ESI Amount updated to ₹{amount}.')
            else:
                SettingsTable.delete_item({'SettingKey': 'Global_ESI_Amount'})
                messages.success(request, 'Global ESI Amount cleared. No ESI will be deducted.')
        except ValueError:
            messages.error(request, 'Invalid ESI amount. Please enter a valid number.')
        except Exception as e:
            messages.error(request, f'Failed to update ESI configuration: {e}')
        
        return redirect('manage_payroll')

class ProcessPayrollApprovalView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'payroll'
    def post(self, request, request_id):
        action = request.POST.get('action') # 'approve' or 'reject'
        approval_request = PayrollApprovalsTable.get_item({'RequestID': request_id})
        
        if not approval_request:
            messages.error(request, "Approval request not found.")
            return redirect('payroll_approval_list')
            
        user_emp_id = request.user.employee_id
        user_role = request.user.role
        current_approver_id = approval_request.get('ApproverID')
        
        if user_role != 'Super admin' and current_approver_id != user_emp_id:
            messages.error(request, "You are not authorized to approve/reject this payroll request.")
            return redirect('payroll_approval_list')
            
        org_id = getattr(request.user, 'org_id', None)
        current_status = approval_request.get('Status', 'Pending')
        
        new_status, next_approver_id, is_final = resolve_workflow_step(
            employee_id=approval_request.get('SubmittedByID'),
            org_id=org_id,
            current_status=current_status,
            action=action,
            request_type='payroll_approval'
        )
            
        if action == 'reject':
            approval_request['Status'] = f'Rejected by {user_role}'
            approval_request['ProcessedAt'] = get_local_now().isoformat()
            approval_request['ProcessedBy'] = user_emp_id
            approval_request['ApproverID'] = None
            PayrollApprovalsTable.put_item(approval_request)
            messages.warning(request, "Payroll request has been rejected.")
            return redirect('payroll_approval_list')
            
        if action == 'approve':
            if not is_final:
                approval_request['Status'] = new_status
                approval_request['ApproverID'] = next_approver_id
                approval_request['ProcessedAt'] = get_local_now().isoformat()
                approval_request['ProcessedBy'] = user_emp_id
                PayrollApprovalsTable.put_item(approval_request)
                messages.success(request, f"Payroll approved by you. Sent for next stage: {new_status}")
                return redirect('payroll_approval_list')
                
            default_next_date = (get_local_date() + datetime.timedelta(days=1)).isoformat()
            scheduled_release_date = request.POST.get('scheduled_release_date', '').strip() or default_next_date
            now = get_local_now()
            
            # Determine if payslip release is scheduled for future/morning 8 AM or immediate
            scheduled_at_8am = False
            try:
                target_dt = datetime.datetime.strptime(f"{scheduled_release_date} 08:00:00", "%Y-%m-%d %H:%M:%S")
                if now.tzinfo:
                    target_dt = target_dt.replace(tzinfo=now.tzinfo)
                if now < target_dt:
                    scheduled_at_8am = True
            except Exception:
                pass

            release_status = 'Scheduled' if scheduled_at_8am else 'Released'

            batch_data = approval_request.get('BatchData', [])
            count = 0
            error_count = 0
            from core.dynamodb_service import OrganizationsTable
            org = OrganizationsTable.get_item({'OrgID': org_id}) if org_id else None
            bank_service = UniversalBankService(org)
            
            for item in batch_data:
                try:
                    emp_id = item['EmployeeID']
                    payslip_data = item['PayslipData']
                    attendance = item['Attendance']
                    month_year = item['MonthYear']
                    
                    # 1. Create Payslip Record
                    final_payslip = {k: Decimal(v) if k in ['NetPay', 'Basic', 'HRA', 'SpecialAllowance', 'PF', 'EmployerPF', 'EmployerEPS', 'EmployerEDLI', 'ESI', 'PT', 'TDS', 'Bonus', 'GrossSalary', 'TotalDeductions', 'AdjustedGross', 'LOPDeduction', 'IncrementAdded', 'BaseSalaryPA', 'NewSalaryPA'] else v for k, v in payslip_data.items()}
                    final_payslip.update({
                        'EmployeeID': emp_id,
                        'MonthYear': month_year,
                        'PaidDays': payslip_data.get('PaidDays', str(attendance.get('paid_days', 0))),
                        'GeneratedAt': get_local_now().isoformat(),
                        'ApprovedBy': request.user.employee_id,
                        'IncrementPercentage': item.get('IncrementPercent', '0'),
                        'BonusPercentage': item.get('BonusPercent', '0'),
                        'ScheduledReleaseDate': scheduled_release_date,
                        'ScheduledReleaseTime': '08:00:00',
                        'ReleaseStatus': release_status
                    })
                    PayslipsTable.put_item(final_payslip)
                    
                    # 2. Update Employee (SalaryPA, PF_Balance)
                    emp = EmployeesTable.get_item({'EmployeeID': emp_id})
                    if emp:
                        pf_deduction = float(payslip_data.get('PF', 0))
                        if pf_deduction > 0:
                            curr_bal = float(emp.get('PF_Balance', 0))
                            emp['PF_Balance'] = str(round(curr_bal + pf_deduction, 2))
                        
                        # NewSalaryPA from payslip_data
                        if payslip_data.get('NewSalaryPA'):
                            emp['SalaryPA'] = payslip_data['NewSalaryPA']
                            
                        EmployeesTable.put_item(emp)
                        
                        # Send notification & email ONLY if release_status == 'Released'
                        if release_status == 'Released':
                            try:
                                month_name = month_year.split('_')[0].upper()
                                year_val = month_year.split('_')[1]
                                email_subject = f"Payslip for {month_name} {year_val} Released"
                                email_body = f"Hi {emp.get('FirstName', 'Employee')},\n\nYour payslip for the month of {month_name} {year_val} has been generated and released.\n\nGross Salary: INR {payslip_data.get('GrossSalary')}\nTotal Deductions: INR {payslip_data.get('TotalDeductions')}\nNet Payable: INR {payslip_data.get('NetPay')}\n\nYou can view and download your detailed payslip from the employee portal.\n\nBest regards,\nKyro People HR Team"
                                
                                send_notification(
                                    employee_id=emp_id,
                                    title=f"Payslip Generated - {month_name} {year_val}",
                                    message=f"Your payslip for {month_name} {year_val} has been released with Net Pay of INR {payslip_data.get('NetPay')}.",
                                    n_type='Payroll',
                                    icon='fa-file-invoice-dollar',
                                    color='success',
                                    email_subject=email_subject,
                                    email_body=email_body
                                )
                            except Exception as email_err:
                                print(f"Error sending payslip notification for {emp_id}: {email_err}")
                    
                    # 3. Trigger Bank API Transfer
                    net_pay = float(payslip_data.get('NetPay', 0))
                    if net_pay > 0:
                        try:
                            bank_service.transfer_funds(emp, net_pay, f"Salary_{month_year}")
                        except Exception as e:
                            print(f"Bank Transfer Error during Approval for {emp_id}: {e}")
                    
                    count += 1
                except Exception as e:
                    print(f"Error processing approved payroll item for {emp_id}: {e}")
                    error_count += 1
            
            approval_request['Status'] = 'Approved'
            approval_request['ApproverID'] = None
            approval_request['ScheduledReleaseDate'] = scheduled_release_date
            approval_request['ScheduledReleaseTime'] = '08:00:00'
            approval_request['ReleaseStatus'] = release_status
            approval_request['ProcessedAt'] = get_local_now().isoformat()
            approval_request['ProcessedBy'] = request.user.employee_id
            PayrollApprovalsTable.put_item(approval_request)
            
            if release_status == 'Scheduled':
                messages.success(request, f"Payroll approved! Payslip release scheduled for {scheduled_release_date} at 08:00 AM for {count} employees.")
            else:
                messages.success(request, f"Payroll approved and executed for {count} employees. {error_count} errors.")
            return redirect('payroll_approval_list')
        
        return redirect('payroll_approval_list')

class HistoricalPayrollView(FeatureRequiredMixin, LoginRequiredMixin, TemplateView):
    required_feature = 'payroll'
    template_name = 'payroll/historical.html'

    def dispatch(self, request, *args, **kwargs):
        is_super_admin = getattr(request.user, 'role', '') == 'Super admin'
        user_permissions = getattr(request.user, 'permissions', [])
        if not is_super_admin and 'historical_payroll_access' not in user_permissions:
            return redirect('forbidden_403')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Fetch all users to find Super Admins
        all_users = UsersTable.scan()

        super_admin_ids = {u.get('UserID') for u in all_users if u.get('Role') == 'Super admin'}

        # Fetch all active employees for the dropdown and filter out Super Admins
        all_employees = EmployeesTable.scan()
        filtered_employees = [e for e in all_employees if e.get('UserID') not in super_admin_ids]
        filtered_employees = sorted(filtered_employees, key=lambda e: e.get('FirstName', ''))
        context['employees'] = filtered_employees

        # Calculate earliest joining year dynamically
        earliest_year = get_local_date().year
        for e in all_employees:
            joined_str = e.get('JoinedDate')
            if joined_str:
                try:
                    y = int(joined_str.split('-')[0])
                    if y < earliest_year:
                        earliest_year = y
                except:
                    pass
        if earliest_year > 2024:
            earliest_year = 2024
        context['years'] = list(range(earliest_year, get_local_date().year + 1))

        selected_emp_id = self.request.GET.get('employee_id')
        
        if selected_emp_id:
            try:
                selected_emp = EmployeesTable.get_item({'EmployeeID': selected_emp_id})
                context['selected_employee'] = selected_emp
                
                from boto3.dynamodb.conditions import Key
                payslips = PayslipsTable.query(
                    KeyConditionExpression=Key('EmployeeID').eq(selected_emp_id)
                )
                
                # Combine and Sort
                combined_history = []
                total_net_paid = 0.0
                total_expenses_paid = 0.0
                
                for ps in payslips:
                    date_val = datetime.datetime.min
                    try:
                        month_str, year_str = ps.get('MonthYear', '').split('_')
                        date_val = datetime.datetime.strptime(f"{month_str[:3]} {year_str}", "%b %Y")
                    except: pass
                    
                    net_pay = float(ps.get('NetPay', 0))
                    total_net_paid += net_pay
                    
                    combined_history.append({
                        'Type': 'Salary',
                        'DateObj': date_val,
                        'DisplayDate': ps.get('GeneratedAt', '')[:10] if ps.get('GeneratedAt') else ps.get('MonthYear', ''),
                        'Description': f"Payroll for {ps.get('MonthYear', '').replace('_', ' ').title()}",
                        'Amount': net_pay
                    })
                
                expenses = ExpensesTable.query(
                    KeyConditionExpression=Key('EmployeeID').eq(selected_emp_id)
                )
                paid_expenses = [e for e in expenses if e.get('Status') == 'Paid']
                
                for exp in paid_expenses:
                    date_val = datetime.datetime.min
                    try:
                        date_val = datetime.datetime.strptime(exp.get('RequestDate', ''), "%Y-%m-%d")
                    except: pass
                    
                    amt = float(exp.get('Amount', 0))
                    total_expenses_paid += amt
                    
                    combined_history.append({
                        'Type': 'Expense',
                        'DateObj': date_val,
                        'DisplayDate': exp.get('RequestDate', ''),
                        'Description': exp.get('ExpenseCategory', 'Expense Reimbursement'),
                        'Amount': amt
                    })
                    
                combined_history = sorted(combined_history, key=lambda x: x['DateObj'], reverse=True)
                
                # Apply Filters
                filter_month = self.request.GET.get('month', '')
                filter_year = self.request.GET.get('year', '')
                
                if filter_month or filter_year:
                    filtered_history = []
                    for item in combined_history:
                        if item['DateObj'] != datetime.datetime.min:
                            match = True
                            if filter_month and str(item['DateObj'].month) != filter_month:
                                match = False
                            if filter_year and str(item['DateObj'].year) != filter_year:
                                match = False
                            if match:
                                filtered_history.append(item)
                    combined_history = filtered_history

                # Pagination
                paginator = Paginator(combined_history, 10)
                page_number = self.request.GET.get('page')
                page_obj = paginator.get_page(page_number)
                
                context['page_obj'] = page_obj
                context['filter_month'] = filter_month
                context['filter_year'] = filter_year
                context['current_year'] = get_local_now().year
                
                context['combined_history'] = combined_history
                context['total_net_paid'] = total_net_paid
                context['total_expenses_paid'] = total_expenses_paid
                context['show_payroll_history'] = True
            except Exception as e:
                print(f"Error fetching historical payroll: {e}")
                
        return context


class ManagePayrollConfigView(LoginRequiredMixin, RoleRequiredMixin, View):
    allowed_roles = ['Super admin', 'HR ADMIN', 'Platform Admin']

    def get(self, request):
        from core.dynamodb_service import OrganizationsTable
        from core.industry_templates import get_industry_profile
        org_id = getattr(request.user, 'org_id', None)
        if not org_id:
            messages.error(request, "Organization context missing.")
            return redirect('payslips_view')

        org = OrganizationsTable.get_item({'OrgID': org_id}) or {}
        payroll_config = org.get('PayrollConfig', {}) or {}
        industry_type = org.get('IndustryType', 'SOFTWARE_IT')
        industry_profile = get_industry_profile(industry_type)

        context = {
            'payroll_config': payroll_config,
            'org': org,
            'industry_type': industry_type,
            'industry_profile': industry_profile
        }
        return render(request, 'payroll/manage_payroll_config.html', context)

    def post(self, request):
        from core.dynamodb_service import OrganizationsTable
        org_id = getattr(request.user, 'org_id', None)
        if not org_id:
            messages.error(request, "Organization context missing.")
            return redirect('payslips_view')

        org = OrganizationsTable.get_item({'OrgID': org_id})
        if not org:
            messages.error(request, "Organization record not found.")
            return redirect('manage_payroll_config')

        payroll_config = {
            'piece_rate_unit_amount': safe_decimal(request.POST.get('piece_rate_unit_amount', 0)),
            'sales_commission_per_unit': safe_decimal(request.POST.get('sales_commission_per_unit', 0)),
            'sales_target_bonus_flat': safe_decimal(request.POST.get('sales_target_bonus_flat', 0)),
            'till_shortage_allowance_limit': safe_decimal(request.POST.get('till_shortage_allowance_limit', 0)),
            'night_shift_allowance_per_day': safe_decimal(request.POST.get('night_shift_allowance_per_day', 0)),
            'cold_storage_risk_allowance': safe_decimal(request.POST.get('cold_storage_risk_allowance', 0)),
            'lecture_rate_per_hour': safe_decimal(request.POST.get('lecture_rate_per_hour', 0)),
            'exam_duty_allowance_per_session': safe_decimal(request.POST.get('exam_duty_allowance_per_session', 0)),
            'paper_evaluation_rate_per_sheet': safe_decimal(request.POST.get('paper_evaluation_rate_per_sheet', 0)),
            'overtime_multiplier': safe_decimal(request.POST.get('overtime_multiplier', 1.0)),
            'pf_deduction_percentage': safe_decimal(request.POST.get('pf_deduction_percentage', 0)),
            'esi_deduction_percentage': safe_decimal(request.POST.get('esi_deduction_percentage', 0)),
            'UpdatedAt': get_local_now().isoformat()
        }

        try:
            OrganizationsTable.update_item(
                Key={'OrgID': org_id},
                UpdateExpression="SET PayrollConfig = :pcfg",
                ExpressionAttributeValues={':pcfg': payroll_config}
            )
            messages.success(request, "Industry Payroll rates & rules saved successfully.")
        except Exception as e:
            messages.error(request, f"Failed to save payroll rates: {e}")

        return redirect('manage_payroll_config')

