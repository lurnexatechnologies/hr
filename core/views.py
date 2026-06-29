from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.generic import TemplateView
from auth_custom.mixins import HRRequiredMixin, ManagerRequiredMixin, LoginRequiredMixin, ApprovedOnboardingMixin, SuperAdminRequiredMixin
import datetime
import uuid
import csv
from boto3.dynamodb.conditions import Key
from core.dynamodb_service import (
    EmployeesTable, ReportingHierarchyTable, LeaveRequestsTable, 
    ExpensesTable, AttendanceTable, HolidaysTable, PoliciesTable, 
    ResignationsTable, NotificationsTable, WFHRequestsTable,
    UsersTable, LoginHistoryTable, PayrollApprovalsTable
)
from core.utils import send_notification, refresh_monthly_leaves, get_initial_leave_balance, safe_float

class HRDashboardView(HRRequiredMixin, TemplateView):
    template_name = 'core/hr_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today_date = datetime.date.today()
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
            payroll_queue = [p for p in PayrollApprovalsTable.scan() if p.get('Status') == 'Pending Super Admin']
            for p in payroll_queue:
                approvals.append({
                    'title': 'Payroll Batch',
                    'subtitle': f"{p.get('MonthYear')} Authorization Required",
                    'badge': 'Payroll',
                    'url': 'payroll_dashboard'
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
        
        return context

class SuperAdminDashboardView(HRDashboardView):
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
        pending_batches = [r for r in payroll_requests if r.get('Status') == 'Pending Super Admin Approval']
        
        pending_list = context.get('pending_approvals', [])
        for r in pending_batches:
            # Check if this batch is already in the list to avoid duplicates if HRDashboardView already added it
            if not any(item.get('title') == f"Payroll Batch: {r.get('Month')} {r.get('Year')}" for item in pending_list):
                pending_list.insert(0, {
                    'title': f"Payroll Batch: {r.get('Month')} {r.get('Year')}",
                    'subtitle': f"Net Disbursement: ₹{float(r.get('TotalNetPay', 0)):,.2f}",
                    'badge': 'Payroll',
                    'url': 'payroll_approval_list'
                })
        context['pending_approvals'] = pending_list
        
        return context

class ManagerDashboardView(ManagerRequiredMixin, TemplateView):
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

class EmployeeDashboardView(LoginRequiredMixin, ApprovedOnboardingMixin, TemplateView):
    template_name = 'core/employee_dashboard.html'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        today = datetime.date.today().isoformat()
        
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

class ExportEmployeesCSVView(HRRequiredMixin, View):
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

class SettingsView(LoginRequiredMixin, TemplateView):
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

            # If user is a Manager, they can pick their Reporting HR
            if user.role == 'Manager':
                all_users = UsersTable.scan()
                all_employees = EmployeesTable.scan()
                hr_list = []
                for u in all_users:
                    if u.get('Role') == 'HR ADMIN':
                        emp = next((e for e in all_employees if e.get('EmployeeID') == u.get('EmployeeID')), None)
                        if emp:
                            hr_list.append({
                                'EmployeeID': emp['EmployeeID'],
                                'Name': f"{emp.get('FirstName')} {emp.get('LastName')}"
                            })
                context['hr_list'] = hr_list
                
                # Fetch current selection
                hierarchy = ReportingHierarchyTable.scan(
                    FilterExpression="EmployeeID = :eid",
                    ExpressionAttributeValues={":eid": user.employee_id}
                )
                if hierarchy:
                    context['current_hr_id'] = hierarchy[0].get('ManagerID')

        except Exception as e:
            print(f"Error in Settings context: {e}")
            context['login_history'] = []
        return context

    def post(self, request):
        user = request.user
        action = request.POST.get('action')
        
        if action == 'update_reporting':
            if user.role == 'Super admin':
                messages.error(request, "Super admin cannot have a reporting HR.")
                return redirect('settings')
                
            hr_id = request.POST.get('hr_id')
            if hr_id:
                from core.dynamodb_service import ReportingHierarchyTable
                # Remove existing
                existing = ReportingHierarchyTable.scan(
                    FilterExpression="EmployeeID = :eid",
                    ExpressionAttributeValues={":eid": user.employee_id}
                )
                for item in existing:
                    ReportingHierarchyTable.delete_item({'ManagerID': item['ManagerID'], 'EmployeeID': user.employee_id})
                
                # Add new
                ReportingHierarchyTable.put_item({
                    'ManagerID': hr_id,
                    'EmployeeID': user.employee_id
                })
                messages.success(request, "Reporting HR updated successfully.")
            return redirect('settings')
            
        # Basic Profile Update
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        passport_photo = request.FILES.get('passport_photo')
        
        from core.dynamodb_service import UsersTable, EmployeesTable
        from django.core.files.storage import FileSystemStorage
        import os

        # 1. Update User Record
        user_record = UsersTable.get_item({'UserID': user.user_id})
        if user_record:
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
                
        messages.success(request, "Account settings updated successfully.")
        return redirect('settings')

class NotificationsView(LoginRequiredMixin, TemplateView):
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

class DeleteNotificationView(LoginRequiredMixin, View):
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

class NotificationDetailView(LoginRequiredMixin, TemplateView):
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

class LoadMoreNotificationsView(LoginRequiredMixin, View):
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

import json

class PoliciesView(LoginRequiredMixin, TemplateView):
    template_name = 'core/policies.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            policies = PoliciesTable.scan()
            context['policies'] = policies
            
            # Create a clean JSON version for the JS layer
            js_data = {}
            for p in policies:
                js_data[p['PolicyID']] = {
                    'title': p.get('Title', ''),
                    'description': p.get('Description', ''),
                    'content': p.get('Content', ''),
                    'gradient': p.get('Gradient', ''),
                    'icon': p.get('Icon', 'fa-file-lines'),
                    'color': p.get('Color', '#1a4f8b')
                }
            context['policies_json'] = json.dumps(js_data)
        except Exception:
            context['policies'] = []
            context['policies_json'] = '{}'
        return context

class AddPolicyView(HRRequiredMixin, View):
    def post(self, request):
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot add policies.")
            return redirect('policies')
        title = request.POST.get('title')
        description = request.POST.get('description')
        content = request.POST.get('content')
        icon = request.POST.get('icon', 'fa-file-lines')
        color = request.POST.get('color', '#1a4f8b')
        
        policy_item = {
            'PolicyID': str(uuid.uuid4()),
            'Title': title,
            'Description': description,
            'Content': content,
            'Icon': icon,
            'Color': color,
            'Gradient': f"linear-gradient(135deg, {color}22 0%, {color}44 100%)",
            'CreatedAt': datetime.datetime.now().isoformat()
        }
        
        try:
            PoliciesTable.put_item(policy_item)
            messages.success(request, f"Policy '{title}' added successfully.")
        except Exception as e:
            messages.error(request, f"Error adding policy: {str(e)}")
            
        return redirect('policies')

class EditPolicyView(HRRequiredMixin, View):
    def post(self, request, policy_id):
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot modify policies.")
            return redirect('policies')
        title = request.POST.get('title')
        description = request.POST.get('description')
        content = request.POST.get('content')
        icon = request.POST.get('icon', 'fa-file-lines')
        color = request.POST.get('color', '#1a4f8b')
        
        try:
            PoliciesTable.update_item(
                Key={'PolicyID': policy_id},
                UpdateExpression="SET #t = :t, Description = :d, Content = :c, Icon = :i, Color = :co, Gradient = :g",
                ExpressionAttributeNames={'#t': 'Title'},
                ExpressionAttributeValues={
                    ':t': title,
                    ':d': description,
                    ':c': content,
                    ':i': icon,
                    ':co': color,
                    ':g': f"linear-gradient(135deg, {color}22 0%, {color}44 100%)"
                }
            )
            messages.success(request, f"Policy '{title}' updated successfully.")
        except Exception as e:
            messages.error(request, f"Error updating policy: {str(e)}")
            
        return redirect('policies')

class DeletePolicyView(HRRequiredMixin, View):
    def post(self, request):
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot delete policies.")
            return redirect('policies')
        policy_id = request.POST.get('policy_id', '').strip()
        if not policy_id:
            messages.error(request, "Error: No Policy ID provided.")
            return redirect('policies')
            
        try:
            print(f"DEBUG: Deleting policy from DynamoDB with ID: '{policy_id}'")
            # Attempt to delete from DynamoDB
            response = PoliciesTable.delete_item({'PolicyID': policy_id})
            print(f"DEBUG: DynamoDB response: {response}")
            messages.success(request, "Policy has been successfully deleted from the database.")
        except Exception as e:
            print(f"DEBUG: Exception during deletion: {e}")
            messages.error(request, f"Critical Database Error during deletion: {str(e)}")
            
        return redirect('policies')

class GlobalSearchView(LoginRequiredMixin, TemplateView):
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

class ClearNotificationsView(LoginRequiredMixin, View):
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

class SuperAdminApprovalsView(SuperAdminRequiredMixin, TemplateView):
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
            payroll_queue = [p for p in PayrollApprovalsTable.scan() if p.get('Status') == 'Pending Super Admin']
            for p in payroll_queue:
                approvals.append({
                    'title': 'Payroll Batch Authorization',
                    'subtitle': f"{p.get('MonthYear')} Financial Liability",
                    'detail': f"Total Disbursement: ₹{p.get('TotalGross')}",
                    'badge': 'Payroll',
                    'badge_class': 'success',
                    'icon': 'fa-money-bill-transfer',
                    'url': 'payroll_dashboard',
                    'date': p.get('SubmissionDate', 'Recent')
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

class HRGenerateLetterView(HRRequiredMixin, View):
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
                'GeneratedDate': datetime.datetime.now().isoformat(),
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
                        <img src="{logo_base64}" alt="Logo" style="height: 35px; width: auto; vertical-align: middle; margin-right: 8px;" />
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
            'GeneratedDate': datetime.datetime.now().isoformat(),
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


class HRSendLetterEmailView(HRRequiredMixin, View):
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
        message = request.POST.get('message', '')
        
        try:
            from django.core.mail import EmailMessage
            from django.conf import settings
            
            subject = f"New Enterprise Inquiry: {first_name} {last_name}"
            body = f"Hello Lurnexa Team,\n\nYou have received a new enterprise inquiry from the Lurnexa HRMS landing page.\n\nContact Details:\n----------------\nName: {first_name} {last_name}\nWork Email: {email}\n\nMessage:\n--------\n{message}\n\n---\nThis is an automated system notification generated by the Lurnexa Platform."
            
            email_msg = EmailMessage(
                subject=subject,
                body=body,
                from_email='lurnexasolution@gmail.com',
                to=['lurnexasolution@gmail.com'],
                reply_to=[email]
            )
            email_msg.send(fail_silently=False)
            messages.success(request, "Your message has been sent successfully! Our team will get back to you soon.")
        except Exception as e:
            messages.error(request, "There was an error sending your message. Please try again later.")
            
        return redirect('/#contact')
