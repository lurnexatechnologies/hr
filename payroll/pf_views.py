from django.shortcuts import render, redirect
from django.views import View
from django.contrib import messages
from django.core.paginator import Paginator
from auth_custom.mixins import LoginRequiredMixin, FeatureRequiredMixin
from core.dynamodb_service import EmployeesTable, PayslipsTable
from core.utils import get_local_date
import datetime
import calendar

class PFManagementView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'pf_management'
    def dispatch(self, request, *args, **kwargs):
        user_permissions = getattr(request.user, 'permissions', [])
        if 'payroll_access' not in user_permissions:
            return redirect('forbidden_403')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        # Default to current month/year if not provided
        today = get_local_date()
        selected_month = request.GET.get('month', today.strftime('%b').lower())
        selected_year = request.GET.get('year', str(today.year))
        month_year = f"{selected_month}_{selected_year}".lower()

        # Prepare dropdown data
        all_employees = EmployeesTable.scan()
        from core.dynamodb_service import UsersTable
        all_users = UsersTable.scan()
        super_admin_ids = {u.get('UserID') for u in all_users if u.get('Role') == 'Super admin' and u.get('UserID')}
        
        # Calculate the first employee's starting date year for the filter
        earliest_year = today.year
        for e in all_employees:
            joined_str = e.get('JoinedDate')
            if joined_str:
                try:
                    y = int(joined_str.split('-')[0])
                    if y < earliest_year:
                        earliest_year = y
                except: pass
        
        years = range(earliest_year, today.year + 2)
        months = [
            ('jan', 'January'), ('feb', 'February'), ('mar', 'March'),
            ('apr', 'April'), ('may', 'May'), ('jun', 'June'),
            ('jul', 'July'), ('aug', 'August'), ('sep', 'September'),
            ('oct', 'October'), ('nov', 'November'), ('dec', 'December')
        ]

        # Calculate the last day of the selected period for filtering
        m_map = {m[0]: i+1 for i, m in enumerate(months)}
        m_idx = m_map.get(selected_month, today.month)
        _, last_day = calendar.monthrange(int(selected_year), m_idx)
        period_end_date = datetime.date(int(selected_year), m_idx, last_day)

        pf_employees = []
        
        for e in all_employees:
            # Filter out Super Admins
            if e.get('EmployeeID') == 'LT-26000' or (e.get('UserID') and e.get('UserID') in super_admin_ids):
                continue
                
            # 1. Permanent Check: Only show Permanent employees for PF management
            if e.get('EmploymentType') != 'Permanent':
                continue
            
            # 2. Joined Date Check: Only show if they joined before or during the selected period
            joined_str = e.get('JoinedDate')
            if not joined_str:
                continue
                
            try:
                joined_date = datetime.datetime.strptime(joined_str, '%Y-%m-%d').date()
                if joined_date <= period_end_date:
                    # They joined on or before the end of the selected month
                    pf_employees.append(e)
            except:
                continue
        
        # Fetch payslips for the selected month/year to get PF and ESI status
        all_payslips = PayslipsTable.scan(
            FilterExpression="MonthYear = :my",
            ExpressionAttributeValues={":my": month_year}
        )
        payslip_map = {p['EmployeeID']: p for p in all_payslips}
        
        # Enrich employee data
        for emp in pf_employees:
            ps = payslip_map.get(emp['EmployeeID'], {})
            emp['CurrentPF'] = ps.get('PF', 0)
            emp['CurrentESI'] = ps.get('ESI', 0)
            emp['HasPayslip'] = bool(ps)
            emp['PF_Paid'] = ps.get('PF_Paid', False) # New status field

        # Sort by Name
        pf_employees.sort(key=lambda x: x.get('FirstName', ''))
        
        # Pagination
        paginator = Paginator(pf_employees, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        return render(request, 'payroll/pf_management.html', {
            'employees': page_obj,
            'total_count': len(pf_employees),
            'selected_month': selected_month,
            'selected_year': selected_year,
            'years': years,
            'months': months,
            'month_year': month_year
        })

class UpdatePFDetailsView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'pf_management'
    def dispatch(self, request, *args, **kwargs):
        user_permissions = getattr(request.user, 'permissions', [])
        if 'payroll_access' not in user_permissions:
            return redirect('forbidden_403')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, emp_id):
        pf_number = request.POST.get('pf_number', '').strip().upper()
        uan_number = request.POST.get('uan_number', '').strip()
        month = request.POST.get('month')
        year = request.POST.get('year')
        
        # 1. Validation checks
        if not pf_number.isalnum() or len(pf_number) != 22:
            messages.error(request, "Invalid PF Number. It must be exactly 22 alphanumeric characters.")
            if month and year:
                return redirect(f"/payroll/pf/management/?month={month}&year={year}")
            return redirect('pf_management')
            
        if not uan_number.isdigit() or len(uan_number) != 12:
            messages.error(request, "Invalid UAN Number. It must be exactly 12 numeric digits.")
            if month and year:
                return redirect(f"/payroll/pf/management/?month={month}&year={year}")
            return redirect('pf_management')
            
        try:
            employee = EmployeesTable.get_item({'EmployeeID': emp_id})
            if employee:
                employee['PFNumber'] = pf_number
                employee['UANNumber'] = uan_number
                EmployeesTable.put_item(employee)
                messages.success(request, f"PF/UAN details updated for {emp_id}")
            else:
                messages.error(request, "Employee not found.")
        except Exception as e:
            messages.error(request, f"Error updating PF details: {str(e)}")
            
        if month and year:
            return redirect(f"/payroll/pf/management/?month={month}&year={year}")
        return redirect('pf_management')

class MarkPFPaidView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'pf_management'
    def dispatch(self, request, *args, **kwargs):
        user_permissions = getattr(request.user, 'permissions', [])
        if 'payroll_access' not in user_permissions:
            return redirect('forbidden_403')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, emp_id):
        month_year = request.POST.get('month_year')
        status = request.POST.get('status') == 'true'
        
        if not month_year:
            messages.error(request, "Missing period information.")
            return redirect('pf_management')
            
        try:
            payslip = PayslipsTable.get_item({'EmployeeID': emp_id, 'MonthYear': month_year})
            if payslip:
                payslip['PF_Paid'] = status
                PayslipsTable.put_item(payslip)
                status_text = "Paid" if status else "Unpaid"
                messages.success(request, f"PF contribution for {emp_id} ({month_year}) marked as {status_text}.")
            else:
                messages.error(request, "No payslip found for this period. Generate payroll first.")
        except Exception as e:
            messages.error(request, f"Error updating PF status: {str(e)}")
            
        if month_year:
            parts = month_year.split('_')
            if len(parts) == 2:
                return redirect(f"/payroll/pf/management/?month={parts[0]}&year={parts[1]}")
                
        return redirect('pf_management')
