from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.generic import TemplateView
from auth_custom.mixins import HRRequiredMixin, ManagerRequiredMixin, LoginRequiredMixin, ApprovedOnboardingMixin, SuperAdminRequiredMixin, FeatureRequiredMixin
import datetime
import uuid
import csv
from boto3.dynamodb.conditions import Key
from decimal import Decimal
from core.dynamodb_service import (
    EmployeesTable, ReportingHierarchyTable, LeaveRequestsTable, 
    ExpensesTable, AttendanceTable, HolidaysTable, PoliciesTable, 
    ResignationsTable, NotificationsTable, WFHRequestsTable,
    UsersTable, LoginHistoryTable, PayrollApprovalsTable, OKRsTable,
    AppraisalCyclesTable, AppraisalsTable, PolicyAcknowledgementsTable
)
from core.utils import send_notification, refresh_monthly_leaves, get_initial_leave_balance, safe_float, get_local_date, get_local_now

class HRDashboardView(FeatureRequiredMixin, HRRequiredMixin, TemplateView):
    required_feature = 'ess_portal'
    template_name = 'core/hr_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today_date = get_local_date()
        today = today_date.strftime('%Y-%m-%d')
        
        # 1. Stats
        all_employees = EmployeesTable.scan()
        # Filter for active employees only (Not Resigned OR Accepted Resignation but today <= LWD) AND Account is Active
        active_employees = []
        all_users = UsersTable.scan()
        for emp in all_employees:
            user = next((u for u in all_users if u.get('UserID') == emp.get('UserID')), None)
            is_user_active = user.get('IsActive', True) if user else True
            
            # Exclusion: Super admin should not count as an employee
            if user and user.get('Role') == 'Super admin':
                continue

            if not is_user_active:
                continue
                
            status = emp.get('OnboardingStatus')
            lwd_str = emp.get('LastWorkingDate')
            
            is_active_view = True
            if status in ['Resigned', 'Pending Review', 'Rejected', 'Pending']:
                is_active_view = False
            elif status == 'Accepted Resignation' and lwd_str:
                try:
                    lwd = datetime.datetime.strptime(lwd_str, '%Y-%m-%d').date()
                    if today_date > lwd:
                        is_active_view = False
                except:
                    pass
            
            if not is_active_view:
                continue
                
            active_employees.append(emp)
            
        context['total_employees'] = len(active_employees)
        
        attendance_today = AttendanceTable.scan(
            FilterExpression=Key('RecordDate').eq(today)
        )
        context['present_today'] = len(attendance_today)
        
        user_role = self.request.user.role
        user_emp_id = self.request.user.employee_id

        all_leaves = LeaveRequestsTable.scan()
        if user_role == 'Super admin':
            pending_leaves = [l for l in all_leaves if l.get('Status') == 'Pending' and l.get('ApproverID') == user_emp_id]
        else:
            pending_leaves = [l for l in all_leaves if l.get('Status') == 'Pending' and (l.get('ApproverID') == user_emp_id or l.get('ApproverRole') in ['HR ADMIN', 'Super admin'])]
        context['pending_leave_count'] = len(pending_leaves)
        
        all_resignations = ResignationsTable.scan()
        if user_role == 'Super admin':
            pending_resignations = [r for r in all_resignations if r.get('Status') == 'Pending HR ADMIN Review' and r.get('ApproverID') == user_emp_id]
        else:
            pending_resignations = [r for r in all_resignations if r.get('Status') == 'Pending HR ADMIN Review']
        context['pending_resignation_count'] = len(pending_resignations)
        
        all_expenses = ExpensesTable.scan()
        if user_role == 'Super admin':
            pending_expenses = [e for e in all_expenses if e.get('Status') == 'Pending Manager Approval' and e.get('ApproverID') == user_emp_id]
        else:
            # HR sees Manager Approved OR items where they are the direct approver
            pending_expenses = [e for e in all_expenses if e.get('Status') in ['Manager Approved', 'Pending HR ADMIN Approval'] or (e.get('Status') == 'Pending Manager Approval' and e.get('ApproverID') == user_emp_id)]
        context['pending_expense_count'] = len(pending_expenses)
        
        all_wfh = WFHRequestsTable.scan()
        if user_role == 'Super admin':
            pending_wfh = [w for w in all_wfh if w.get('Status') == 'Pending Manager Approval' and w.get('ApproverID') == user_emp_id]
        else:
            pending_wfh = [w for w in all_wfh if w.get('Status') == 'Pending HR ADMIN Approval' or (w.get('Status') == 'Pending Manager Approval' and w.get('ApproverID') == user_emp_id)]
        context['pending_wfh_count'] = len(pending_wfh)

        # 2. Pending Approvals List (Combine Payroll, Leaves, Resignations, Expenses, and WFH)
        approvals = []
        
        # 0. Payroll (Critical Priority)
        try:
            if user_role == 'Super admin':
                payroll_queue = [p for p in PayrollApprovalsTable.scan() if p.get('Status', '').startswith('Pending')]
            else:
                payroll_queue = [p for p in PayrollApprovalsTable.scan() if p.get('Status', '').startswith('Pending') and p.get('ApproverID') == user_emp_id]
            for p in payroll_queue:
                approvals.append({
                    'title': 'Payroll Batch',
                    'subtitle': f"{p.get('MonthYear')} Authorization Required",
                    'badge': 'Payroll',
                    'url': 'payroll_approval_list'
                })
        except: pass

        for l in pending_leaves[:2]:
            emp = next((e for e in all_employees if e.get('EmployeeID') == l.get('EmployeeID')), None)
            approvals.append({
                'title': f"{l.get('Type')} Leave",
                'subtitle': f"{emp.get('FirstName', '')} {emp.get('LastName', '')} - {emp.get('Department', '')}" if emp else l.get('EmployeeID'),
                'badge': 'Leave',
                'url': 'leave_approvals'
            })
            
        for r in pending_resignations[:2]:
            emp = next((e for e in all_employees if e.get('EmployeeID') == r.get('EmployeeID')), None)
            approvals.append({
                'title': 'Resignation',
                'subtitle': f"{emp.get('FirstName', '')} {emp.get('LastName', '')} - {emp.get('Department', '')}" if emp else r.get('EmployeeID'),
                'badge': 'Review',
                'url': 'resignation_approvals'
            })

        for e in pending_expenses[:2]:
            emp = next((emp_ for emp_ in all_employees if emp_.get('EmployeeID') == e.get('EmployeeID')), None)
            approvals.append({
                'title': 'Expense Claim',
                'subtitle': f"{emp.get('FirstName', '')} {emp.get('LastName', '')} - ₹{e.get('Amount')}" if emp else e.get('EmployeeID'),
                'badge': 'Expense',
                'url': 'expense_approvals'
            })

        for w in pending_wfh[:2]:
            emp = next((e_ for e_ in all_employees if e_.get('EmployeeID') == w.get('EmployeeID')), None)
            approvals.append({
                'title': 'WFH Request',
                'subtitle': f"{emp.get('FirstName', '')} {emp.get('LastName', '')} - {w.get('WFHDate')}" if emp else w.get('EmployeeID'),
                'badge': 'WFH',
                'url': 'wfh_approvals'
            })
        
        context['pending_approvals'] = approvals[:6] # Show up to 6 critical items
        
        # 3. Department Data for Chart
        dept_counts = {}
        for e in active_employees:
            dept = e.get('Department')
            if not dept or dept == 'None':
                dept = 'Other'
            dept_counts[dept] = dept_counts.get(dept, 0) + 1
            
        context['dept_labels'] = list(dept_counts.keys())
        context['dept_values'] = list(dept_counts.values())
        
        # 4. Leave Types Distribution
        leave_counts = {}
        for l in all_leaves:
            if l.get('Status') == 'Approved':
                ltype = l.get('Type', 'Other')
                leave_counts[ltype] = leave_counts.get(ltype, 0) + float(l.get('DaysCount', 1.0))
        context['leave_labels'] = list(leave_counts.keys())
        context['leave_values'] = list(leave_counts.values())

        # 5. Department-wise Monthly Payroll Distribution
        dept_payroll = {}
        user_permissions = getattr(self.request.user, 'permissions', [])
        if 'payroll_access' in user_permissions:
            for e in active_employees:
                dept = e.get('Department')
                if not dept or dept == 'None':
                    dept = 'Other'
                try:
                    monthly_sal = safe_float(e.get('SalaryPA', 0)) / 12.0
                except:
                    monthly_sal = 0.0
                dept_payroll[dept] = dept_payroll.get(dept, 0.0) + monthly_sal
        context['payroll_labels'] = list(dept_payroll.keys())
        context['payroll_values'] = [round(val, 2) for val in dept_payroll.values()]

        # 6. Last 7 Days Attendance Trend
        import datetime
        seven_days_ago = (today_date - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        recent_attendance = AttendanceTable.scan(
            FilterExpression=Key('RecordDate').gte(seven_days_ago)
        )
        attendance_by_date = {}
        for record in recent_attendance:
            rdate = record.get('RecordDate')
            attendance_by_date[rdate] = attendance_by_date.get(rdate, 0) + 1

        dates_range = [(today_date - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
        attendance_labels = [dt.strftime('%a (%b %d)') for dt in dates_range]
        attendance_values = [attendance_by_date.get(dt.strftime('%Y-%m-%d'), 0) for dt in dates_range]
        
        context['attendance_labels'] = attendance_labels
        context['attendance_values'] = attendance_values
        
        return context

class SuperAdminDashboardView(HRDashboardView):
    required_feature = 'ess_portal'
    template_name = 'core/super_admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_employees = EmployeesTable.scan()
        today = datetime.date.today()
        
        # 1. Total Monthly Payroll Projection
        total_payroll = 0
        for emp in all_employees:
            try:
                # Field is SalaryPA (Annual), divide by 12 for monthly
                total_payroll += safe_float(emp.get('SalaryPA')) / 12
            except (ValueError, TypeError):
                pass
        context['total_monthly_salary'] = total_payroll
        
        # 2. Logins Today
        today_str = today.strftime('%Y-%m-%d')
        logins = LoginHistoryTable.scan()
        # Field is LoginTime, not Timestamp
        context['logins_today'] = len([l for l in logins if l.get('LoginTime', '').startswith(today_str)])
        
        # 3. Dept Avg
        if context.get('dept_values'):
            context['avg_per_dept'] = round(sum(context['dept_values']) / len(context['dept_values']), 1)
        else:
            context['avg_per_dept'] = 0

        # 4. Inject Payroll into Pending Approvals
        payroll_requests = PayrollApprovalsTable.scan()
        pending_batches = [r for r in payroll_requests if r.get('Status', '').startswith('Pending')]
        
        pending_list = context.get('pending_approvals', [])
        for r in pending_batches:
            # Check if this batch is already in the list to avoid duplicates if HRDashboardView already added it
            if not any(item.get('title') == f"Payroll Batch: {r.get('Month')} {r.get('Year')}" for item in pending_list):
                pending_list.insert(0, {
                    'title': f"Payroll Batch: {r.get('MonthYear')}",
                    'subtitle': f"Net Disbursement: ₹{float(r.get('TotalNetPay', 0)):,.2f}",
                    'badge': 'Payroll',
                    'url': 'payroll_approval_list'
                })
        # 5. Inject Policies pending approval
        try:
            pending_policies = [p for p in PoliciesTable.scan() if p.get('ApprovalStatus') == 'Pending Approval']
            for p in pending_policies:
                pending_list.insert(0, {
                    'title': p.get('Title', 'Corporate Policy'),
                    'subtitle': f"Version {p.get('Version')} - Approval Required",
                    'badge': 'Policy',
                    'url': 'policies'
                })
        except Exception as e:
            print(f"Error loading pending policies for dashboard: {e}")

        context['pending_approvals'] = pending_list
        
        return context

class ManagerDashboardView(FeatureRequiredMixin, ManagerRequiredMixin, TemplateView):
    required_feature = 'ess_portal'
    template_name = 'core/manager_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # --- Fetch Team Members ---
        team_members = []
        try:
            reporting_lines = ReportingHierarchyTable.query(
                KeyConditionExpression=Key('ManagerID').eq(user.employee_id)
            )
            for line in reporting_lines:
                emp = EmployeesTable.get_item({'EmployeeID': line.get('EmployeeID')})
                if emp:
                    # Check if active
                    status = emp.get('OnboardingStatus')
                    lwd_str = emp.get('LastWorkingDate')
                    
                    user_rec = UsersTable.scan(FilterExpression="EmployeeID = :eid", ExpressionAttributeValues={":eid": emp['EmployeeID']})
                    is_active = user_rec[0].get('IsActive', True) if user_rec else True
                    
                    if not is_active: continue
                    if status in ['Resigned', 'Pending Review', 'Rejected', 'Pending']: continue
                    if status == 'Accepted Resignation' and lwd_str:
                        try:
                            lwd = datetime.datetime.strptime(lwd_str, '%Y-%m-%d').date()
                            if datetime.date.today() > lwd: continue
                        except: pass
                        
                    team_members.append(emp)
        except Exception:
            pass

        # Ensure the logged-in user is always included in the team list
        if not any(emp.get('EmployeeID') == user.employee_id for emp in team_members):
            self_emp = EmployeesTable.get_item({'EmployeeID': user.employee_id})
            if self_emp:
                team_members.append(self_emp)

        context['team_members'] = team_members

        # --- Fetch Pending Leave Requests (for manager approval) ---
        pending_leaves = []
        try:
            all_leaves = LeaveRequestsTable.scan()
            pending_leaves = [l for l in all_leaves if l.get('Status') == 'Pending' and l.get('ApproverID') == user.employee_id]
            pending_leaves.sort(key=lambda x: x.get('LeaveDate', ''), reverse=True)
        except Exception:
            pass
        context['pending_leaves'] = pending_leaves[:10] # Show 10 most recent on dashboard

        # --- Fetch Pending Expense Claims ---
        pending_expenses = []
        try:
            all_expenses = ExpensesTable.scan()
            # Managers see claims pending manager approval where they are the approver
            pending_expenses = [e for e in all_expenses if e.get('Status') == 'Pending Manager Approval' and e.get('ApproverID') == user.employee_id]
            pending_expenses.sort(key=lambda x: x.get('Date', ''), reverse=True)
        except Exception:
            pass
        context['pending_expenses'] = pending_expenses[:10]

        # --- Fetch Pending WFH Requests ---
        pending_wfh = []
        try:
            all_wfh = WFHRequestsTable.scan()
            pending_wfh = [w for w in all_wfh if w.get('Status') == 'Pending Manager Approval' and w.get('ApproverID') == user.employee_id]
            pending_wfh.sort(key=lambda x: x.get('WFHDate', ''), reverse=True)
        except Exception:
            pass
        context['pending_wfh'] = pending_wfh[:10]

        # --- Stats ---
        context['team_size'] = len(team_members)
        context['pending_leave_count'] = len(pending_leaves)
        context['pending_expense_count'] = len(pending_expenses)
        context['pending_wfh_count'] = len(pending_wfh)

        from django.core.paginator import Paginator
        paginator = Paginator(team_members, 10)
        page = self.request.GET.get('page')
        context['team_members'] = paginator.get_page(page)

        return context

class EmployeeDashboardView(FeatureRequiredMixin, LoginRequiredMixin, ApprovedOnboardingMixin, TemplateView):
    required_feature = 'ess_portal'
    template_name = 'core/employee_dashboard.html'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = get_local_date().isoformat()
        
        # Fetch today's attendance
        today_record = None
        employee = None
        try:
            today_record = AttendanceTable.get_item({'EmployeeID': user.employee_id, 'RecordDate': today})
            employee = EmployeesTable.get_item({'EmployeeID': user.employee_id})
        except Exception:
            pass
            
        # Fetch This Month's Holidays
        upcoming_holidays = []
        try:
            holidays = HolidaysTable.scan()
            current_month = today[:7] # YYYY-MM
            upcoming_holidays = sorted([h for h in holidays if h.get('HolidayDate', '').startswith(current_month)], key=lambda x: x.get('HolidayDate'))
        except Exception:
            pass

        # Fetch Recent Leave Requests
        recent_leaves = []
        try:
            leaves = LeaveRequestsTable.query(KeyConditionExpression=Key('EmployeeID').eq(user.employee_id))
            recent_leaves = sorted(leaves, key=lambda x: x.get('LeaveDate', ''), reverse=True)[:1]
        except Exception:
            pass
            
        context['today_record'] = today_record
        context['upcoming_holidays'] = upcoming_holidays
        context['recent_leaves'] = recent_leaves
        
        # Add balances
        if employee:
            # Trigger monthly refresh if needed (only on the 1st)
            refreshed = refresh_monthly_leaves(employee)
            if refreshed:
                # Re-fetch employee data to get updated balances
                employee = EmployeesTable.get_item({'EmployeeID': user.employee_id})

            # Fetch all leaves to calculate pending days
            existing_leaves = []
            try:
                existing_leaves = LeaveRequestsTable.query(KeyConditionExpression=Key('EmployeeID').eq(user.employee_id))
            except Exception:
                pass
            
            pending_pl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and ('Earned Leave' in l.get('Type', '') or 'Paid Leave' in l.get('Type', '')))
            pending_sl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and 'Sick Leave' in l.get('Type', ''))
            pending_cl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and 'Casual Leave' in l.get('Type', ''))

            # Spent calculations (Approved leaves)
            spent_pl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and ('Earned Leave' in l.get('Type', '') or 'Paid Leave' in l.get('Type', '')))
            spent_sl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and 'Sick Leave' in l.get('Type', ''))
            spent_cl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and 'Casual Leave' in l.get('Type', ''))
            spent_marriage = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and 'Marriage Leave' in l.get('Type', ''))
            spent_parental = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and ('Maternity' in l.get('Type', '') or 'Paternity' in l.get('Type', '')))
            spent_unpaid = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and 'Unpaid Leave' in l.get('Type', ''))

            gender = employee.get('Gender', 'Male')
            parental_type = 'Maternity Leave' if gender == 'Female' else 'Paternity Leave'

            context['balance_pl'] = float(employee.get('Balance_PL') or 0.0) - pending_pl
            context['balance_sl'] = float(employee.get('Balance_SL', get_initial_leave_balance(employee, 'SL'))) - pending_sl
            context['balance_cl'] = float(employee.get('Balance_CL', get_initial_leave_balance(employee, 'CL'))) - pending_cl
            context['spent_pl'] = spent_pl
            context['spent_sl'] = spent_sl
            context['spent_cl'] = spent_cl
            context['spent_marriage'] = spent_marriage
            context['spent_parental'] = spent_parental
            context['spent_unpaid'] = spent_unpaid
            context['parental_leave_type'] = parental_type
            context['is_intern'] = employee.get('EmploymentType') == 'Intern'
        else:
            context['balance_pl'] = 0.0
            context['balance_sl'] = 0.0
            context['balance_cl'] = 0.0
            context['is_intern'] = False
            
        return context

class ExportEmployeesCSVView(FeatureRequiredMixin, HRRequiredMixin, View):
    required_feature = 'employee_directory'
    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="employees.csv"'

        writer = csv.writer(response)
        writer.writerow(['EmployeeID', 'First Name', 'Last Name', 'Email', 'Department', 'Role', 'Employment Type', 'Status'])
        
        employees = EmployeesTable.scan()
        for e in employees:
            writer.writerow([
                e.get('EmployeeID', ''),
                e.get('FirstName', ''),
                e.get('LastName', ''),
                e.get('Email', ''),
                e.get('Department', ''),
                e.get('Designation', ''),
                e.get('EmploymentType', 'Permanent'),
                e.get('EmploymentStatus', 'Full Time')
            ])

        return response

class SettingsView(FeatureRequiredMixin, LoginRequiredMixin, TemplateView):
    required_feature = 'ess_portal'
    template_name = 'core/settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        try:
            from core.dynamodb_service import (
                EmployeesTable, ReportingHierarchyTable, LeaveRequestsTable, 
                ExpensesTable, AttendanceTable, HolidaysTable, PoliciesTable, 
                ResignationsTable, NotificationsTable, WFHRequestsTable, LoginHistoryTable, UsersTable, PayrollApprovalsTable
            )
            from boto3.dynamodb.conditions import Key
            
            # Login History (Sidebar - Last 5)
            sidebar_history = LoginHistoryTable.query(
                KeyConditionExpression=Key('UserID').eq(user.user_id),
                ScanIndexForward=False,
                Limit=5
            )
            context['login_history'] = sidebar_history
            
            # Full Login History (For Modal - Last 50)
            full_history = LoginHistoryTable.query(
                KeyConditionExpression=Key('UserID').eq(user.user_id),
                ScanIndexForward=False,
                Limit=50
            )
            context['full_login_history'] = full_history

            # Organization-level Biometric Settings for Super Admin
            if getattr(user, 'role', None) == 'Super admin' and getattr(user, 'org_id', None):
                from core.dynamodb_service import OrganizationsTable
                org = OrganizationsTable.get_item({'OrgID': user.org_id})
                if org:
                    all_users = UsersTable.scan(
                        FilterExpression="OrgID = :oid",
                        ExpressionAttributeValues={":oid": user.org_id}
                    )
                    context['org_users'] = sorted(all_users, key=lambda u: u.get('Email', ''))
                    context['org'] = org

                    context['biometric_settings'] = {
                        'Enabled': org.get('BiometricEnabled', False),
                        'APIURL': org.get('BiometricAPIURL', ''),
                        'APIKey': org.get('BiometricAPIKey', ''),
                        'DeviceID': org.get('BiometricDeviceID', ''),
                    }
                    context['bank_settings'] = {
                        'Enabled': org.get('BankAPIEnabled', False),
                        'APIURL': org.get('BankAPIURL', ''),
                        'ClientID': org.get('BankClientID', ''),
                        'APIKey': org.get('BankAPIKey', ''),
                    }
                    
                    # Leave Policies (with defaults)
                    leave_policies = org.get('LeavePolicies', {})
                    from core.utils import DEFAULT_LEAVE_POLICIES
                    for emp_type in ['Permanent', 'Probation', 'Intern']:
                        if emp_type not in leave_policies:
                            leave_policies[emp_type] = DEFAULT_LEAVE_POLICIES[emp_type]
                    context['leave_policies'] = leave_policies
                    
                    # Tax and PF Settings
                    context['tax_pf_settings'] = {
                        'PFEnabled': org.get('PFEnabled', True),
                        'EmployeePFPercent': org.get('EmployeePFPercent', 12.0),
                        'EmployerPFPercent': org.get('EmployerPFPercent', 12.0),
                        'TDSEnabled': org.get('TDSEnabled', True),
                        'TaxRegime': org.get('TaxRegime', 'New Regime'),
                        'TaxStandardDeduction': org.get('TaxStandardDeduction', 75000.0)
                    }

        except Exception as e:
            print(f"Error in Settings context: {e}")
            context['login_history'] = []
        return context

    def post(self, request):
        user = request.user
        action = request.POST.get('action')

        if action == 'update_biometric' and getattr(user, 'role', None) == 'Super admin':
            enabled = request.POST.get('biometric_enabled') == 'on'
            api_url = request.POST.get('biometric_api_url', '').strip()
            api_key = request.POST.get('biometric_api_key', '').strip()
            device_id = request.POST.get('biometric_device_id', '').strip()

            from core.dynamodb_service import OrganizationsTable
            try:
                org = OrganizationsTable.get_item({'OrgID': user.org_id})
                if org:
                    org['BiometricEnabled'] = enabled
                    org['BiometricAPIURL'] = api_url
                    org['BiometricAPIKey'] = api_key
                    org['BiometricDeviceID'] = device_id
                    OrganizationsTable.put_item(org)
                    messages.success(request, "Biometric API settings updated successfully.")
                else:
                    messages.error(request, "Organization not found.")
            except Exception as e:
                messages.error(request, f"Error saving biometric settings: {str(e)}")
            return redirect('settings')

        if action == 'update_bank' and getattr(user, 'role', None) == 'Super admin':
            enabled = request.POST.get('bank_enabled') == 'on'
            api_url = request.POST.get('bank_api_url', '').strip()
            client_id = request.POST.get('bank_client_id', '').strip()
            api_key = request.POST.get('bank_api_key', '').strip()

            from core.dynamodb_service import OrganizationsTable
            try:
                org = OrganizationsTable.get_item({'OrgID': user.org_id})
                if org:
                    org['BankAPIEnabled'] = enabled
                    org['BankAPIURL'] = api_url
                    org['BankClientID'] = client_id
                    org['BankAPIKey'] = api_key
                    OrganizationsTable.put_item(org)
                    messages.success(request, "Bank API settings updated successfully.")
                else:
                    messages.error(request, "Organization not found.")
            except Exception as e:
                messages.error(request, f"Error saving bank API settings: {str(e)}")
        if action == 'update_leave_policies' and getattr(user, 'role', None) == 'Super admin':
            from core.dynamodb_service import OrganizationsTable
            try:
                org = OrganizationsTable.get_item({'OrgID': user.org_id})
                if org:
                    leave_policies = {}
                    for emp_type in ['Permanent', 'Probation', 'Intern']:
                        sl_limit = Decimal(request.POST.get(f'{emp_type}_SL_Limit', '0.0') or '0.0')
                        cl_limit = Decimal(request.POST.get(f'{emp_type}_CL_Limit', '0.0') or '0.0')
                        pl_limit = Decimal(request.POST.get(f'{emp_type}_PL_Limit', '0.0') or '0.0')
                        allowed_types = request.POST.getlist(f'{emp_type}_AllowedTypes')
                        leave_policies[emp_type] = {
                            'SL_Limit': sl_limit,
                            'CL_Limit': cl_limit,
                            'PL_Limit': pl_limit,
                            'AllowedTypes': allowed_types
                        }
                    org['LeavePolicies'] = leave_policies
                    OrganizationsTable.put_item(org)
                    messages.success(request, "Leave policies updated successfully.")
                else:
                    messages.error(request, "Organization not found.")
            except Exception as e:
                messages.error(request, f"Error saving leave policies: {str(e)}")
            return redirect('settings')

        if action == 'update_tax_pf' and getattr(user, 'role', None) == 'Super admin':
            from core.dynamodb_service import OrganizationsTable
            try:
                org = OrganizationsTable.get_item({'OrgID': user.org_id})
                if org:
                    org['PFEnabled'] = request.POST.get('pf_enabled') == 'on'
                    org['EmployeePFPercent'] = Decimal(request.POST.get('employee_pf_percent', '12.0') or '12.0')
                    org['EmployerPFPercent'] = Decimal(request.POST.get('employer_pf_percent', '12.0') or '12.0')
                    org['TDSEnabled'] = request.POST.get('tds_enabled') == 'on'
                    org['TaxRegime'] = request.POST.get('tax_regime', 'New Regime')
                    org['TaxStandardDeduction'] = Decimal(request.POST.get('tax_standard_deduction', '75000.0') or '75000.0')
                    OrganizationsTable.put_item(org)
                    messages.success(request, "Tax & PF settings updated successfully.")
                else:
                    messages.error(request, "Organization not found.")
            except Exception as e:
                messages.error(request, f"Error saving Tax & PF settings: {str(e)}")
            return redirect('settings')

        if action == 'update_payroll_manager' and getattr(user, 'role', None) == 'Super admin':
            payroll_manager_user_id = request.POST.get('payroll_manager_user_id', '').strip()
            pf_manager_user_id = request.POST.get('pf_manager_user_id', '').strip()
            historical_payroll_manager_user_id = request.POST.get('historical_payroll_manager_user_id', '').strip()
            from core.dynamodb_service import OrganizationsTable
            try:
                org = OrganizationsTable.get_item({'OrgID': user.org_id})
                if org:
                    org['PayrollManagerUserID'] = payroll_manager_user_id or None
                    org['PFManagerUserID'] = pf_manager_user_id or None
                    org['HistoricalPayrollManagerUserID'] = historical_payroll_manager_user_id or None
                    OrganizationsTable.put_item(org)
                    messages.success(request, "Designated Payroll/PF/Historical Access updated successfully.")
                else:
                    messages.error(request, "Organization not found.")
            except Exception as e:
                messages.error(request, f"Error saving payroll/PF/historical access settings: {str(e)}")
            return redirect('settings')
        
        # Basic Profile Update & Security Settings
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        passport_photo = request.FILES.get('passport_photo')
        
        current_password = request.POST.get('current_password', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        
        from core.dynamodb_service import UsersTable, EmployeesTable
        from django.core.files.storage import FileSystemStorage
        import os
        import re
        from django.contrib.auth.hashers import check_password, make_password
        import bcrypt

        # 1. Update User Record
        user_record = UsersTable.get_item({'UserID': user.user_id})
        if not user_record:
            messages.error(request, "User not found.")
            return redirect('settings')

        # Handle password change if requested
        password_changed = False
        if current_password or new_password or confirm_password:
            if not current_password:
                messages.error(request, "Current password is required to change password.")
                return redirect('settings')
            if not new_password:
                messages.error(request, "New password is required.")
                return redirect('settings')
            if new_password != confirm_password:
                messages.error(request, "New password and confirm password do not match.")
                return redirect('settings')

            # Password Strength Validation
            password_regex = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$'
            if not re.match(password_regex, new_password):
                messages.error(request, "Password is too weak. It must be at least 8 characters long and include uppercase letters, lowercase letters, numbers, and special characters.")
                return redirect('settings')

            # Verify current password
            hashed = user_record.get('PasswordHash', '')
            if not hashed:
                hashed = user_record.get('Password', '') # fallback for test users

            is_valid = False
            if check_password(current_password, hashed):
                is_valid = True
            else:
                try:
                    if bcrypt.checkpw(current_password.encode('utf-8')[:72], hashed.encode('utf-8')):
                        is_valid = True
                except Exception:
                    pass

            if not is_valid:
                messages.error(request, "Incorrect current password.")
                return redirect('settings')

            # Hash and set new password
            user_record['PasswordHash'] = make_password(new_password)
            # Remove legacy plaintext password field if it exists to be secure
            if 'Password' in user_record:
                del user_record['Password']
            password_changed = True

        user_record['FirstName'] = first_name
        user_record['LastName'] = last_name
        
        if passport_photo:
            fs = FileSystemStorage()
            filename = fs.save(f"profiles/{user.user_id}_{passport_photo.name}", passport_photo)
            user_record['PassportPhoto'] = filename
            
        UsersTable.put_item(user_record)
            
        # 2. Update Employee Record if exists
        if user.employee_id:
            emp_record = EmployeesTable.get_item({'EmployeeID': user.employee_id})
            if emp_record:
                emp_record['FirstName'] = first_name
                emp_record['LastName'] = last_name
                if passport_photo:
                    emp_record['PassportPhoto'] = user_record['PassportPhoto']
                EmployeesTable.put_item(emp_record)
                
        if password_changed:
            messages.success(request, "Account settings and password updated successfully.")
        else:
            messages.success(request, "Account settings updated successfully.")
        return redirect('settings')

class NotificationsView(FeatureRequiredMixin, LoginRequiredMixin, TemplateView):
    required_feature = 'ess_portal'
    template_name = 'core/notifications.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_emp_id = self.request.user.employee_id
        
        try:
            # 1. Start with dynamic birthday notifications
            today_str = datetime.date.today().strftime('%m-%d')
            all_employees = EmployeesTable.scan()
            
            final_notifications = []
            
            # Check if user has cleared notifications in this session
            notifications_dismissed = self.request.session.get('notifications_dismissed', False)
            
            if not notifications_dismissed:
                for emp in all_employees:
                    dob = emp.get('DOB')
                    if dob and len(dob) >= 10 and dob[5:10] == today_str:
                        final_notifications.append({
                            'Title': 'Birthday Celebration!',
                            'Message': f"Today is {emp.get('FirstName')}'s birthday! 🎉",
                            'Timestamp': 'Today',
                            'Icon': 'fa-cake-candles',
                            'Color': 'danger',
                            'IsRead': True
                        })

            # 2. Add real notifications from DB with limit
            table = NotificationsTable._get_table()
            response = table.query(
                KeyConditionExpression=Key('EmployeeID').eq(user_emp_id),
                ScanIndexForward=False,
                Limit=5
            )
            db_notifications = response.get('Items', [])
            final_notifications.extend(db_notifications)
            context['notifications'] = final_notifications
            
            # For "Load More" logic
            if 'LastEvaluatedKey' in response:
                context['last_timestamp'] = response['LastEvaluatedKey']['Timestamp']
            
            # Mark DB notifications as read
            for n in db_notifications:
                if not n.get('IsRead'):
                    NotificationsTable.update_item(
                        Key={'EmployeeID': user_emp_id, 'Timestamp': n['Timestamp']},
                        UpdateExpression="SET IsRead = :val",
                        ExpressionAttributeValues={':val': True}
                    )
        except Exception as e:
            print(f"Error fetching notifications: {e}")
            context['notifications'] = []
            
        return context

class DeleteNotificationView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'ess_portal'
    def get(self, request, timestamp):
        user_emp_id = request.user.employee_id
        if timestamp == 'Today':
            # Handle birthday notifications by dismissing them for session
            request.session['notifications_dismissed'] = True
        else:
            try:
                NotificationsTable.delete_item({
                    'EmployeeID': user_emp_id,
                    'Timestamp': timestamp
                })
                messages.success(request, "Notification deleted.")
            except Exception as e:
                messages.error(request, f"Error deleting notification: {e}")
        return redirect('notifications')

class NotificationDetailView(FeatureRequiredMixin, LoginRequiredMixin, TemplateView):
    required_feature = 'ess_portal'
    template_name = 'core/notification_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        timestamp = self.kwargs.get('timestamp')
        user_emp_id = self.request.user.employee_id
        
        if timestamp == 'Today':
            context['notification'] = {
                'Title': 'Birthday Celebration!',
                'Message': 'Multiple birthdays today!', # Simplified
                'Timestamp': 'Today',
                'Icon': 'fa-cake-candles',
                'Color': 'danger'
            }
        else:
            notification = NotificationsTable.get_item({
                'EmployeeID': user_emp_id,
                'Timestamp': timestamp
            })
            context['notification'] = notification
        return context

class LoadMoreNotificationsView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'ess_portal'
    def get(self, request):
        user_emp_id = request.user.employee_id
        last_timestamp = request.GET.get('last_timestamp')
        
        try:
            table = NotificationsTable._get_table()
            query_kwargs = {
                'KeyConditionExpression': Key('EmployeeID').eq(user_emp_id),
                'ScanIndexForward': False,
                'Limit': 5
            }
            if last_timestamp:
                query_kwargs['ExclusiveStartKey'] = {
                    'EmployeeID': user_emp_id,
                    'Timestamp': last_timestamp
                }
            
            response = table.query(**query_kwargs)
            items = response.get('Items', [])
            
            # Mark these as read
            for n in items:
                if not n.get('IsRead'):
                    NotificationsTable.update_item(
                        Key={'EmployeeID': user_emp_id, 'Timestamp': n['Timestamp']},
                        UpdateExpression="SET IsRead = :val",
                        ExpressionAttributeValues={':val': True}
                    )

            data = {
                'notifications': items,
                'last_timestamp': response.get('LastEvaluatedKey', {}).get('Timestamp')
            }
            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

class NotificationPollView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'ess_portal'
    def get(self, request):
        user_emp_id = request.user.employee_id
        if not user_emp_id:
            return JsonResponse({'unread_count': 0, 'notifications': []})
        try:
            try:
                all_unread = NotificationsTable.query(
                    KeyConditionExpression=Key('EmployeeID').eq(user_emp_id),
                    FilterExpression="#r = :val",
                    ExpressionAttributeNames={'#r': 'IsRead'},
                    ExpressionAttributeValues={':val': False}
                )
                unread_count = len(all_unread)
            except Exception:
                unread_count = 0

            notifications = NotificationsTable.query(
                KeyConditionExpression=Key('EmployeeID').eq(user_emp_id),
                ScanIndexForward=False,
                Limit=10,
                ConsistentRead=True
            )
            new_notifications = []
            for n in notifications:
                new_notifications.append({
                    'title': n.get('Title', ''),
                    'message': n.get('Message', ''),
                    'timestamp': n.get('Timestamp', ''),
                    'is_read': n.get('IsRead', False),
                    'icon': n.get('Icon', 'fa-bell'),
                    'color': n.get('Color', 'primary')
                })
            return JsonResponse({
                'unread_count': unread_count,
                'notifications': new_notifications
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

import json

class PoliciesView(FeatureRequiredMixin, LoginRequiredMixin, TemplateView):
    required_feature = 'ess_portal'
    template_name = 'core/policies.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        role = getattr(user, 'role', '')
        emp_id = getattr(user, 'employee_id', None) or user.user_id
        
        try:
            all_policies = PoliciesTable.scan(
                FilterExpression="OrgID = :oid",
                ExpressionAttributeValues={':oid': user.org_id}
            )
            visible_policies = []
            
            # Fetch acknowledgments for this organization
            try:
                org_acks = PolicyAcknowledgementsTable.scan(
                    FilterExpression="OrgID = :oid",
                    ExpressionAttributeValues={':oid': user.org_id}
                )
            except Exception:
                org_acks = []
                
            # Map acknowledgments by PolicyID -> EmployeeID -> AcknowledgedAt
            acks_by_policy = {}
            for ack in org_acks:
                pid = ack.get('PolicyID')
                eid = ack.get('EmployeeID')
                if pid not in acks_by_policy:
                    acks_by_policy[pid] = {}
                acks_by_policy[pid][eid] = ack.get('AcknowledgedAt')

            # Fetch active employees for the organization to generate HR / Super Admin Reports
            active_employees = []
            if role in ['HR ADMIN', 'Super admin']:
                try:
                    all_org_emps = EmployeesTable.scan(
                        FilterExpression="OrgID = :oid",
                        ExpressionAttributeValues={':oid': user.org_id}
                    )
                    all_users = UsersTable.scan()
                    user_map = {u.get('UserID'): u for u in all_users if u.get('UserID')}
                    
                    today_date = get_local_date()
                    for emp in all_org_emps:
                        uid = emp.get('UserID')
                        usr = user_map.get(uid) if uid else None
                        
                        is_user_active = usr.get('IsActive', True) if usr else True
                        if not is_user_active:
                            continue
                            
                        # Exclude Admins (Super Admin, Platform Admin, HR Admin) from needing to acknowledge
                        user_role = (usr.get('Role') or '').strip().upper() if usr else 'EMPLOYEE'
                        if user_role in ['SUPER ADMIN', 'SUPERADMIN', 'PLATFORM ADMIN', 'PLATFORM SUPER ADMIN']:
                            continue
                            
                        status = emp.get('OnboardingStatus')
                        if status in ['Resigned', 'Pending Review', 'Rejected', 'Pending']:
                            continue
                            
                        lwd_str = emp.get('LastWorkingDate')
                        is_active_view = True
                        if status == 'Accepted Resignation' and lwd_str:
                            try:
                                lwd = datetime.datetime.strptime(lwd_str, '%Y-%m-%d').date()
                                if today_date > lwd:
                                    is_active_view = False
                            except:
                                pass
                        
                        if is_active_view:
                            active_employees.append(emp)
                except Exception as e:
                    print(f"Error fetching active employees for report: {e}")

            for p in all_policies:
                pid = p['PolicyID']
                status = p.get('ApprovalStatus', 'Approved')
                
                # Role-based visibility logic
                is_visible = False
                if role in ['Super admin', 'HR ADMIN']:
                    is_visible = True
                elif status == 'Approved':
                    is_visible = True
                    
                if is_visible:
                    p['ApprovalStatus'] = status
                    p['Version'] = p.get('Version', '1.0')
                    p['VersionDate'] = p.get('VersionDate', '')
                    
                    # Check current user's acknowledgment status
                    user_acks = acks_by_policy.get(pid, {})
                    p['user_acknowledged'] = emp_id in user_acks
                    p['acknowledged_at'] = user_acks.get(emp_id)
                    
                    if role in ['HR ADMIN', 'Super admin']:
                        acknowledged_list = []
                        pending_list = []
                        
                        for emp in active_employees:
                            emp_eid = emp.get('EmployeeID')
                            emp_name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}".strip() or emp.get('Email', '')
                            
                            if emp_eid in user_acks:
                                acknowledged_list.append({
                                    'name': emp_name,
                                    'date': user_acks[emp_eid]
                                })
                            else:
                                pending_list.append({
                                    'name': emp_name
                                })
                                
                        p['ack_report'] = {
                            'acknowledged': acknowledged_list,
                            'pending': pending_list,
                            'ack_count': len(acknowledged_list),
                            'total_count': len(active_employees),
                            'ack_percentage': round((len(acknowledged_list) / len(active_employees) * 100), 1) if active_employees else 0
                        }
                    visible_policies.append(p)
                    
            context['policies'] = visible_policies
            
            # Create a clean JSON version for JS layer
            js_data = {}
            for p in visible_policies:
                js_data[p['PolicyID']] = {
                    'title': p.get('Title', ''),
                    'description': p.get('Description', ''),
                    'content': p.get('Content', ''),
                    'gradient': p.get('Gradient', ''),
                    'icon': p.get('Icon', 'fa-file-lines'),
                    'color': p.get('Color', '#1a4f8b'),
                    'version': p.get('Version', '1.0'),
                    'version_date': p.get('VersionDate', ''),
                    'status': p.get('ApprovalStatus', 'Approved'),
                    'user_acknowledged': p.get('user_acknowledged', False),
                    'ack_report': p.get('ack_report', None),
                    'is_onboarding_policy': p.get('IsOnboardingPolicy', False)
                }
            context['policies_json'] = json.dumps(js_data)
        except Exception as e:
            print(f"Error loading Policies: {e}")
            context['policies'] = []
            context['policies_json'] = '{}'
            
        return context

class AddPolicyView(FeatureRequiredMixin, HRRequiredMixin, View):
    required_feature = 'employee_directory'
    def post(self, request):
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot add policies.")
            return redirect('policies')
        title = request.POST.get('title')
        description = request.POST.get('description')
        content = request.POST.get('content')
        icon = request.POST.get('icon', 'fa-file-lines')
        color = request.POST.get('color', '#1a4f8b')
        version = request.POST.get('version', '1.0').strip() or '1.0'
        version_date = request.POST.get('version_date', '').strip() or get_local_date().isoformat()
        is_onboarding_policy = request.POST.get('is_onboarding_policy') == 'on'
        
        policy_item = {
            'PolicyID': str(uuid.uuid4()),
            'OrgID': request.user.org_id,
            'Title': title,
            'Description': description,
            'Content': content,
            'Icon': icon,
            'Color': color,
            'Gradient': f"linear-gradient(135deg, {color}22 0%, {color}44 100%)",
            'Version': version,
            'VersionDate': version_date,
            'ApprovalStatus': 'Pending Approval',
            'CreatedAt': get_local_now().isoformat(),
            'IsOnboardingPolicy': is_onboarding_policy
        }
        
        try:
            PoliciesTable.put_item(policy_item)
            
            try:
                super_admins = [u for u in UsersTable.scan() if (u.get('Role') or '').strip().upper() in ['SUPER ADMIN', 'SUPERADMIN'] and u.get('OrgID') == request.user.org_id]
                for sa in super_admins:
                    sa_emp_id = sa.get('EmployeeID') or sa.get('UserID')
                    if sa_emp_id:
                        send_notification(
                            employee_id=sa_emp_id,
                            title="New Policy Pending Approval",
                            message=f"Policy '{title}' (Version {version}) has been submitted for approval.",
                            n_type='Policy',
                            icon='fa-file-contract',
                            color='warning',
                            org_id=request.user.org_id
                        )
            except Exception as e:
                print(f"Error sending Super Admin notification for policy: {e}")
                
            messages.success(request, f"Policy '{title}' created and sent to Super Admin for approval.")
        except Exception as e:
            messages.error(request, f"Error adding policy: {str(e)}")
            
        return redirect('policies')

class EditPolicyView(FeatureRequiredMixin, HRRequiredMixin, View):
    required_feature = 'employee_directory'
    def post(self, request, policy_id):
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot modify policies.")
            return redirect('policies')
        policy = PoliciesTable.get_item({'PolicyID': policy_id})
        if not policy:
            messages.error(request, "Policy not found or unauthorized access.")
            return redirect('policies')

        title = request.POST.get('title')
        description = request.POST.get('description')
        content = request.POST.get('content')
        icon = request.POST.get('icon', 'fa-file-lines')
        color = request.POST.get('color', '#1a4f8b')
        version = request.POST.get('version', '1.0').strip() or '1.0'
        version_date = request.POST.get('version_date', '').strip() or get_local_date().isoformat()
        is_onboarding_policy = request.POST.get('is_onboarding_policy') == 'on'
        
        try:
            PoliciesTable.update_item(
                Key={'PolicyID': policy_id},
                UpdateExpression="SET #t = :t, Description = :d, Content = :c, Icon = :i, Color = :co, Gradient = :g, Version = :v, VersionDate = :vd, ApprovalStatus = :s, IsOnboardingPolicy = :io",
                ExpressionAttributeNames={'#t': 'Title'},
                ExpressionAttributeValues={
                    ':t': title,
                    ':d': description,
                    ':c': content,
                    ':i': icon,
                    ':co': color,
                    ':g': f"linear-gradient(135deg, {color}22 0%, {color}44 100%)",
                    ':v': version,
                    ':vd': version_date,
                    ':s': 'Pending Approval',
                    ':io': is_onboarding_policy
                }
            )
            
            try:
                super_admins = [u for u in UsersTable.scan() if (u.get('Role') or '').strip().upper() in ['SUPER ADMIN', 'SUPERADMIN'] and u.get('OrgID') == request.user.org_id]
                for sa in super_admins:
                    sa_emp_id = sa.get('EmployeeID') or sa.get('UserID')
                    if sa_emp_id:
                        send_notification(
                            employee_id=sa_emp_id,
                            title="Policy Update Pending Approval",
                            message=f"Policy '{title}' (Version {version}) has been updated and requires approval.",
                            n_type='Policy',
                            icon='fa-file-contract',
                            color='warning',
                            org_id=request.user.org_id
                        )
            except Exception as e:
                print(f"Error sending Super Admin notification for policy update: {e}")
                
            messages.success(request, f"Policy '{title}' updated and sent to Super Admin for approval.")
        except Exception as e:
            messages.error(request, f"Error updating policy: {str(e)}")
            
        return redirect('policies')

class DeletePolicyView(FeatureRequiredMixin, HRRequiredMixin, View):
    required_feature = 'employee_directory'
    def post(self, request):
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot delete policies.")
            return redirect('policies')
        policy_id = request.POST.get('policy_id', '').strip()
        if not policy_id:
            messages.error(request, "Error: No Policy ID provided.")
            return redirect('policies')
        policy = PoliciesTable.get_item({'PolicyID': policy_id})
        if not policy:
            messages.error(request, "Policy not found or unauthorized access.")
            return redirect('policies')
            
        try:
            PoliciesTable.delete_item({'PolicyID': policy_id})
            messages.success(request, "Policy has been successfully deleted from the database.")
        except Exception as e:
            messages.error(request, f"Error during deletion: {str(e)}")
            
        return redirect('policies')

class ApprovePolicyView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'ess_portal'
    def post(self, request, policy_id):
        user = request.user
        role = getattr(user, 'role', '')
        if role not in ['Super admin', 'HR ADMIN']:
            messages.error(request, "Unauthorized to approve policies.")
            return redirect('policies')
            
        policy = PoliciesTable.get_item({'PolicyID': policy_id})
        if not policy:
            messages.error(request, "Policy not found or unauthorized access.")
            return redirect('policies')

        current_status = policy.get('ApprovalStatus', 'Pending Approval')
        title = policy.get('Title', 'New Policy')
        version = policy.get('Version', '1.0')

        try:
            if role == 'Super admin':
                if current_status != 'Pending Approval':
                    messages.error(request, f"This policy cannot be approved by Super Admin in its current state ({current_status}).")
                    return redirect('policies')
                
                # Super Admin Approval: Move to Pending HR Admin Approval
                PoliciesTable.update_item(
                    Key={'PolicyID': policy_id},
                    UpdateExpression="SET ApprovalStatus = :s",
                    ExpressionAttributeValues={':s': 'Pending HR Admin Approval'}
                )
                
                # Notify HR Admins
                try:
                    hr_admins = [u for u in UsersTable.scan() if (u.get('Role') or '').strip().upper() in ['HR ADMIN', 'HRADMIN', 'HR'] and u.get('OrgID') == user.org_id]
                    for hr in hr_admins:
                        hr_emp_id = hr.get('EmployeeID') or hr.get('UserID')
                        if hr_emp_id:
                            send_notification(
                                employee_id=hr_emp_id,
                                title="Policy Approved by Super Admin",
                                message=f"Policy '{title}' (Version {version}) has been approved by the Super Admin and requires your final validation/acceptance.",
                                n_type='Policy',
                                icon='fa-file-circle-check',
                                color='warning',
                                org_id=user.org_id
                            )
                except Exception as e:
                    print(f"Error sending Super Admin approval notification to HR Admin: {e}")
                
                messages.success(request, "Policy approved by Super Admin. Awaiting HR Admin validation.")

            elif role == 'HR ADMIN':
                if current_status != 'Pending HR Admin Approval':
                    messages.error(request, f"You can only validate policies that are approved by the Super Admin. Current status: {current_status}")
                    return redirect('policies')

                # HR Admin Validation: Move to Approved
                PoliciesTable.update_item(
                    Key={'PolicyID': policy_id},
                    UpdateExpression="SET ApprovalStatus = :s",
                    ExpressionAttributeValues={':s': 'Approved'}
                )

                # Fetch all active employees (excluding Super Admin, Platform Admin)
                employees = []
                try:
                    all_org_emps = EmployeesTable.scan(
                        FilterExpression="OrgID = :oid",
                        ExpressionAttributeValues={':oid': user.org_id}
                    )
                    all_users = UsersTable.scan()
                    user_map = {u.get('UserID'): u for u in all_users if u.get('UserID')}
                    
                    today_date = get_local_date()
                    for emp in all_org_emps:
                        uid = emp.get('UserID')
                        usr = user_map.get(uid) if uid else None
                        
                        is_user_active = usr.get('IsActive', True) if usr else True
                        if not is_user_active:
                            continue
                            
                        user_role = (usr.get('Role') or '').strip().upper() if usr else 'EMPLOYEE'
                        # HR Admins also need to acknowledge approved policies
                        if user_role in ['SUPER ADMIN', 'SUPERADMIN', 'PLATFORM ADMIN', 'PLATFORM SUPER ADMIN']:
                            continue
                            
                        status = emp.get('OnboardingStatus')
                        if status in ['Resigned', 'Pending Review', 'Rejected', 'Pending']:
                            continue
                            
                        lwd_str = emp.get('LastWorkingDate')
                        is_active_view = True
                        if status == 'Accepted Resignation' and lwd_str:
                            try:
                                lwd = datetime.datetime.strptime(lwd_str, '%Y-%m-%d').date()
                                if today_date > lwd:
                                    is_active_view = False
                            except:
                                pass
                        
                        if is_active_view:
                            employees.append(emp)
                except Exception as e:
                    print(f"Error fetching active employees for final approval notification: {e}")

                # Notify all employees (including HR Admin themselves if they are in the list)
                for emp in employees:
                    emp_id = emp.get('EmployeeID')
                    if emp_id:
                        send_notification(
                            employee_id=emp_id,
                            title="New Policy Acknowledgment Required",
                            message=f"Policy '{title}' (Version {version}) has been fully approved. Please review and acknowledge it.",
                            n_type='Policy',
                            icon='fa-file-signature',
                            color='info',
                            org_id=user.org_id
                        )
                messages.success(request, "Policy fully approved and published for all employees.")
        except Exception as e:
            messages.error(request, f"Error processing policy approval: {str(e)}")

        return redirect('policies')

class RejectPolicyView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'ess_portal'
    def post(self, request, policy_id):
        user = request.user
        role = getattr(user, 'role', '')
        if role not in ['Super admin', 'HR ADMIN']:
            messages.error(request, "Unauthorized to reject policies.")
            return redirect('policies')
            
        policy = PoliciesTable.get_item({'PolicyID': policy_id})
        if not policy:
            messages.error(request, "Policy not found or unauthorized access.")
            return redirect('policies')
            
        try:
            PoliciesTable.update_item(
                Key={'PolicyID': policy_id},
                UpdateExpression="SET ApprovalStatus = :s",
                ExpressionAttributeValues={':s': 'Rejected'}
            )
            
            # Send rejection notification to HR Admin who handles policies
            try:
                hr_admins = [u for u in UsersTable.scan() if (u.get('Role') or '').strip().upper() in ['HR ADMIN', 'HRADMIN', 'HR'] and u.get('OrgID') == user.org_id]
                for hr in hr_admins:
                    hr_emp_id = hr.get('EmployeeID') or hr.get('UserID')
                    if hr_emp_id:
                        send_notification(
                            employee_id=hr_emp_id,
                            title="Policy Rejected",
                            message=f"Policy '{policy.get('Title')}' (Version {policy.get('Version')}) has been rejected by {role}.",
                            n_type='Policy',
                            icon='fa-file-circle-xmark',
                            color='danger',
                            org_id=user.org_id
                        )
            except Exception as e:
                print(f"Error sending rejection notification: {e}")
                
            messages.success(request, f"Policy has been rejected by {role}.")
        except Exception as e:
            messages.error(request, f"Error rejecting policy: {str(e)}")
            
        return redirect('policies')

class AcknowledgePolicyView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'ess_portal'
    def post(self, request, policy_id):
        user = request.user
        emp_id = getattr(user, 'employee_id', None) or user.user_id
        emp_name = f"{user.first_name} {user.last_name}".strip() or user.email
        
        try:
            policy = PoliciesTable.get_item({'PolicyID': policy_id})
            if not policy or policy.get('ApprovalStatus', 'Approved') != 'Approved':
                messages.error(request, "Invalid policy or policy is not approved yet.")
                return redirect('policies')
                
            ack_item = {
                'PolicyID': policy_id,
                'EmployeeID': emp_id,
                'EmployeeName': emp_name,
                'OrgID': user.org_id,
                'AcknowledgedAt': get_local_now().isoformat()
            }
            PolicyAcknowledgementsTable.put_item(ack_item)
            messages.success(request, f"Thank you! Policy '{policy.get('Title')}' has been acknowledged.")
        except Exception as e:
            messages.error(request, f"Error acknowledging policy: {str(e)}")
            
        return redirect('policies')

class GlobalSearchView(FeatureRequiredMixin, LoginRequiredMixin, TemplateView):
    required_feature = 'ess_portal'
    template_name = 'core/search_results.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get('q', '').strip().lower()
        today_date = datetime.date.today()
        
        results = {
            'employees': [],
            'policies': [],
            'total_count': 0
        }

        if query:
            # 1. Search Employees
            all_employees = EmployeesTable.scan()
            all_users = UsersTable.scan()
            for emp in all_employees:
                user = next((u for u in all_users if u.get('UserID') == emp.get('UserID')), None)
                is_user_active = user.get('IsActive', True) if user else True
                
                if not is_user_active:
                    continue

                # Filter for active employees only (Not Resigned OR Accepted Resignation but today <= LWD)
                status = emp.get('OnboardingStatus')
                lwd_str = emp.get('LastWorkingDate')
                
                is_active_view = True
                if status in ['Resigned', 'Pending Review', 'Rejected', 'Pending']:
                    is_active_view = False
                elif status == 'Accepted Resignation' and lwd_str:
                    try:
                        lwd = datetime.datetime.strptime(lwd_str, '%Y-%m-%d').date()
                        if today_date > lwd:
                            is_active_view = False
                    except:
                        pass
                
                if not is_active_view:
                    continue

                first_name = emp.get('FirstName', '').lower()
                last_name = emp.get('LastName', '').lower()
                email = emp.get('Email', '').lower()
                dept = emp.get('Department', '').lower()
                type_ = emp.get('EmploymentType', '').lower()
                status_ = emp.get('EmploymentStatus', '').lower()
                emp_id = emp.get('EmployeeID', '').lower()
                
                if (query in first_name or query in last_name or 
                    query in email or query in dept or 
                    query in emp_id or
                    query in type_ or query in status_):
                    results['employees'].append(emp)

            # 2. Search Policies
            all_policies = PoliciesTable.scan()
            for p in all_policies:
                title = p.get('Title', '').lower()
                desc = p.get('Description', '').lower()
                
                if query in title or query in desc:
                    results['policies'].append(p)

            results['total_count'] = len(results['employees']) + len(results['policies'])

        context['search_results'] = results
        context['query'] = query
        return context

class ClearNotificationsView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'ess_portal'
    def post(self, request):
        user_emp_id = request.user.employee_id
        try:
            # Fetch all notifications for the user
            notifications = NotificationsTable.query(
                KeyConditionExpression=Key('EmployeeID').eq(user_emp_id)
            )
            # Delete each one
            for n in notifications:
                NotificationsTable.delete_item(
                    key={'EmployeeID': user_emp_id, 'Timestamp': n['Timestamp']}
                )
            # Set session flag to dismiss dynamic notifications (birthdays)
            request.session['notifications_dismissed'] = True
            messages.success(request, "All notifications cleared successfully.")
        except Exception as e:
            messages.error(request, f"Error clearing notifications: {e}")
            
        return redirect('notifications')

class MarkAllNotificationsReadView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'ess_portal'
    def post(self, request):
        user_emp_id = request.user.employee_id
        if not user_emp_id:
            return JsonResponse({'success': False, 'error': 'No employee profile.'}, status=400)
        try:
            # Query all notifications for the user
            table = NotificationsTable._get_table()
            response = table.query(
                KeyConditionExpression=Key('EmployeeID').eq(user_emp_id),
                ConsistentRead=True
            )
            for n in response.get('Items', []):
                if not n.get('IsRead'):
                    NotificationsTable.update_item(
                        Key={'EmployeeID': user_emp_id, 'Timestamp': n['Timestamp']},
                        UpdateExpression="SET IsRead = :val",
                        ExpressionAttributeValues={':val': True}
                    )
            # Set session flag to dismiss dynamic notifications (birthdays)
            request.session['notifications_dismissed'] = True
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

class SuperAdminApprovalsView(FeatureRequiredMixin, SuperAdminRequiredMixin, TemplateView):
    required_feature = 'ess_portal'
    template_name = 'core/super_admin_approvals.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from core.dynamodb_service import (
            EmployeesTable, PayrollApprovalsTable, WFHRequestsTable, 
            ResignationsTable, ExpensesTable, UsersTable
        )
        from boto3.dynamodb.conditions import Key
        
        all_employees = EmployeesTable.scan()
        all_users = UsersTable.scan()
        user_role_map = {u.get('EmployeeID'): u.get('Role') for u in all_users if u.get('EmployeeID')}
        
        approvals = []
        
        # 1. Payroll Approvals (Most Critical)
        try:
            payroll_queue = [p for p in PayrollApprovalsTable.scan() if p.get('Status') == 'Pending Super Admin Approval']
            for p in payroll_queue:
                approvals.append({
                    'title': 'Payroll Batch Authorization',
                    'subtitle': f"{p.get('MonthYear')} Financial Liability",
                    'detail': f"Total Disbursement: ₹{p.get('TotalNetPay')}",
                    'badge': 'Payroll',
                    'badge_class': 'success',
                    'icon': 'fa-money-bill-transfer',
                    'url': 'payroll_approval_list',
                    'date': p.get('SubmittedAt', 'Recent')
                })
        except: pass

        # 2. Resignation Approvals (Direct Reports - HR ADMINs)
        try:
            pending_res = [r for r in ResignationsTable.scan() if r.get('Status') == 'Pending HR ADMIN Review']
            for r in pending_res:
                emp_id = r.get('EmployeeID')
                if user_role_map.get(emp_id) == 'HR ADMIN': # Only SA sees HR ADMIN resignations
                    emp = next((e for e in all_employees if e.get('EmployeeID') == emp_id), None)
                    approvals.append({
                        'title': 'Resignation Notice',
                        'subtitle': f"{emp.get('FirstName', '')} {emp.get('LastName', '')} (HR ADMIN)",
                        'detail': f"Last Working Day: {r.get('LastWorkingDay')}",
                        'badge': 'Governance',
                        'badge_class': 'danger',
                        'icon': 'fa-user-minus',
                        'url': 'resignation_approvals',
                        'date': 'Pending'
                    })
        except: pass

        # 3. WFH Approvals (If SA is the direct manager)
        try:
            pending_wfh = [w for w in WFHRequestsTable.scan() if w.get('Status') == 'Pending Manager Approval' and w.get('ApproverID') == self.request.user.employee_id]
            for w in pending_wfh:
                emp = next((e for e in all_employees if e.get('EmployeeID') == w.get('EmployeeID')), None)
                approvals.append({
                    'title': 'WFH Request',
                    'subtitle': f"{emp.get('FirstName', '')} {emp.get('LastName', '')}",
                    'detail': f"Requested for: {w.get('WFHDate')}",
                    'badge': 'WFH',
                    'badge_class': 'primary',
                    'icon': 'fa-house-laptop',
                    'url': 'wfh_approvals',
                    'date': w.get('WFHDate')
                })
        except: pass

        context['all_approvals'] = approvals
        context['total_pending'] = len(approvals)
        return context

class HRGenerateLetterView(FeatureRequiredMixin, HRRequiredMixin, View):
    required_feature = 'hr_letters'
    def get(self, request):
        from core.utils import apply_pending_hikes
        apply_pending_hikes()
        from core.dynamodb_service import EmployeesTable, UsersTable, EmployeeLettersTable
        import datetime
        all_employees = EmployeesTable.scan()
        all_users = UsersTable.scan()
        current_user_role = request.user.role
        active_employees = []
        emp_dict = {emp['EmployeeID']: emp for emp in all_employees}
        
        for emp in all_employees:
            user = next((u for u in all_users if u.get('UserID') == emp.get('UserID')), None)
            if user and user.get('Role') == 'Super admin': continue
            if user and not user.get('IsActive', True): continue
            
            # If logged in as HR ADMIN, do not display other HR ADMINs in the dropdown
            if current_user_role == 'HR ADMIN' and user and user.get('Role') == 'HR ADMIN':
                continue
                
            active_employees.append(emp)

        # Retrieve all generated letters
        all_letters = EmployeeLettersTable.scan()
        letters_list = []
        for l in all_letters:
            emp_id = l.get('EmployeeID')
            emp_info = emp_dict.get(emp_id)
            if emp_info:
                # If current user is HR ADMIN, do not show letters for other HR ADMINs
                if current_user_role == 'HR ADMIN':
                    user = next((u for u in all_users if u.get('UserID') == emp_info.get('UserID')), None)
                    if user and user.get('Role') == 'HR ADMIN':
                        continue
                        
                l['employee_name'] = f"{emp_info.get('FirstName', '')} {emp_info.get('LastName', '')}"
                l['department'] = emp_info.get('Department', 'N/A')
                try:
                    parsed_date = datetime.datetime.fromisoformat(l.get('GeneratedDate', '')).strftime('%B %d, %Y, %I:%M %p')
                except Exception:
                    parsed_date = l.get('GeneratedDate', 'N/A')
                l['formatted_date'] = parsed_date
                letters_list.append(l)

        # Sort letters by GeneratedDate descending
        letters_list = sorted(letters_list, key=lambda x: x.get('GeneratedDate', ''), reverse=True)
        
        return render(request, 'core/generate_letter.html', {
            'employees': active_employees,
            'letters': letters_list
        })

    def post(self, request):
        from core.utils import apply_pending_hikes, get_lurnexa_logo_base64, get_authorized_signature_stamp_base64
        apply_pending_hikes()
        logo_base64 = get_lurnexa_logo_base64()
        
        sig_data = request.POST.get('signature_data')
        if sig_data and sig_data.startswith('data:image/'):
            signature_stamp_base64 = sig_data
        else:
            signature_stamp_base64 = get_authorized_signature_stamp_base64()
            
        employee_id = request.POST.get('employee_id')
        letter_type = request.POST.get('letter_type')
        effective_date = request.POST.get('effective_date')
        
        from core.dynamodb_service import EmployeesTable, EmployeeLettersTable
        import uuid, datetime
        emp = EmployeesTable.get_item({'EmployeeID': employee_id})
        if not emp:
            from django.contrib import messages
            messages.error(request, 'Employee not found.')
            return redirect('hr_generate_letter')
            
        emp_name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}"
        letter_id = str(uuid.uuid4())
        
        # 1. Offer Letter: Handled via File Upload
        if letter_type == 'Offer Letter':
            offer_document = request.FILES.get('offer_document')
            if not offer_document:
                from django.contrib import messages
                messages.error(request, 'Please upload the Offer Document.')
                return redirect('hr_generate_letter')
                
            from core.utils import save_uploaded_file
            file_path = save_uploaded_file(offer_document, 'letters')
            
            letter_item = {
                'EmployeeID': employee_id,
                'LetterID': letter_id,
                'LetterType': letter_type,
                'GeneratedDate': get_local_now().isoformat(),
                'FilePath': file_path,
                'EmailSent': False
            }
            EmployeeLettersTable.put_item(letter_item)
            
            from django.contrib import messages
            messages.success(request, f"Offer Letter uploaded successfully for {emp_name}.")
            return redirect('hr_generate_letter')

        # 2. Other Letters: Handled via HTML Generation
        content_html = ""
        email_body_plain = ""
        
        gender = (emp.get('Gender') or '').strip().lower()
        salutation = 'Mr.' if gender == 'male' else 'Ms.' if gender == 'female' else 'Mr./Ms.'
        last_name = emp.get('LastName', '').strip()
        if not last_name:
            last_name = emp.get('FirstName', '')

        subject_pronoun = 'He' if gender == 'male' else 'She' if gender == 'female' else 'He/She'
        possessive_pronoun = 'his' if gender == 'male' else 'her' if gender == 'female' else 'his/her'
        object_pronoun = 'him' if gender == 'male' else 'her' if gender == 'female' else 'him/her'
        subject_pronoun_lower = subject_pronoun.lower()
        possessive_pronoun_cap = possessive_pronoun.capitalize()
        
        if letter_type == 'Bonus Letter':
            amount = request.POST.get('bonus_amount', '')
            letter_title = "Bonus Award Letter"
            letter_body = f"""
            <p><strong>Dear {emp_name},</strong></p>
            <p>We are delighted to inform you that in recognition of your outstanding performance and dedication, the management has decided to award you a performance bonus of <strong>{amount}</strong>.</p>
            <p>This bonus is effective as of <strong>{effective_date}</strong> and will be processed along with your next payroll cycle.</p>
            <p>We appreciate your hard work and look forward to your continued contributions to the success of Lurnexa.</p>
            """
        elif letter_type == 'Hike Letter':
            percentage = request.POST.get('hike_percentage', '')
            letter_title = "Compensation Revision Letter"
            letter_body = f"""
            <p><strong>Dear {emp_name},</strong></p>
            <p>Following the recent performance review cycle, we are pleased to inform you that your compensation has been revised.</p>
            <p>Your annual salary has been increased by <strong>{percentage}%</strong>, effective from <strong>{effective_date}</strong>.</p>
            <p>This increase reflects our appreciation for your commitment and the value you bring to our team. Keep up the great work!</p>
            """
            
            # Automatically update the employee's CTC (SalaryPA) based on the hike percentage ONLY if effective date has already been reached
            hike_applied_immediately = False
            try:
                today_str = datetime.date.today().isoformat()
                if effective_date <= today_str:
                    current_salary = safe_float(emp.get('SalaryPA'))
                    hike_pct = float(percentage or 0)
                    if hike_pct > 0:
                        new_salary = current_salary * (1 + hike_pct / 100)
                        emp['SalaryPA'] = str(round(new_salary, 2))
                        EmployeesTable.put_item(emp)
                        hike_applied_immediately = True
            except Exception as ex:
                print(f"Failed to update employee CTC for hike: {ex}")
        elif letter_type == 'Promotion Letter':
            new_designation = request.POST.get('new_designation', '').strip()
            new_salary = request.POST.get('new_salary', '').strip()
            letter_title = "Promotion Letter"
            letter_body = f"""
            <p><strong>Dear {emp_name},</strong></p>
            <p>We are pleased to inform you that you have been promoted to the position of <strong>{new_designation}</strong>, effective from <strong>{effective_date}</strong>.</p>
            """
            if new_salary:
                letter_body += f"<p>With this promotion, your revised annual compensation will be <strong>Rs. {new_salary}</strong>.</p>"
            letter_body += """
            <p>This promotion is in recognition of your outstanding performance, dedication, and contributions to Lurnexa. We thank you for your hard work and look forward to your continued success in this new role.</p>
            """
            
            # Automatically update the employee's designation (and CTC) if effective date has already been reached
            promotion_applied_immediately = False
            try:
                today_str = datetime.date.today().isoformat()
                if effective_date <= today_str:
                    emp['Designation'] = new_designation
                    if new_salary:
                        emp['SalaryPA'] = new_salary
                    EmployeesTable.put_item(emp)
                    promotion_applied_immediately = True
            except Exception as ex:
                print(f"Failed to update employee details for promotion: {ex}")
        elif letter_type == 'Experience Letter':
            lwd = request.POST.get('lwd', '')
            today_str = datetime.date.today().strftime('%B %d, %Y')
            try:
                joined_date_fmt = datetime.datetime.strptime(emp.get('JoinedDate', ''), '%Y-%m-%d').strftime('%B %d, %Y') if emp.get('JoinedDate') else today_str
            except Exception:
                joined_date_fmt = today_str

            try:
                lwd_fmt = datetime.datetime.strptime(lwd, '%Y-%m-%d').strftime('%B %d, %Y') if lwd else today_str
            except Exception:
                lwd_fmt = lwd or today_str

            designation = emp.get('Designation', 'Employee')
            department = emp.get('Department', 'Operations')

            letter_title = "Relieving & Experience Letter"
            letter_body = f"""
            <p><strong>To,</strong></p>
            <p>This is to certify that <strong>{salutation} {emp_name}</strong> was employed with <strong>Lurnexa</strong>. {subject_pronoun} served the organization from <strong>{joined_date_fmt}</strong> to <strong>{lwd_fmt}</strong>.</p>
            <p>During {possessive_pronoun} tenure with us, {salutation} {emp_name} was designated as <strong>{designation}</strong> in the <strong>{department}</strong> department. Throughout {possessive_pronoun} employment, {subject_pronoun_lower} demonstrated outstanding professionalism, dedication, and a strong work ethic. {possessive_pronoun_cap} contributions have been highly valued by the team and management alike.</p>
            <p>This certificate confirms that {salutation} {emp_name} has been officially relieved of {possessive_pronoun} duties and responsibilities, effective from the close of business hours on <strong>{lwd_fmt}</strong>. We verify that all formal handing-over procedures have been successfully completed.</p>
            <p>We extend our sincere appreciation to {object_pronoun} for {possessive_pronoun} dedicated services and wish {object_pronoun} the absolute best in all future professional and personal endeavors.</p>
            """
            email_body_plain = f"Dear {emp_name},\n\nYour Experience Letter has been generated. This certifies your employment with Lurnexa from {joined_date_fmt} until {lwd_fmt}.\n\nPlease log in to your Lurnexa portal (Documents -> Letters) to download the official formatted PDF version for your records.\n\nBest Regards,\nHR Department"
            
        elif letter_type == 'PF Letter':
            letter_title = "Provident Fund Declaration"
            letter_body = f"""
            <p><strong>To,</strong></p>
            <p>This is to certify that Provident Fund contributions for <strong>{salutation} {emp_name}</strong> have been processed according to statutory requirements during {possessive_pronoun} tenure with Lurnexa.</p>
            <p>For further details, please refer to the official EPFO portal.</p>
            """
            email_body_plain = f"Dear {emp_name},\n\nYour PF Letter has been generated.\n\nPlease log in to your Lurnexa portal (Documents -> Letters) to download the official formatted PDF version for your records.\n\nBest Regards,\nHR Department"

        date_element = ""
        if letter_type not in ['Experience Letter', 'PF Letter']:
            date_element = f'<p style="text-align: right; color: black; margin-bottom: 20px;"><strong>Date:</strong> {datetime.date.today().strftime("%B %d, %Y")}</p>'

        styled_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                @page {{
                    size: A4;
                    margin: 0;
                }}
                body {{
                    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                    padding: 0;
                    margin: 0;
                    color: black;
                    line-height: 1.6;
                    background-color: #f3f4f6;
                }}
                .container {{
                    width: 210mm;
                    min-height: 297mm;
                    margin: 20px auto;
                    border: 1px solid black;
                    padding: 25mm 20mm;
                    background-color: #ffffff;
                    box-sizing: border-box;
                    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
                }}
                .header {{ text-align: center; margin-bottom: 30px; border-bottom: 2px solid black; padding-bottom: 15px; }}
                .header h2 {{ margin: 0; color: black; font-size: 24px; font-weight: bold; letter-spacing: 1px; text-transform: uppercase; }}
                .content {{ margin-bottom: 40px; font-size: 15px; color: black; }}
                .footer {{ margin-top: 40px; color: black; }}
                .signature {{ margin-top: 5px; border-top: 1px solid black; width: 220px; padding-top: 8px; font-weight: bold; color: black; }}
                @media print {{
                    body {{
                        background-color: #ffffff;
                    }}
                    .container {{
                        width: 210mm;
                        height: 297mm;
                        margin: 0;
                        padding: 25mm 20mm;
                        border: none;
                        box-shadow: none;
                        page-break-after: always;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div style="text-align: center; margin-bottom: 5px;">
                        <h2 style="margin: 0; color: black; font-size: 24px; font-weight: bold; letter-spacing: 1px; text-transform: uppercase; display: inline-block; vertical-align: middle;">LURNEXA</h2>
                    </div>
                    <p style="margin: 5px 0 0 0; font-size: 14px; color: black;">Official Employee Document</p>
                </div>
                <div class="content">
                    <h1 style="text-align: center; color: black; margin-bottom: 30px; font-weight: bold; text-decoration: underline; text-transform: uppercase; font-size: 22px;">{letter_title}</h1>
                    {date_element}
                    {letter_body}
                </div>
                <div class="footer">
                    <p style="color: black; margin-bottom: 10px;">Best Regards,</p>
                    <div style="margin-bottom: 5px; height: 110px;">
                        <img src="{signature_stamp_base64}" alt="Authorized Signature & Stamp" style="height: 110px; width: auto;" />
                    </div>
                    <div class="signature">
                        Authorized Signatory<br>
                        Human Resources, Lurnexa
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

        # Save the generated HTML content as a file in default_storage
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        
        file_path = f"letters/{letter_id}.html"
        default_storage.save(file_path, ContentFile(styled_html.encode('utf-8')))

        letter_item = {
            'EmployeeID': employee_id,
            'LetterID': letter_id,
            'LetterType': letter_type,
            'GeneratedDate': get_local_now().isoformat(),
            'FilePath': file_path,
            'EmailSent': False
        }
        if letter_type == 'Hike Letter':
            letter_item['EffectiveDate'] = effective_date
            letter_item['HikePercentage'] = percentage
            letter_item['HikeApplied'] = hike_applied_immediately
        elif letter_type == 'Promotion Letter':
            letter_item['EffectiveDate'] = effective_date
            letter_item['NewDesignation'] = new_designation
            letter_item['NewSalary'] = new_salary
            letter_item['PromotionApplied'] = promotion_applied_immediately
        elif letter_type == 'Bonus Letter':
            letter_item['BonusAmount'] = request.POST.get('bonus_amount', '0')
        
        EmployeeLettersTable.put_item(letter_item)
        
        from django.contrib import messages
        if letter_type == 'Hike Letter':
            if hike_applied_immediately:
                messages.success(request, f"{letter_type} generated successfully for {emp_name} and their CTC has been updated automatically.")
            else:
                messages.success(request, f"{letter_type} generated successfully for {emp_name} and scheduled to take effect on {effective_date}.")
        elif letter_type == 'Promotion Letter':
            if promotion_applied_immediately:
                messages.success(request, f"{letter_type} generated successfully for {emp_name} and their designation/CTC has been updated automatically.")
            else:
                messages.success(request, f"{letter_type} generated successfully for {emp_name} and scheduled to take effect on {effective_date}.")
        else:
            messages.success(request, f"{letter_type} generated successfully for {emp_name}.")
        return redirect('hr_generate_letter')


class HRSendLetterEmailView(FeatureRequiredMixin, HRRequiredMixin, View):
    required_feature = 'hr_letters'
    def get(self, request, employee_id, letter_id):
        from core.dynamodb_service import EmployeesTable, EmployeeLettersTable
        from django.contrib import messages
        from core.utils import send_notification
        from django.core.files.storage import default_storage
        import mimetypes
        import os

        # Get the letter details
        letter = EmployeeLettersTable.get_item({'EmployeeID': employee_id, 'LetterID': letter_id})
        if not letter:
            messages.error(request, "Letter not found.")
            return redirect('hr_generate_letter')

        # Get employee details
        emp = EmployeesTable.get_item({'EmployeeID': employee_id})
        if not emp:
            messages.error(request, "Employee not found.")
            return redirect('hr_generate_letter')

        letter_type = letter.get('LetterType')
        file_path = letter.get('FilePath')
        emp_name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}"

        # Determine subject and body for the email
        if letter_type == 'Experience Letter':
            email_subject = f"Lurnexa: Your Experience Letter"
            email_body = (
                f"Dear {emp_name},\n\n"
                f"Your Experience Letter has been generated. Please find it attached to this email.\n\n"
                f"Best Regards,\nHR Department"
            )
        elif letter_type == 'PF Letter':
            email_subject = f"Lurnexa: Your PF Letter"
            email_body = (
                f"Dear {emp_name},\n\n"
                f"Your PF Letter has been generated. Please find it attached to this email.\n\n"
                f"Best Regards,\nHR Department"
            )
        elif letter_type == 'Hike Letter':
            email_subject = f"Lurnexa: Your Compensation Revision Letter"
            email_body = (
                f"Dear {emp_name},\n\n"
                f"We are pleased to inform you that your compensation has been revised. Please find your Hike Revision Letter attached.\n\n"
                f"Best Regards,\nHR Department"
            )
        elif letter_type == 'Promotion Letter':
            email_subject = f"Congratulations on Your Promotion, {emp.get('FirstName', 'Employee')}!"
            email_body = (
                f"Dear {emp_name},\n\n"
                f"Congratulations! We are absolutely thrilled to inform you that you have been promoted. "
                f"This promotion is a testament to your outstanding performance, dedication, and contributions to Lurnexa.\n\n"
                f"We have attached your official Promotion Letter to this email. You can also view and download this letter "
                f"at any time by logging into the Lurnexa portal and navigating to the 'My Letters' page.\n\n"
                f"We are incredibly proud of your accomplishments and wish you continued success in your new role!\n\n"
                f"Best Regards,\n"
                f"Human Resources Team\n"
                f"Lurnexa"
            )
        elif letter_type == 'Bonus Letter':
            email_subject = f"Lurnexa: Your Bonus Award Letter"
            email_body = (
                f"Dear {emp_name},\n\n"
                f"We are pleased to inform you that you have been awarded a performance bonus. Please find your Bonus Award Letter attached.\n\n"
                f"Best Regards,\nHR Department"
            )
        elif letter_type == 'Offer Letter':
            email_subject = f"Lurnexa: Your Offer Letter"
            email_body = (
                f"Dear {emp_name},\n\n"
                f"Congratulations! Please find your Offer Letter attached.\n\n"
                f"Best Regards,\nHR Department"
            )
        else:
            email_subject = f"Lurnexa: Your Generated Document ({letter_type})"
            email_body = (
                f"Dear {emp_name},\n\n"
                f"Please find your official {letter_type} attached.\n\n"
                f"Best Regards,\nHR Department"
            )

        attachments = []
        if file_path:
            try:
                with default_storage.open(file_path, 'rb') as f:
                    file_content = f.read()

                _, ext = os.path.splitext(file_path)
                ext = ext.lower()

                if ext == '.html':
                    # Convert HTML content to PDF for email attachment
                    from workflows.views import html_to_pdf_bytes
                    import re
                    html_str = file_content.decode('utf-8')
                    
                    pdf_style = """
    <style>
        @page {
            size: A4;
            margin: 2.5cm 2cm 2.5cm 2cm;
        }
        body {
            font-family: 'Helvetica', 'Arial', sans-serif;
            background-color: #ffffff;
            color: #333333;
            line-height: 1.6;
            font-size: 14px;
        }
        .container {
            width: 100%;
            margin: 0;
            padding: 0;
            background: none;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 2px solid #1a4f8b;
            padding-bottom: 15px;
        }
        .header h2 {
            margin: 0;
            color: #1a4f8b;
            font-size: 24px;
            font-weight: bold;
            letter-spacing: 1px;
            text-transform: uppercase;
        }
        .content {
            margin-bottom: 40px;
            font-size: 14px;
            color: #333333;
        }
        .content p {
            margin-bottom: 15px;
        }
        .footer {
            margin-top: 40px;
        }
        .signature {
            margin-top: 5px;
            border-top: 1px solid #cbd5e1;
            width: 220px;
            padding-top: 8px;
            font-weight: bold;
            color: #1a4f8b;
        }
    </style>
"""
                    html_str = re.sub(r'<style>.*?</style>', pdf_style, html_str, flags=re.DOTALL | re.IGNORECASE)
                    pdf_bytes = html_to_pdf_bytes(html_str)
                    if pdf_bytes:
                        filename = f"{letter_type.replace(' ', '_')}_{emp.get('FirstName', 'Employee')}_{emp.get('LastName', '')}.pdf"
                        attachments.append((filename, pdf_bytes, 'application/pdf'))
                else:
                    content_type, _ = mimetypes.guess_type(file_path)
                    filename = f"{letter_type.replace(' ', '_')}_{emp.get('FirstName', 'Employee')}_{emp.get('LastName', '')}{ext}"
                    attachments.append((filename, file_content, content_type or 'application/octet-stream'))
            except Exception as e:
                print(f"Error reading or generating attachment for manual send: {e}")

        try:
            send_notification(
                employee_id=employee_id,
                title=f"{letter_type} Emailed",
                message=f"Your {letter_type} has been sent to your registered email address.",
                n_type='System',
                icon='fa-envelope',
                color='success',
                email_subject=email_subject,
                email_body=email_body,
                attachments=attachments if attachments else None
            )

            # Update the letter to set EmailSent = True
            letter['EmailSent'] = True
            EmployeeLettersTable.put_item(letter)

            messages.success(request, f"Email for {letter_type} sent successfully to {emp_name}.")
        except Exception as e:
            messages.error(request, f"Failed to send email: {e}")

        from django.urls import reverse
        return redirect(reverse('hr_generate_letter') + '?tab=history')

class ContactUsView(View):
    def post(self, request):
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        email = request.POST.get('email', '')
        phone = request.POST.get('phone', '')
        message = request.POST.get('message', '')
        
        try:
            from django.core.mail import EmailMessage
            from django.conf import settings
            
            subject = f"New Enterprise Inquiry: {first_name} {last_name}"
            body = f"Hello Lurnexa Team,\n\nYou have received a new enterprise inquiry from the Lurnexa HRMS landing page.\n\nContact Details:\n----------------\nName: {first_name} {last_name}\nWork Email: {email}\nContact Number: {phone}\n\nMessage:\n--------\n{message}\n\n---\nThis is an automated system notification generated by the Lurnexa Platform."
            
            email_msg = EmailMessage(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=['info@lurnexatechnologies.in'],
                reply_to=[email]
            )
            email_msg.send(fail_silently=False)
            messages.success(request, "Your message has been sent successfully! Our team will get back to you soon.")
        except Exception as e:
            messages.error(request, "There was an error sending your message. Please try again later.")
            
        return redirect('/#contact')


class OKRView(FeatureRequiredMixin, LoginRequiredMixin, TemplateView):
    required_feature = 'okrs_appraisals'
    template_name = 'core/okrs.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        eid = user.employee_id
        role = user.role

        today_str = get_local_date().isoformat()
        try:
            my_okrs = OKRsTable.query(
                KeyConditionExpression=Key('EmployeeID').eq(eid)
            )
            for o in my_okrs:
                o['Progress'] = int(o.get('Progress', 0))
                o['TargetValue'] = int(o.get('TargetValue', 100))
                o['CurrentValue'] = int(o.get('CurrentValue', 0))
                if o.get('ManagerRating') is not None:
                    o['ManagerRating'] = float(o.get('ManagerRating'))
                
                # Daily update calculations
                hist = o.get('ProgressHistory', [])
                o['TodayProgress'] = sum(int(h.get('Increment', 0)) for h in hist if h.get('Date') == today_str)
                o['ProgressHistory'] = hist
        except Exception:
            my_okrs = []
        
        context['my_okrs'] = sorted(my_okrs, key=lambda x: x.get('CreatedAt', ''), reverse=True)

        team_okrs = []
        all_okrs = []
        try:
            all_okrs = OKRsTable.scan(
                FilterExpression="OrgID = :oid",
                ExpressionAttributeValues={":oid": user.org_id}
            )
            for o in all_okrs:
                o['Progress'] = int(o.get('Progress', 0))
                o['TargetValue'] = int(o.get('TargetValue', 100))
                o['CurrentValue'] = int(o.get('CurrentValue', 0))
                if o.get('ManagerRating') is not None:
                    o['ManagerRating'] = float(o.get('ManagerRating'))
                
                # Daily update calculations
                hist = o.get('ProgressHistory', [])
                o['TodayProgress'] = sum(int(h.get('Increment', 0)) for h in hist if h.get('Date') == today_str)
                o['ProgressHistory'] = hist
        except Exception:
            pass

        emp_role_map = {}
        try:
            all_emp_raw = EmployeesTable.scan(
                FilterExpression="OrgID = :oid",
                ExpressionAttributeValues={":oid": user.org_id}
            )
            emp_map = {e['EmployeeID']: f"{e.get('FirstName', '')} {e.get('LastName', '')}" for e in all_emp_raw}
            
            # Fetch user roles mapping from UsersTable
            users_raw = UsersTable.scan(
                FilterExpression="OrgID = :oid",
                ExpressionAttributeValues={":oid": user.org_id}
            )
            emp_role_map = {u['EmployeeID']: u.get('Role') for u in users_raw if u.get('EmployeeID')}
            
            if role == 'Super admin':
                # Super admin decides goals for Managers and HR.
                active_subs = [e for e in all_emp_raw if emp_role_map.get(e['EmployeeID']) in ('Manager', 'HR ADMIN')]
                context['active_employees'] = sorted(active_subs, key=lambda x: x.get('FirstName', ''))
            elif role == 'Manager':
                # Manager decides goals for Employees (subordinates).
                subordinates = ReportingHierarchyTable.scan(
                    FilterExpression="ManagerID = :mid",
                    ExpressionAttributeValues={":mid": eid}
                )
                sub_ids = {s.get('EmployeeID') for s in subordinates if s.get('EmployeeID')}
                mgr_subs = [e for e in all_emp_raw if e['EmployeeID'] in sub_ids]
                context['active_employees'] = sorted(mgr_subs, key=lambda x: x.get('FirstName', ''))
            else:
                # HR ADMIN and Employees cannot assign goals.
                context['active_employees'] = []
        except Exception:
            emp_map = {}
            context['active_employees'] = []

        if role in ('Super admin', 'HR ADMIN'):
            for o in all_okrs:
                if o.get('EmployeeID') != eid:
                    o['EmployeeName'] = emp_map.get(o.get('EmployeeID'), o.get('EmployeeID'))
                    o['EmployeeRole'] = emp_role_map.get(o.get('EmployeeID'), 'Employee')
                    team_okrs.append(o)
        else:
            try:
                subordinates = ReportingHierarchyTable.scan(
                    FilterExpression="ManagerID = :mid",
                    ExpressionAttributeValues={":mid": eid}
                )
                sub_ids = [s.get('EmployeeID') for s in subordinates if s.get('EmployeeID')]
            except Exception:
                sub_ids = []

            for o in all_okrs:
                if o.get('EmployeeID') in sub_ids:
                    o['EmployeeName'] = emp_map.get(o.get('EmployeeID'), o.get('EmployeeID'))
                    o['EmployeeRole'] = emp_role_map.get(o.get('EmployeeID'), 'Employee')
                    team_okrs.append(o)

        context['team_okrs'] = sorted(team_okrs, key=lambda x: x.get('CreatedAt', ''), reverse=True)
        context['is_manager_or_hr'] = len(team_okrs) > 0 or role in ('Super admin', 'HR ADMIN', 'Manager')
        
        # Calculate Stats for my_okrs
        total_my = len(my_okrs)
        completed_my = sum(1 for o in my_okrs if o.get('Status') == 'Completed')
        avg_progress_my = 0
        if total_my > 0:
            avg_progress_my = sum(int(o.get('Progress', 0)) for o in my_okrs) // total_my
            
        ratings = [float(o.get('ManagerRating')) for o in my_okrs if o.get('ManagerRating')]
        avg_rating_my = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
        
        context['stats_my'] = {
            'total': total_my,
            'completed': completed_my,
            'avg_progress': avg_progress_my,
            'avg_rating': avg_rating_my
        }
        
        # Calculate Stats for team_okrs
        total_team = len(team_okrs)
        pending_appraisal_team = sum(1 for o in team_okrs if not o.get('ManagerRating'))
        
        context['stats_team'] = {
            'total': total_team,
            'pending': pending_appraisal_team
        }
        
        # 1. Seeding / Fetching Appraisal Cycles
        try:
            cycles = AppraisalCyclesTable.scan()
            if not cycles:
                default_cycle = {
                    'CycleID': 'q3-2026',
                    'Name': 'Q3 2026 Appraisal Cycle',
                    'Type': 'Quarterly',
                    'StartDate': '2026-07-01',
                    'EndDate': '2026-09-30',
                    'SubmissionDeadline': '2026-08-15',
                    'ReviewDeadline': '2026-09-01',
                    'ApprovalDeadline': '2026-09-15',
                    'Status': 'Active'
                }
                AppraisalCyclesTable.put_item(default_cycle)
                cycles = [default_cycle]
        except Exception:
            cycles = []
            
        active_cycles = [c for c in cycles if c.get('Status') == 'Active']
        active_cycle = active_cycles[0] if active_cycles else (cycles[0] if cycles else None)
        context['active_cycle'] = active_cycle
        context['all_cycles'] = cycles

        # 2. Self Appraisal details & History
        my_appraisal = None
        if active_cycle:
            try:
                my_appraisal = AppraisalsTable.get_item({'EmployeeID': eid, 'CycleID': active_cycle['CycleID']})
            except Exception:
                pass
        context['my_appraisal'] = my_appraisal

        try:
            appraisal_history = AppraisalsTable.query(
                KeyConditionExpression=Key('EmployeeID').eq(eid)
            )
        except Exception:
            appraisal_history = []
        context['appraisal_history'] = sorted(appraisal_history, key=lambda x: x.get('CycleID', ''), reverse=True)

        # 3. Employee's own designation, salary history
        try:
            all_emp_raw = EmployeesTable.scan()
        except Exception:
            all_emp_raw = []
        current_employee = next((e for e in all_emp_raw if e.get('EmployeeID') == eid), {})
        context['current_employee'] = current_employee
        context['promotion_history'] = current_employee.get('PromotionHistory', [])
        context['salary_history'] = current_employee.get('SalaryHistory', [])

        # 4. Manager subordinates mapping
        try:
            subordinates = ReportingHierarchyTable.scan(
                FilterExpression="ManagerID = :mid",
                ExpressionAttributeValues={":mid": eid}
            )
            sub_ids = [s.get('EmployeeID') for s in subordinates if s.get('EmployeeID')]
        except Exception:
            sub_ids = []

        # 5. Load and enrich appraisals
        all_appraisals = []
        try:
            all_appraisals = AppraisalsTable.scan()
            for app in all_appraisals:
                emp_details = next((e for e in all_emp_raw if e.get('EmployeeID') == app.get('EmployeeID')), {})
                app['EmployeeName'] = f"{emp_details.get('FirstName', '')} {emp_details.get('LastName', '')}"
                app['Designation'] = emp_details.get('Designation', 'Employee')
                app['Department'] = emp_details.get('Department', 'Operations')
                app['JoinedDate'] = emp_details.get('JoinedDate', '')
                app['Salary'] = float(emp_details.get('Salary', 0))
        except Exception:
            pass

        # Filter appraisals based on role
        if role in ('Super admin', 'HR ADMIN'):
            context['all_appraisals'] = all_appraisals
        else:
            context['all_appraisals'] = []
            
        # Determine target reviewee IDs based on role
        reviewee_ids = []
        try:
            users_raw = UsersTable.scan()
            emp_role_map = {u['EmployeeID']: u.get('Role') for u in users_raw if u.get('EmployeeID')}
        except Exception:
            emp_role_map = {}

        if role == 'Manager':
            reviewee_ids = [rid for rid in sub_ids if rid != eid]
        elif role == 'Super admin':
            reviewee_ids = [rid for rid, r in emp_role_map.items() if r in ('Manager', 'HR ADMIN') and rid != eid]

        mgr_appraisals = []
        active_cycle_id = active_cycle['CycleID'] if active_cycle else 'q3-2026'
        
        for rid in reviewee_ids:
            emp_details = next((e for e in all_emp_raw if e.get('EmployeeID') == rid), None)
            if not emp_details:
                continue
            app = next((a for a in all_appraisals if a.get('EmployeeID') == rid and a.get('CycleID') == active_cycle_id), None)
            if not app:
                app = {
                    'EmployeeID': rid,
                    'CycleID': active_cycle_id,
                    'Status': 'Pending Manager Review',
                    'SelfAppraisal': {'Achievements': 'Self Appraisal Disabled'},
                    'ManagerReview': {},
                    'HRReview': {},
                    'FounderApproval': {}
                }
            app['EmployeeName'] = f"{emp_details.get('FirstName', '')} {emp_details.get('LastName', '')}"
            app['Designation'] = emp_details.get('Designation', 'Employee')
            app['Department'] = emp_details.get('Department', 'Operations')
            app['JoinedDate'] = emp_details.get('JoinedDate', '')
            app['Salary'] = float(emp_details.get('Salary', 0))
            mgr_appraisals.append(app)
            
        context['mgr_appraisals'] = mgr_appraisals

        # 6. Performance Analytics
        # HR/Founder Analytics
        ratings_list = []
        dept_performances = {}
        top_performers = []
        pending_approvals = []
        promotion_requests = []
        salary_hike_requests = []
        salary_budget_delta = 0.0

        for a in all_appraisals:
            mgr_rev = a.get('ManagerReview', {})
            fnd_app = a.get('FounderApproval', {})
            
            rating = float(fnd_app.get('OverrideRating') or mgr_rev.get('Rating') or 0.0)
            if rating > 0:
                ratings_list.append(rating)
                
            # Department averages
            dept = a.get('Department', 'Operations')
            if rating > 0:
                if dept not in dept_performances:
                    dept_performances[dept] = []
                dept_performances[dept].append(rating)
                
            # Top performers
            if rating >= 4.0:
                top_performers.append({
                    'EmployeeName': a.get('EmployeeName'),
                    'Rating': rating,
                    'Department': dept
                })

            # Pending founder approval / HR review list
            if a.get('Status') == 'Pending Founder Approval':
                pending_approvals.append(a)
            if a.get('Status') == 'Pending HR Review':
                context['pending_hr_reviews_count'] = context.get('pending_hr_reviews_count', 0) + 1

            # Promotion recommendations
            if mgr_rev.get('RecommendPromotion'):
                promotion_requests.append({
                    'EmployeeName': a.get('EmployeeName'),
                    'CurrentDesignation': a.get('Designation'),
                    'RecommendedDesignation': mgr_rev.get('RecommendedDesignation'),
                    'Status': a.get('Status')
                })

            # Salary hike recommendations
            if mgr_rev.get('RecommendSalaryHike'):
                old_sal = float(a.get('Salary', 0))
                new_sal = float(mgr_rev.get('RecommendedSalary', old_sal))
                hike_pct = ((new_sal - old_sal) / old_sal * 100) if old_sal > 0 else 0.0
                salary_budget_delta += (new_sal - old_sal)
                salary_hike_requests.append({
                    'EmployeeName': a.get('EmployeeName'),
                    'CurrentSalary': old_sal,
                    'RecommendedSalary': new_sal,
                    'HikePercentage': round(hike_pct, 1),
                    'Status': a.get('Status')
                })

        # Calculate department rankings
        dept_rankings = []
        for d, r_list in dept_performances.items():
            dept_rankings.append({
                'Department': d,
                'AvgRating': round(sum(r_list) / len(r_list), 2)
            })
        dept_rankings = sorted(dept_rankings, key=lambda x: x['AvgRating'], reverse=True)

        context['analytics'] = {
            'avg_company_rating': round(sum(ratings_list) / len(ratings_list), 2) if ratings_list else 0.0,
            'top_performers': sorted(top_performers, key=lambda x: x['Rating'], reverse=True)[:5],
            'pending_approvals': pending_approvals,
            'promotion_requests': promotion_requests,
            'salary_hike_requests': salary_hike_requests,
            'salary_budget_delta': salary_budget_delta,
            'dept_rankings': dept_rankings
        }

        # 360-degree feedback data fetching
        feedback_eligible_employees = []
        try:
            for e in all_emp_raw:
                if e.get('OrgID') == user.org_id and e.get('EmployeeID') != eid:
                    role_of_e = emp_role_map.get(e.get('EmployeeID'))
                    if role_of_e not in ('Super admin', 'Platform Admin'):
                        feedback_eligible_employees.append({
                            'EmployeeID': e.get('EmployeeID'),
                            'Name': f"{e.get('FirstName', '')} {e.get('LastName', '')}",
                            'Designation': e.get('Designation', 'Employee'),
                            'Department': e.get('Department', '')
                        })
        except Exception as ex:
            print(f"Error fetching feedback eligible employees: {ex}")
        context['feedback_eligible_employees'] = feedback_eligible_employees

        feedback_requests_pending = []
        feedback_requests_submitted = []
        feedback_received = []
        feedback_manager_hr_view = []

        try:
            from core.dynamodb_service import FeedbackReviewAssignmentsTable, FeedbackReviewResponsesTable
            
            all_assignments = FeedbackReviewAssignmentsTable.scan(
                FilterExpression="OrgID = :oid",
                ExpressionAttributeValues={":oid": user.org_id}
            )
            all_responses = FeedbackReviewResponsesTable.scan(
                FilterExpression="OrgID = :oid",
                ExpressionAttributeValues={":oid": user.org_id}
            )
            
            responses_by_assign = {r.get('AssignmentID'): r for r in all_responses if r.get('AssignmentID')}
            
            def get_avg_rating(resp):
                if not resp:
                    return 0.0
                answers = resp.get('Answers', {})
                ratings = []
                for val in answers.values():
                    try:
                        ratings.append(float(val))
                    except ValueError:
                        pass
                return round(sum(ratings) / len(ratings), 1) if ratings else 0.0

            for a in all_assignments:
                assignment_id = a.get('AssignmentID')
                status = a.get('Status')
                resp_obj = responses_by_assign.get(assignment_id)
                
                formatted_fb = {
                    'FeedbackID': assignment_id,
                    'AssignmentID': assignment_id,
                    'RevieweeID': a.get('RevieweeID'),
                    'RevieweeName': a.get('RevieweeName'),
                    'ReviewerID': a.get('ReviewerID'),
                    'ReviewerName': a.get('ReviewerName'),
                    'ReviewerRole': a.get('ReviewerRole') or a.get('Relationship', 'Peer'),
                    'Status': 'Pending' if status in ('Pending Review', 'Pending Approval') else 'Submitted',
                    'RequestedAt': a.get('CreatedAt') or '2026-07-20',
                    'SubmittedAt': resp_obj.get('SubmittedAt', '') if resp_obj else '',
                    'Rating': get_avg_rating(resp_obj),
                    'Comments': resp_obj.get('Comments', 'No comments provided.') if resp_obj else ''
                }
                
                if a.get('ReviewerID') == eid:
                    if status in ('Pending Review', 'Pending Approval'):
                        feedback_requests_pending.append(formatted_fb)
                    elif status == 'Submitted':
                        feedback_requests_submitted.append(formatted_fb)
                
                if a.get('RevieweeID') == eid and status == 'Submitted':
                    feedback_received.append(formatted_fb)
                
                if status == 'Submitted':
                    if role == 'HR ADMIN':
                        feedback_manager_hr_view.append(formatted_fb)
                    elif role == 'Manager':
                        if a.get('RevieweeID') in sub_ids:
                            feedback_manager_hr_view.append(formatted_fb)
        except Exception as ex:
            print(f"Error loading new 360 feedback records for OKRView: {ex}")

        context['feedback_requests_pending'] = feedback_requests_pending
        context['feedback_requests_submitted'] = feedback_requests_submitted
        context['feedback_received'] = feedback_received
        context['feedback_manager_hr_view'] = feedback_manager_hr_view

        return context

class CreateOKRView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'okrs_appraisals'
    def post(self, request):
        user = request.user
        role = user.role
        
        # Only Super Admin or Manager can assign goals
        if role not in ('Super admin', 'Manager'):
            messages.error(request, "Permission denied. Only Super Admins and Managers can assign goals.")
            return redirect('okrs')
            
        assignee_id = request.POST.get('assignee_id')
        eid = user.employee_id
        
        # Fetch user roles mapping from UsersTable to validate role restrictions
        try:
            users_raw = UsersTable.scan()
            emp_role_map = {u['EmployeeID']: u.get('Role') for u in users_raw if u.get('EmployeeID')}
        except Exception:
            emp_role_map = {}
            
        assignee_role = emp_role_map.get(assignee_id)
        
        if role == 'Super admin':
            if assignee_role not in ('Manager', 'HR ADMIN'):
                messages.error(request, "Permission denied. Super Admins can only assign goals to Managers and HR.")
                return redirect('okrs')
        elif role == 'Manager':
            # Verify that assignee is indeed their subordinate
            try:
                subordinates = ReportingHierarchyTable.scan(
                    FilterExpression="ManagerID = :mid",
                    ExpressionAttributeValues={":mid": eid}
                )
                sub_ids = {s.get('EmployeeID') for s in subordinates if s.get('EmployeeID')}
                if assignee_id not in sub_ids:
                    messages.error(request, "Permission denied. You can only assign goals to your subordinates.")
                    return redirect('okrs')
            except Exception as e:
                messages.error(request, f"Error validating reporting hierarchy: {e}")
                return redirect('okrs')
        goal_name = request.POST.get('goal_name')
        description = request.POST.get('description')
        due_date = request.POST.get('due_date', '').strip()
        target_val = request.POST.get('target_value', '100')

        if not assignee_id or not goal_name or not description or not due_date:
            messages.error(request, "Employee Assignee, Goal Name, Description, and Target Date are required.")
            return redirect('okrs')

        try:
            goal_id = str(uuid.uuid4())
            item = {
                'EmployeeID': assignee_id,
                'GoalID': goal_id,
                'GoalName': goal_name,
                'Description': description,
                'Quarter': due_date,
                'DueDate': due_date,
                'TargetValue': int(target_val) if target_val.isdigit() else 100,
                'CurrentValue': 0,
                'Progress': 0,
                'Status': 'In Progress',
                'CreatedAt': get_local_now().isoformat(),
                'UpdatedAt': get_local_now().isoformat(),
                'OrgID': request.user.org_id
            }
            OKRsTable.put_item(item)
            messages.success(request, "Goal successfully assigned to the employee.")
        except Exception as e:
            messages.error(request, f"Error creating OKR: {e}")
        return redirect('okrs')


class RequestFeedback360View(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'okrs_appraisals'

    def post(self, request):
        reviewer_id = request.POST.get('reviewer_id', '').strip()
        reviewee_id = request.user.employee_id
        
        if not reviewer_id or not reviewee_id:
            messages.error(request, "Invalid feedback request parameters.")
            return redirect('okrs')
            
        try:
            from core.dynamodb_service import Feedback360Table, EmployeesTable
            import uuid
            from core.utils import get_local_now, send_notification
            
            user = request.user
            
            # Fetch names
            all_employees = EmployeesTable.scan()
            reviewer_emp = next((e for e in all_employees if e.get('EmployeeID') == reviewer_id), None)
            reviewee_emp = next((e for e in all_employees if e.get('EmployeeID') == reviewee_id), None)
            
            if not reviewer_emp or not reviewee_emp:
                messages.error(request, "Employee not found.")
                return redirect('okrs')
                
            # Verify OrgID matching
            if reviewer_emp.get('OrgID') != user.org_id or reviewee_emp.get('OrgID') != user.org_id:
                messages.error(request, "Access denied. Employee belongs to another organization.")
                return redirect('okrs')
                
            # Check if request already exists
            existing = Feedback360Table.scan(
                FilterExpression="OrgID = :oid AND RevieweeID = :rid AND ReviewerID = :rvr AND Status = :status",
                ExpressionAttributeValues={
                    ':oid': user.org_id,
                    ':rid': reviewee_id,
                    ':rvr': reviewer_id,
                    ':status': 'Pending'
                }
            )
            if existing:
                messages.warning(request, f"A pending feedback request already exists for {reviewer_emp.get('FirstName')} {reviewer_emp.get('LastName')}.")
                return redirect('okrs')
                
            feedback_id = str(uuid.uuid4())
            item = {
                'FeedbackID': feedback_id,
                'OrgID': user.org_id,
                'RevieweeID': reviewee_id,
                'RevieweeName': f"{reviewee_emp.get('FirstName', '')} {reviewee_emp.get('LastName', '')}",
                'ReviewerID': reviewer_id,
                'ReviewerName': f"{reviewer_emp.get('FirstName', '')} {reviewer_emp.get('LastName', '')}",
                'ReviewerRole': reviewer_emp.get('Designation', 'Peer'),
                'Status': 'Pending',
                'RequestedAt': get_local_now().isoformat(),
            }
            Feedback360Table.put_item(item)
            
            # Send Notification to Reviewer
            send_notification(
                employee_id=reviewer_id,
                title="360° Feedback Request",
                message=f"{item['RevieweeName']} has requested your 360° performance feedback.",
                n_type='System',
                icon='fa-arrows-spin',
                color='info'
            )
            
            messages.success(request, f"Feedback request sent successfully to {item['ReviewerName']}.")
        except Exception as e:
            messages.error(request, f"Error requesting feedback: {e}")
            
        return redirect('okrs')


class SubmitFeedback360View(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'okrs_appraisals'

    def post(self, request):
        feedback_id = request.POST.get('feedback_id', '').strip()
        rating = request.POST.get('rating', '').strip()
        comments = request.POST.get('comments', '').strip()
        
        if not feedback_id or not rating or not comments:
            messages.error(request, "All fields are required to submit feedback.")
            return redirect('okrs')
            
        try:
            from decimal import Decimal
            rating_val = Decimal(rating)
            if not (Decimal('1.0') <= rating_val <= Decimal('5.0')):
                raise ValueError("Rating must be between 1.0 and 5.0")
        except (ValueError, Exception) as e:
            messages.error(request, str(e))
            return redirect('okrs')
            
        try:
            from core.dynamodb_service import Feedback360Table
            from core.utils import get_local_now, send_notification
            
            # Get feedback request
            fb_item = Feedback360Table.get_item({'FeedbackID': feedback_id})
            if not fb_item:
                messages.error(request, "Feedback request not found.")
                return redirect('okrs')
                
            # Verify authorization (only reviewer can submit)
            if fb_item.get('ReviewerID') != request.user.employee_id:
                messages.error(request, "Unauthorized to submit this feedback.")
                return redirect('okrs')
                
            fb_item['Status'] = 'Submitted'
            fb_item['Rating'] = rating_val
            fb_item['Comments'] = comments
            fb_item['SubmittedAt'] = get_local_now().isoformat()
            
            Feedback360Table.put_item(fb_item)
            
            # Send notification to Reviewee
            send_notification(
                employee_id=fb_item['RevieweeID'],
                title="360° Feedback Received",
                message="A colleague has submitted 360° performance feedback for you.",
                n_type='System',
                icon='fa-thumbs-up',
                color='success'
            )
            
            messages.success(request, "Feedback submitted successfully. Thank you for your contribution!")
        except Exception as e:
            messages.error(request, f"Error submitting feedback: {e}")
            
        return redirect('okrs')


class UpdateOKRProgressView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'okrs_appraisals'
    def post(self, request):
        user = request.user
        eid = user.employee_id
        goal_id = request.POST.get('goal_id')
        current_val_str = request.POST.get('current_value')

        if not goal_id or not current_val_str:
            messages.error(request, "Goal ID and Current Value are required.")
            return redirect('okrs')

        try:
            okr = OKRsTable.get_item({'EmployeeID': eid, 'GoalID': goal_id})
            if not okr:
                messages.error(request, "OKR not found.")
                return redirect('okrs')

            old_progress = int(okr.get('Progress', 0))
            old_value = int(okr.get('CurrentValue', 0))

            current_val = int(current_val_str)
            target_val = int(okr.get('TargetValue', 100))
            if target_val <= 0:
                target_val = 100
            progress = min(100, max(0, int((current_val / target_val) * 100)))

            status = 'Completed' if progress >= 100 else 'In Progress'
            increment = progress - old_progress

            history = okr.get('ProgressHistory', [])
            
            clean_history = []
            for h in history:
                clean_history.append({
                    'Timestamp': str(h.get('Timestamp', '')),
                    'Date': str(h.get('Date', '')),
                    'PreviousValue': int(h.get('PreviousValue', 0)),
                    'CurrentValue': int(h.get('CurrentValue', 0)),
                    'PreviousProgress': int(h.get('PreviousProgress', 0)),
                    'NewProgress': int(h.get('NewProgress', 0)),
                    'Increment': int(h.get('Increment', 0))
                })

            new_entry = {
                'Timestamp': get_local_now().isoformat(),
                'Date': get_local_date().isoformat(),
                'PreviousValue': old_value,
                'CurrentValue': current_val,
                'PreviousProgress': old_progress,
                'NewProgress': progress,
                'Increment': increment
            }
            clean_history.append(new_entry)

            OKRsTable.update_item(
                Key={'EmployeeID': eid, 'GoalID': goal_id},
                UpdateExpression="SET CurrentValue = :cv, Progress = :p, #s = :s, UpdatedAt = :ua, ProgressHistory = :hist",
                ExpressionAttributeNames={'#s': 'Status'},
                ExpressionAttributeValues={
                    ':cv': current_val,
                    ':p': progress,
                    ':s': status,
                    ':ua': get_local_now().isoformat(),
                    ':hist': clean_history
                }
            )
            messages.success(request, "OKR progress updated successfully.")
        except Exception as e:
            messages.error(request, f"Error updating OKR progress: {e}")
        return redirect('okrs')

class EvaluateOKRView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'okrs_appraisals'
    def post(self, request):
        goal_id = request.POST.get('goal_id')
        target_emp_id = request.POST.get('employee_id')
        rating_str = request.POST.get('rating')
        appraisal = request.POST.get('appraisal', '').strip()

        if not goal_id or not target_emp_id or not rating_str:
            messages.error(request, "Goal ID, Employee ID, and Rating are required.")
            return redirect('okrs')

        try:
            okr = OKRsTable.get_item({'EmployeeID': target_emp_id, 'GoalID': goal_id})
            if not okr:
                messages.error(request, "OKR not found.")
                return redirect('okrs')

            from decimal import Decimal
            rating = Decimal(rating_str)
            OKRsTable.update_item(
                Key={'EmployeeID': target_emp_id, 'GoalID': goal_id},
                UpdateExpression="SET ManagerRating = :mr, ManagerAppraisal = :ma, UpdatedAt = :ua",
                ExpressionAttributeValues={
                    ':mr': rating,
                    ':ma': appraisal,
                    ':ua': get_local_now().isoformat()
                }
            )
            messages.success(request, "OKR evaluation submitted successfully.")
        except Exception as e:
            messages.error(request, f"Error submitting OKR evaluation: {e}")
        return redirect('okrs')

class SubmitSelfAppraisalView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'okrs_appraisals'
    def post(self, request):
        messages.error(request, "Self Appraisal is disabled.")
        return redirect('okrs')

class SubmitManagerReviewView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'okrs_appraisals'
    def post(self, request):
        user = request.user
        role = user.role
        
        if role not in ('Manager', 'Super admin'):
            messages.error(request, "Permission denied. Only Managers and Super Admins can perform appraisals.")
            return redirect('okrs')
            
        cycle_id = request.POST.get('cycle_id')
        employee_id = request.POST.get('employee_id')
        
        eid = user.employee_id
        if role == 'Manager':
            try:
                subordinates = ReportingHierarchyTable.scan(
                    FilterExpression="ManagerID = :mid",
                    ExpressionAttributeValues={":mid": eid}
                )
                sub_ids = {s.get('EmployeeID') for s in subordinates if s.get('EmployeeID')}
                if employee_id not in sub_ids:
                    messages.error(request, "Permission denied. You can only evaluate employees under you.")
                    return redirect('okrs')
            except Exception as e:
                messages.error(request, f"Error validating reporting hierarchy: {e}")
                return redirect('okrs')
        elif role == 'Super admin':
            try:
                users_raw = UsersTable.scan()
                emp_role_map = {u['EmployeeID']: u.get('Role') for u in users_raw if u.get('EmployeeID')}
                if emp_role_map.get(employee_id) not in ('Manager', 'HR ADMIN') and employee_id != eid:
                    messages.error(request, "Permission denied. Super Admins can only evaluate Managers and HR.")
                    return redirect('okrs')
            except Exception as e:
                messages.error(request, f"Error validating user role: {e}")
                return redirect('okrs')

        action_type = request.POST.get('action_type', 'Approve') # 'Approve' or 'Return'
        
        rating_str = request.POST.get('rating', '4.0')
        comments = request.POST.get('comments', '')
        strengths = request.POST.get('strengths', '')
        weaknesses = request.POST.get('weaknesses', '')
        
        recommend_promotion = request.POST.get('recommend_promotion') == 'on'
        recommended_designation = request.POST.get('recommended_designation', '')
        promotion_reason = request.POST.get('promotion_reason', '')
        
        recommend_salary_hike = request.POST.get('recommend_salary_hike') == 'on'
        recommended_salary_str = request.POST.get('recommended_salary', '0')
        salary_hike_reason = request.POST.get('salary_hike_reason', '')
        
        recommend_bonus = request.POST.get('recommend_bonus') == 'on'
        bonus_type = request.POST.get('bonus_type', 'None')
        bonus_amount_str = request.POST.get('bonus_amount', '0')
        
        try:
            rating = float(rating_str)
            recommended_salary = float(recommended_salary_str)
            bonus_amount = float(bonus_amount_str)
        except ValueError:
            rating = 4.0
            recommended_salary = 0.0
            bonus_amount = 0.0

        if not cycle_id or not employee_id:
            messages.error(request, "Cycle ID and Employee ID are required.")
            return redirect('okrs')
            
        try:
            appraisal = AppraisalsTable.get_item({'EmployeeID': employee_id, 'CycleID': cycle_id})
            if not appraisal:
                appraisal = {
                    'EmployeeID': employee_id,
                    'CycleID': cycle_id,
                    'SelfAppraisal': {'Achievements': 'Self Appraisal Disabled'},
                    'ManagerReview': {},
                    'HRReview': {},
                    'FounderApproval': {},
                    'AuditLog': [],
                    'CreatedAt': get_local_now().isoformat()
                }
                
            current_status = appraisal.get('Status', 'Pending Manager Review')
            if current_status not in ('Pending Manager Review', 'Submitted', 'Returned by HR', 'Returned by Manager', 'Draft'):
                messages.error(request, f"Appraisal is in state '{current_status}' and cannot be reviewed.")
                return redirect('okrs')
                
            if action_type == 'Return':
                status = 'Returned by Manager'
                remarks = "Manager returned appraisal to employee."
            else:
                status = 'Pending HR Review'
                remarks = "Manager completed review & recommendations."
                
            from decimal import Decimal
            manager_review_data = {
                'Rating': Decimal(str(rating)),
                'Comments': comments,
                'Strengths': strengths,
                'Weaknesses': weaknesses,
                'RecommendPromotion': recommend_promotion,
                'RecommendedDesignation': recommended_designation,
                'PromotionReason': promotion_reason,
                'RecommendSalaryHike': recommend_salary_hike,
                'RecommendedSalary': Decimal(str(recommended_salary)),
                'SalaryHikeReason': salary_hike_reason,
                'RecommendBonus': recommend_bonus,
                'BonusType': bonus_type,
                'BonusAmount': Decimal(str(bonus_amount)),
                'ReviewedAt': get_local_now().isoformat()
            }
            
            audit_log = appraisal.get('AuditLog', [])
            audit_log.append({
                'Action': f"Manager Review: {status}",
                'User': f"{user.first_name} {user.last_name}",
                'Timestamp': get_local_now().isoformat(),
                'PrevStatus': current_status,
                'NewStatus': status,
                'Remarks': remarks
            })
            
            appraisal.update({
                'Status': status,
                'ManagerReview': manager_review_data,
                'AuditLog': audit_log,
                'UpdatedAt': get_local_now().isoformat()
            })
            AppraisalsTable.put_item(appraisal)
            messages.success(request, f"Manager review successfully updated status to {status}.")
        except Exception as e:
            messages.error(request, f"Error saving manager review: {e}")
        return redirect('okrs')

class SubmitHRReviewView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'okrs_appraisals'
    def post(self, request):
        user = request.user
        role = user.role
        
        if role not in ('HR ADMIN', 'Super admin'):
            messages.error(request, "Permission denied.")
            return redirect('okrs')
            
        cycle_id = request.POST.get('cycle_id')
        employee_id = request.POST.get('employee_id')
        action_type = request.POST.get('action_type', 'Approve') # 'Approve' or 'Return'
        
        policy_compliance = request.POST.get('policy_compliance', '')
        budget_remarks = request.POST.get('budget_remarks', '')
        remarks = request.POST.get('remarks', '')
        
        if not cycle_id or not employee_id:
            messages.error(request, "Cycle ID and Employee ID are required.")
            return redirect('okrs')
            
        try:
            appraisal = AppraisalsTable.get_item({'EmployeeID': employee_id, 'CycleID': cycle_id})
            if not appraisal:
                messages.error(request, "Appraisal not found.")
                return redirect('okrs')
                
            current_status = appraisal.get('Status')
            if current_status != 'Pending HR Review':
                messages.error(request, "Appraisal is not pending HR review.")
                return redirect('okrs')
                
            if action_type == 'Return':
                status = 'Returned by HR'
                audit_remarks = f"HR returned appraisal. Remarks: {remarks}"
            else:
                status = 'Pending Founder Approval'
                audit_remarks = f"HR approved appraisal. Remarks: {remarks}"
                
            hr_review_data = {
                'PolicyCompliance': policy_compliance,
                'BudgetRemarks': budget_remarks,
                'Remarks': remarks,
                'ReviewedAt': get_local_now().isoformat()
            }
            
            audit_log = appraisal.get('AuditLog', [])
            audit_log.append({
                'Action': f"HR Review: {status}",
                'User': f"{user.first_name} {user.last_name}",
                'Timestamp': get_local_now().isoformat(),
                'PrevStatus': current_status,
                'NewStatus': status,
                'Remarks': audit_remarks
            })
            
            appraisal.update({
                'Status': status,
                'HRReview': hr_review_data,
                'AuditLog': audit_log,
                'UpdatedAt': get_local_now().isoformat()
            })
            AppraisalsTable.put_item(appraisal)
            messages.success(request, f"HR review successfully updated status to {status}.")
        except Exception as e:
            messages.error(request, f"Error saving HR review: {e}")
        return redirect('okrs')

class SubmitFounderApprovalView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'okrs_appraisals'
    def post(self, request):
        user = request.user
        role = user.role
        
        if role not in ('Super admin', 'HR ADMIN'):
            messages.error(request, "Permission denied.")
            return redirect('okrs')
            
        cycle_id = request.POST.get('cycle_id')
        employee_id = request.POST.get('employee_id')
        action_type = request.POST.get('action_type', 'Approve') # 'Approve', 'Reject', 'Return', 'Override'
        
        override_rating_str = request.POST.get('override_rating', '')
        override_salary_str = request.POST.get('override_salary', '')
        override_bonus_str = request.POST.get('override_bonus_amount', '')
        approve_promotion = request.POST.get('approve_promotion') == 'on'
        approve_salary_hike = request.POST.get('approve_salary_hike') == 'on'
        approve_bonus = request.POST.get('approve_bonus') == 'on'
        remarks = request.POST.get('remarks', '')
        
        if not cycle_id or not employee_id:
            messages.error(request, "Cycle ID and Employee ID are required.")
            return redirect('okrs')
            
        try:
            appraisal = AppraisalsTable.get_item({'EmployeeID': employee_id, 'CycleID': cycle_id})
            if not appraisal:
                messages.error(request, "Appraisal not found.")
                return redirect('okrs')
                
            current_status = appraisal.get('Status')
            if current_status != 'Pending Founder Approval':
                messages.error(request, "Appraisal is not pending Founder approval.")
                return redirect('okrs')
                
            if action_type == 'Return':
                status = 'Draft'
                audit_remarks = f"Founder returned appraisal. Remarks: {remarks}"
            elif action_type == 'Reject':
                status = 'Rejected'
                audit_remarks = f"Founder rejected appraisal. Remarks: {remarks}"
            else:
                status = 'Approved'
                audit_remarks = f"Founder approved appraisal. Remarks: {remarks}"
                
            from decimal import Decimal
            override_rating = Decimal(override_rating_str) if override_rating_str else None
            override_salary = Decimal(override_salary_str) if override_salary_str else None
            override_bonus = Decimal(override_bonus_str) if override_bonus_str else None
            
            founder_approval_data = {
                'OverrideRating': override_rating,
                'OverrideSalary': override_salary,
                'OverrideBonusAmount': override_bonus,
                'ApprovePromotion': approve_promotion,
                'ApproveSalaryHike': approve_salary_hike,
                'ApproveBonus': approve_bonus,
                'Remarks': remarks,
                'ApprovedAt': get_local_now().isoformat()
            }
            
            audit_log = appraisal.get('AuditLog', [])
            audit_log.append({
                'Action': f"Founder Approval: {status}",
                'User': f"{user.first_name} {user.last_name}",
                'Timestamp': get_local_now().isoformat(),
                'PrevStatus': current_status,
                'NewStatus': status,
                'Remarks': audit_remarks
            })
            
            appraisal.update({
                'Status': status,
                'FounderApproval': founder_approval_data,
                'AuditLog': audit_log,
                'UpdatedAt': get_local_now().isoformat()
            })
            
            AppraisalsTable.put_item(appraisal)
            
            # Apply changes to employee profile if approved
            if status == 'Approved':
                emp = EmployeesTable.get_item({'EmployeeID': employee_id})
                if emp:
                    mgr_rev = appraisal.get('ManagerReview', {})
                    
                    # Update designation
                    if approve_promotion:
                        old_desig = emp.get('Designation', 'Employee')
                        new_desig = mgr_rev.get('RecommendedDesignation', old_desig)
                        
                        promo_history = emp.get('PromotionHistory', [])
                        promo_history.append({
                            'Date': get_local_date().isoformat(),
                            'CycleID': cycle_id,
                            'PreviousDesignation': old_desig,
                            'NewDesignation': new_desig,
                            'Reason': mgr_rev.get('PromotionReason', 'Performance appraisal recommendation')
                        })
                        emp['Designation'] = new_desig
                        emp['PromotionHistory'] = promo_history
                        
                    # Update salary
                    if approve_salary_hike:
                        old_sal = float(emp.get('Salary', 0))
                        new_sal = float(override_salary or mgr_rev.get('RecommendedSalary', old_sal))
                        hike_pct = ((new_sal - old_sal) / old_sal * 100) if old_sal > 0 else 0.0
                        
                        salary_history = emp.get('SalaryHistory', [])
                        salary_history.append({
                            'Date': get_local_date().isoformat(),
                            'CycleID': cycle_id,
                            'PreviousSalary': Decimal(str(old_sal)),
                            'NewSalary': Decimal(str(new_sal)),
                            'HikePercentage': Decimal(str(round(hike_pct, 2))),
                            'Reason': mgr_rev.get('SalaryHikeReason', 'Performance appraisal salary revision')
                        })
                        emp['Salary'] = Decimal(str(new_sal))
                        emp['SalaryHistory'] = salary_history
                        
                    # Add bonus to letter/records if approved
                    if approve_bonus:
                        # Bonus logic, can trigger spot awards, festivals, spots, retentions
                        pass
                        
                    EmployeesTable.put_item(emp)
                    
            messages.success(request, f"Founder decision '{status}' submitted successfully.")
        except Exception as e:
            messages.error(request, f"Error saving Founder decision: {e}")
        return redirect('okrs')

class ManageAppraisalCyclesView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'okrs_appraisals'
    def post(self, request):
        user = request.user
        role = user.role
        
        if role not in ('HR ADMIN', 'Super admin'):
            messages.error(request, "Permission denied.")
            return redirect('okrs')
            
        cycle_id = request.POST.get('cycle_id')
        name = request.POST.get('name')
        cycle_type = request.POST.get('type', 'Quarterly')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        sub_deadline = request.POST.get('submission_deadline')
        rev_deadline = request.POST.get('review_deadline')
        app_deadline = request.POST.get('approval_deadline')
        status = request.POST.get('status', 'Active')
        
        if not cycle_id or not name:
            messages.error(request, "Cycle ID and Name are required.")
            return redirect('okrs')
            
        try:
            item = {
                'CycleID': cycle_id,
                'Name': name,
                'Type': cycle_type,
                'StartDate': start_date,
                'EndDate': end_date,
                'SubmissionDeadline': sub_deadline,
                'ReviewDeadline': rev_deadline,
                'ApprovalDeadline': app_deadline,
                'Status': status
            }
            AppraisalCyclesTable.put_item(item)
            messages.success(request, f"Appraisal cycle '{name}' saved successfully.")
        except Exception as e:
            messages.error(request, f"Error saving appraisal cycle: {e}")
        return redirect('okrs')

class DownloadAppraisalLetterView(FeatureRequiredMixin, LoginRequiredMixin, View):
    required_feature = 'okrs_appraisals'
    def get(self, request, employee_id, cycle_id, type):
        user = request.user
        role = user.role
        
        if role not in ('Super admin', 'HR ADMIN') and user.employee_id != employee_id:
            return HttpResponse("Unauthorized", status=401)
            
        try:
            emp_details = EmployeesTable.get_item({'EmployeeID': employee_id})
            appraisal = AppraisalsTable.get_item({'EmployeeID': employee_id, 'CycleID': cycle_id})
            
            if not emp_details or not appraisal:
                return HttpResponse("Not Found", status=404)
                
            name = f"{emp_details.get('FirstName', '')} {emp_details.get('LastName', '')}"
            date_str = get_local_date().strftime('%d %B %Y')
            
            if type == 'promotion':
                title = "PROMOTION LETTER"
                body = f"""
                <p>Dear {name},</p>
                <p>Based on your exceptional performance appraisal for cycle {cycle_id}, we are pleased to promote you to the designation of <strong>{emp_details.get('Designation')}</strong> effective immediately.</p>
                <p>We appreciate your dedication, commitment, and achievements in Completed Projects, and hope you continue to excel in your new role.</p>
                """
            elif type == 'salary':
                title = "SALARY REVISION LETTER"
                body = f"""
                <p>Dear {name},</p>
                <p>We are pleased to inform you that your compensation structure has been revised following your performance appraisal for cycle {cycle_id}.</p>
                <p>Your new annual CTC will be INR <strong>{emp_details.get('Salary')}</strong>.</p>
                <p>All other terms and conditions of your employment contract remain unchanged.</p>
                """
            else:
                title = "PERFORMANCE APPRAISAL LETTER"
                mgr_rev = appraisal.get('ManagerReview', {})
                body = f"""
                <p>Dear {name},</p>
                <p>This letter is in reference to your performance appraisal review for the cycle {cycle_id}.</p>
                <p>We are happy to share that you achieved a score of <strong>{mgr_rev.get('Rating', appraisal.get('FounderApproval', {}).get('OverrideRating', '4.0'))} / 5.0</strong>.</p>
                <p>Manager Remarks: "{mgr_rev.get('Comments', '')}"</p>
                """
                
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; padding: 40px; color: #333; }}
                    .letterhead {{ border-bottom: 2px solid #0056b3; padding-bottom: 20px; margin-bottom: 40px; }}
                    .logo {{ font-size: 24px; font-weight: bold; color: #0056b3; }}
                    .date {{ text-align: right; margin-bottom: 20px; }}
                    .title {{ text-align: center; font-size: 20px; font-weight: bold; margin-bottom: 30px; text-decoration: underline; }}
                    .content {{ line-height: 1.6; margin-bottom: 40px; }}
                    .signature {{ margin-top: 50px; }}
                    @media print {{ body {{ padding: 0; }} }}
                </style>
            </head>
            <body onload="window.print()">
                <div class="letterhead">
                    <div class="logo">Lurnexa Technologies</div>
                    <div>HR Department</div>
                </div>
                <div class="date">Date: {date_str}</div>
                <div class="title">{title}</div>
                <div class="content">{body}</div>
                <div class="signature">
                    <p>Sincerely,</p>
                    <p><strong>HR Department</strong><br>Lurnexa Technologies</p>
                </div>
            </body>
            </html>
            """
            return HttpResponse(html_content)
        except Exception as e:
            return HttpResponse(f"Error: {e}", status=500)

from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json

@method_decorator(csrf_exempt, name='dispatch')
class RegisterDeviceView(LoginRequiredMixin, View):
    def post(self, request):
        user_emp_id = request.user.employee_id
        if not user_emp_id:
            return JsonResponse({'success': False, 'error': 'No employee profile associated.'}, status=400)
        try:
            data = json.loads(request.body)
            token = data.get('token')
            platform = data.get('platform', 'android')
            if not token:
                return JsonResponse({'success': False, 'error': 'Token is required.'}, status=400)
            
            from core.dynamodb_service import DeviceTokensTable
            from core.utils import get_local_now
            
            DeviceTokensTable.put_item({
                'EmployeeID': user_emp_id,
                'DeviceToken': token,
                'Platform': platform,
                'LastUpdated': get_local_now().isoformat()
            })
            return JsonResponse({'success': True, 'message': 'Device registered successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class UnregisterDeviceView(LoginRequiredMixin, View):
    def post(self, request):
        user_emp_id = request.user.employee_id
        if not user_emp_id:
            return JsonResponse({'success': False, 'error': 'No employee profile associated.'}, status=400)
        try:
            data = json.loads(request.body)
            token = data.get('token')
            if not token:
                return JsonResponse({'success': False, 'error': 'Token is required.'}, status=400)
                
            from core.dynamodb_service import DeviceTokensTable
            DeviceTokensTable.delete_item({
                'EmployeeID': user_emp_id,
                'DeviceToken': token
            })
            return JsonResponse({'success': True, 'message': 'Device unregistered successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class TestPushNotificationView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            token = data.get('token')
            if not token:
                return JsonResponse({'success': False, 'error': 'Token is required.'}, status=400)
            
            import firebase_admin
            from firebase_admin import messaging
            
            message_payload = messaging.Message(
                notification=messaging.Notification(
                    title='Lurnexa Push Diagnostics',
                    body='Congratulations! Firebase Push Notifications are working perfectly on this device.',
                ),
                android=messaging.AndroidConfig(
                    notification=messaging.AndroidNotification(
                        sound='default',
                        channel_id='fcm_default_channel'
                    )
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound='default'
                        )
                    )
                ),
                data={
                    'title': 'Lurnexa Push Diagnostics',
                    'body': 'Congratulations! Firebase Push Notifications are working perfectly on this device.',
                    'type': 'Announcement',
                    'route': '/core/notifications/',
                    'sender_avatar_url': ''
                },
                token=token
            )
            response = messaging.send(message_payload)
            return JsonResponse({'success': True, 'message': 'Test push sent successfully.', 'response': str(response)})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


from django.views import View
import uuid
import datetime
from auth_custom.mixins import SuperAdminRequiredMixin
from core.dynamodb_service import DepartmentsTable

class ManageDepartmentsView(SuperAdminRequiredMixin, View):
    def get(self, request):
        org_id = request.user.org_id
        try:
            departments = DepartmentsTable.scan(
                FilterExpression="OrgID = :oid",
                ExpressionAttributeValues={":oid": org_id}
            )
        except Exception:
            departments = []

        # Sort departments by Name
        departments = sorted(departments, key=lambda x: x.get('Name', '').lower())

        return render(request, 'core/manage_departments.html', {
            'departments': departments
        })

    def post(self, request):
        org_id = request.user.org_id
        action = request.POST.get('action')

        if action == 'create_department':
            dept_name = request.POST.get('department_name', '').strip()
            dept_desc = request.POST.get('department_desc', '').strip()
            if not dept_name:
                messages.error(request, "Department name is required.")
                return redirect('manage_departments')

            dept_id = f"DEPT-{uuid.uuid4().hex[:6].upper()}"
            dept_item = {
                'OrgID': org_id,
                'DepartmentID': dept_id,
                'Name': dept_name,
                'Description': dept_desc,
                'CreatedAt': datetime.datetime.utcnow().isoformat()
            }
            try:
                DepartmentsTable.put_item(dept_item)
                messages.success(request, f"Department '{dept_name}' created successfully.")
            except Exception as e:
                messages.error(request, f"Error creating department: {e}")

        elif action == 'delete_department':
            dept_id = request.POST.get('department_id', '').strip()
            try:
                DepartmentsTable.delete_item({'OrgID': org_id, 'DepartmentID': dept_id})
                messages.success(request, "Department deleted successfully.")
            except Exception as e:
                messages.error(request, f"Error deleting department: {e}")

        return redirect('manage_departments')



