from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.contrib import messages
from django.views import View
from django.views.generic import TemplateView
from auth_custom.mixins import LoginRequiredMixin, HRRequiredMixin, ManagerRequiredMixin, ApprovedOnboardingMixin
from core.dynamodb_service import UsersTable, EmployeesTable, LeaveRequestsTable, ReportingHierarchyTable, HolidaysTable
from core.utils import send_notification, refresh_monthly_leaves, get_initial_leave_balance, safe_float, get_local_date, get_local_now
from boto3.dynamodb.conditions import Key
import datetime
import uuid
from django.core.files.storage import default_storage


class AddHolidayView(HRRequiredMixin, View):
    def post(self, request):
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot add holidays.")
            return redirect('company_calendar')
        name = request.POST.get('name')
        date = request.POST.get('date')
        h_type = request.POST.get('type', 'National')
        description = request.POST.get('description', '')
        
        holiday_item = {
            'HolidayID': str(uuid.uuid4()),
            'HolidayDate': date,
            'Name': name,
            'Type': h_type,
            'Description': description
        }
        HolidaysTable.put_item(holiday_item)
        
        # --- Holiday Notification ---
        # Notify all active employees about the new holiday addition.
        try:
            from core.utils import send_notification
            from core.dynamodb_service import EmployeesTable
            
            all_employees = EmployeesTable.scan()
            for emp in all_employees:
                # We send to the DB for the dashboard bell icon
                send_notification(
                    employee_id=emp['EmployeeID'],
                    title="New Holiday Added! 🎉",
                    message=f"HR has added a new holiday: {name} on {date}.",
                    n_type='Holiday',
                    icon='fa-umbrella-beach',
                    color='info',
                    email_subject=f"New Holiday: {name}",
                    email_body=f"Hi {emp.get('FirstName', '')},\n\nPlease note that a new holiday has been added to the company calendar.\n\nHoliday: {name}\nDate: {date}\nType: {h_type}\n\nBest regards,\nLurnexa HR Admin"
                )
        except Exception as e:
            print(f"Error sending holiday notifications: {e}")

        messages.success(request, f"Holiday '{name}' added successfully and notifications sent.")
        return redirect('company_calendar')

class DeleteHolidayView(HRRequiredMixin, View):
    def get(self, request, holiday_id):
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot delete holidays.")
            return redirect('company_calendar')
        HolidaysTable.delete_item({'HolidayID': holiday_id})
        messages.success(request, "Holiday deleted.")
        return redirect('company_calendar')

class EditHolidayView(HRRequiredMixin, View):
    def post(self, request, holiday_id):
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot modify holidays.")
            return redirect('company_calendar')
        name = request.POST.get('name')
        date = request.POST.get('date')
        h_type = request.POST.get('type', 'National')
        description = request.POST.get('description', '')
        
        try:
            HolidaysTable.update_item(
                Key={'HolidayID': holiday_id},
                UpdateExpression="SET #n = :n, HolidayDate = :d, #t = :t, Description = :desc",
                ExpressionAttributeNames={'#n': 'Name', '#t': 'Type'},
                ExpressionAttributeValues={
                    ':n': name,
                    ':d': date,
                    ':t': h_type,
                    ':desc': description
                }
            )
            messages.success(request, f"Holiday updated successfully.")
        except Exception as e:
            messages.error(request, f"Error updating holiday: {str(e)}")
            
        return redirect('company_calendar')

import json

class GlobalCalendarView(LoginRequiredMixin, ApprovedOnboardingMixin, TemplateView):
    template_name = 'leave/calendar.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        events = []
        
        # 1. Add Holidays (Single Blue Dot per Holiday)
        holidays = HolidaysTable.scan()
        sorted_holidays = sorted(holidays, key=lambda x: x.get('HolidayDate', ''))
        for h in sorted_holidays:
            # Add formatted date for sidebar display
            try:
                dt = datetime.datetime.strptime(h.get('HolidayDate'), '%Y-%m-%d')
                h['MonthName'] = dt.strftime('%b') # Jan, Feb, etc.
                h['Day'] = dt.strftime('%d')
            except:
                h['MonthName'] = h.get('HolidayDate', '')[5:7]
                h['Day'] = h.get('HolidayDate', '')[8:10]

            events.append({
                'title': h.get('Name'),
                'start': h.get('HolidayDate'),
                'allDay': True,
                'color': '#4f46e5', # Blue/Indigo dot
                'extendedProps': {
                    'id': h.get('HolidayID'),
                    'type': 'Holiday',
                    'category': h.get('Type', 'Company'),
                    'description': h.get('Description', '')
                }
            })
            
        # 2. Group Approved Leaves by Date
        all_leaves = LeaveRequestsTable.scan()
        approved_leaves = [l for l in all_leaves if l.get('Status') == 'Approved']
        
        if user.role == 'Employee':
            display_leaves = [l for l in approved_leaves if l.get('EmployeeID') == user.employee_id]
        else:
            display_leaves = approved_leaves
            
        all_emps = EmployeesTable.scan()
        emp_map = {e['EmployeeID']: f"{e.get('FirstName', '')} {e.get('LastName', '')}" for e in all_emps}

        # Map to group leaves by their START dates only (as requested)
        date_leaves_map = {}

        for l in display_leaves:
            d_str = l.get('LeaveDate')
            if d_str not in date_leaves_map:
                date_leaves_map[d_str] = []
            
            emp_name = emp_map.get(l.get('EmployeeID'), l.get('EmployeeID'))
            leave_info = {
                'employee': emp_name,
                'type': l.get('Type'),
                'isHalfDay': l.get('IsHalfDay', False),
                'session': l.get('HalfDaySession', ''),
                'reason': l.get('Reason', ''),
                'startDate': l.get('LeaveDate'),
                'endDate': l.get('EndDate')
            }
            # Avoid duplicates
            if not any(x['employee'] == emp_name for x in date_leaves_map[d_str]):
                date_leaves_map[d_str].append(leave_info)

        # Create one Green Dot event per date that has leaves starting on it
        for d_str, leaves_list in date_leaves_map.items():
            events.append({
                'title': f"{len(leaves_list)} Member(s) starting Leave",
                'start': d_str,
                'allDay': True,
                'color': '#10b981', # Green dot
                'extendedProps': {
                    'type': 'LeaveBatch',
                    'leaves': leaves_list
                }
            })
            
        context['calendar_events_json'] = json.dumps(events)
        context['holidays'] = sorted_holidays
        return context

class ApplyLeaveView(LoginRequiredMixin, ApprovedOnboardingMixin, View):
    def get(self, request):
        if request.user.role == 'Super admin':
            messages.error(request, "Access Denied: Super admin cannot apply for leaves.")
            return redirect('super_admin_dashboard')
        user = request.user
        employee = EmployeesTable.get_item({'EmployeeID': user.employee_id})
        
        if employee:
            # Refresh if needed
            if refresh_monthly_leaves(employee):
                employee = EmployeesTable.get_item({'EmployeeID': user.employee_id})

        # Fetch all leaves to calculate pending days
        existing_leaves = LeaveRequestsTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(user.employee_id)
        )
        
        pending_pl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and ('Earned Leave' in l.get('Type', '') or 'Paid Leave' in l.get('Type', '')))
        pending_sl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and 'Sick Leave' in l.get('Type', ''))
        pending_cl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and 'Casual Leave' in l.get('Type', ''))
        pending_co = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and ('Comp' in l.get('Type', '') or 'Comp' in l.get('LeaveType', '')))

        # Fetch all holiday dates for frontend validation
        holidays = HolidaysTable.scan()
        holiday_dates = [h['HolidayDate'] for h in holidays]

        gender = employee.get('Gender', 'Male')
        parental_type = 'Maternity Leave' if gender == 'Female' else 'Paternity Leave'

        # Spent calculations (Approved leaves)
        spent_pl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and ('Earned Leave' in l.get('Type', '') or 'Paid Leave' in l.get('Type', '')))
        spent_sl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and 'Sick Leave' in l.get('Type', ''))
        spent_cl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and 'Casual Leave' in l.get('Type', ''))
        spent_marriage = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and 'Marriage Leave' in l.get('Type', ''))
        spent_parental = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and ('Maternity' in l.get('Type', '') or 'Paternity' in l.get('Type', '')))
        spent_unpaid = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Approved' and 'Unpaid Leave' in l.get('Type', ''))
        from attendance.utils import get_active_compoff_balance
        co_details = get_active_compoff_balance(employee)
        balance_co_effective = co_details['effective_balance']
        spent_co = co_details['spent_balance']

        # Default balances if not set
        context = {
            'balance_pl': float(employee.get('Balance_PL') or 0.0) - pending_pl,
            'balance_sl': float(employee.get('Balance_SL', get_initial_leave_balance(employee, 'SL'))) - pending_sl,
            'balance_cl': float(employee.get('Balance_CL', get_initial_leave_balance(employee, 'CL'))) - pending_cl,
            'balance_co': balance_co_effective,
            'spent_pl': spent_pl,
            'spent_sl': spent_sl,
            'spent_cl': spent_cl,
            'spent_marriage': spent_marriage,
            'spent_parental': spent_parental,
            'spent_unpaid': spent_unpaid,
            'spent_co': spent_co,
            'holiday_dates': json.dumps(holiday_dates),
            'parental_leave_type': parental_type,
            'gender': gender,
            'is_intern': employee.get('EmploymentType') == 'Intern',
            'has_marriage_leave': any(l.get('Type') == 'Marriage Leave' and l.get('Status') != 'Rejected' for l in existing_leaves) if not employee.get('AllowSecondMarriage') else False,
            'has_parental_leave': any((l.get('Type') == 'Maternity Leave' or l.get('Type') == 'Paternity Leave') and l.get('Status') != 'Rejected' for l in existing_leaves) if not employee.get('AllowSecondParental') else False
        }
        return render(request, 'leave/apply.html', context)

    def post(self, request):
        if request.user.role == 'Super admin':
            return redirect('hr_dashboard')
        leave_type = request.POST.get('leave_type')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        reason = request.POST.get('reason')
        is_half_day = request.POST.get('is_half_day') == 'true'
        half_day_session = request.POST.get('half_day_session') if is_half_day else None
        
        user = request.user
        employee = EmployeesTable.get_item({'EmployeeID': user.employee_id})
        if employee:
            refresh_monthly_leaves(employee)
            if employee.get('EmploymentType') == 'Intern' and leave_type != 'Unpaid Leave':
                messages.error(request, "Interns can only apply for Unpaid Leave.")
                return redirect('apply_leave')
            
        user_emp_id = user.employee_id
        
        # Fetch all holiday dates
        holidays = HolidaysTable.scan()
        holiday_dates = {h['HolidayDate'] for h in holidays}
        
        # --- Weekend and Holiday validation (server-side) ---
        try:
            start_dt = datetime.datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d')
        except (ValueError, TypeError):
            messages.error(request, "Invalid date format. Please select valid dates.")
            return redirect('apply_leave')
        
        # Validate Start Date
        if start_dt.weekday() >= 5:  # 5=Saturday, 6=Sunday
            messages.error(request, "Start date falls on a weekend. Please select a weekday.")
            return redirect('apply_leave')
        if start_date in holiday_dates:
            messages.error(request, f"Start date ({start_date}) is a public holiday. You cannot apply for leave on a holiday.")
            return redirect('apply_leave')
            
        # Validate End Date
        if end_dt.weekday() >= 5:
            messages.error(request, "End date falls on a weekend. Please select a weekday.")
            return redirect('apply_leave')
        if end_date in holiday_dates:
            messages.error(request, f"End date ({end_date}) is a public holiday.")
            return redirect('apply_leave')
        
        # Calculate working days (Excluding weekends and holidays)
        if is_half_day:
            working_days = 0.5
            end_date = start_date # Ensure end date is same for half day
        else:
            working_days = 0
            current = start_dt
            while current <= end_dt:
                curr_str = current.strftime('%Y-%m-%d')
                if current.weekday() < 5 and curr_str not in holiday_dates:
                    working_days += 1
                current += datetime.timedelta(days=1)
        
        if working_days == 0:
            messages.error(request, "The selected range contains no working days (all are holidays or weekends).")
            return redirect('apply_leave')
        
        # --- Overlap validation ---
        existing_leaves = LeaveRequestsTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(user_emp_id)
        )
        for l in existing_leaves:
            if l.get('Status') == 'Rejected':
                continue
            
            try:
                l_start = datetime.datetime.strptime(l['LeaveDate'], '%Y-%m-%d')
                l_end = datetime.datetime.strptime(l['EndDate'], '%Y-%m-%d')
                
                # Check overlap: (StartA <= EndB) and (EndA >= StartB)
                if (start_dt <= l_end) and (end_dt >= l_start):
                    messages.error(request, f"Overlap detected: You already have a {l.get('Status')} leave from {l['LeaveDate']} to {l['EndDate']}.")
                    return redirect('apply_leave')
            except (ValueError, KeyError):
                continue

        # --- Overlap validation with WFH ---
        from core.dynamodb_service import WFHRequestsTable
        existing_wfh = WFHRequestsTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(user_emp_id)
        )
        for w in existing_wfh:
            if w.get('Status') == 'Rejected': continue
            try:
                w_start_str = w.get('WFHDate')
                w_end_str = w.get('EndDate') or w_start_str
                if not w_start_str or not w_end_str: continue
                w_start = datetime.datetime.strptime(w_start_str, '%Y-%m-%d')
                w_end = datetime.datetime.strptime(w_end_str, '%Y-%m-%d')
                
                if (start_dt <= w_end) and (end_dt >= w_start):
                    if w.get('Status') == 'Approved':
                        messages.error(request, f"Overlap detected: You already have an approved WFH from {w_start_str} to {w_end_str}.")
                    else:
                        messages.error(request, f"Overlap detected: You have a pending WFH request from {w_start_str} to {w_end_str}.")
                    return redirect('apply_leave')
            except (ValueError, KeyError):
                continue

        # --- Balance validation ---
        employee = EmployeesTable.get_item({'EmployeeID': user_emp_id})
        if not employee:
            messages.error(request, "Employee record not found.")
            return redirect('apply_leave')

        balance_field = None
        if 'Earned Leave' in leave_type or 'Paid Leave' in leave_type: balance_field = 'Balance_PL'
        elif 'Sick Leave' in leave_type: balance_field = 'Balance_SL'
        elif 'Casual Leave' in leave_type: balance_field = 'Balance_CL'
        elif 'Compensatory' in leave_type or 'Comp Off' in leave_type: balance_field = 'Balance_CO'
        
        if balance_field:
            if balance_field == 'Balance_CO':
                from attendance.utils import get_active_compoff_balance
                co_details = get_active_compoff_balance(employee)
                db_balance = co_details['active_balance']
                pending_days = co_details['pending_balance']
                effective_balance = co_details['effective_balance']
            else:
                if balance_field == 'Balance_PL':
                    db_balance = float(employee.get('Balance_PL') or 0.0)
                else:
                    fallback_type = 'SL' if balance_field == 'Balance_SL' else 'CL'
                    db_balance = float(employee.get(balance_field, get_initial_leave_balance(employee, fallback_type)))
            
                # Identify the shorthand or name used in existing records for this type
                type_keywords = []
                if balance_field == 'Balance_PL': type_keywords = ['Earned Leave', 'Paid Leave', '(EL)', '(PL)']
                elif balance_field == 'Balance_SL': type_keywords = ['Sick Leave', '(SL)']
                elif balance_field == 'Balance_CL': type_keywords = ['Casual Leave', '(CL)']

                # Subtract days from all PENDING requests of the same type
                pending_days = 0
                for l in existing_leaves:
                    if l.get('Status') == 'Pending':
                        l_type = l.get('Type', '')
                        if any(kw in l_type for kw in type_keywords):
                            pending_days += float(l.get('DaysCount', 0))
            
                effective_balance = db_balance - pending_days
            
            if working_days > effective_balance:
                msg = f"Insufficient balance for {leave_type}. You have {db_balance} day(s) total"
                if pending_days > 0:
                    msg += f" ({pending_days} day(s) are currently pending approval), leaving you with {effective_balance} available."
                else:
                    msg += "."
                messages.error(request, msg)
                return redirect('apply_leave')
        
        # --- Parental Leave Validation ---
        if 'Maternity' in leave_type or 'Paternity' in leave_type:
            gender = employee.get('Gender', 'Male')
            limit = 90 if gender == 'Female' else 10
            
            if any((l.get('Type') == 'Maternity Leave' or l.get('Type') == 'Paternity Leave') and l.get('Status') != 'Rejected' for l in existing_leaves):
                if not employee.get('AllowSecondParental'):
                    messages.error(request, f"You have already used your {leave_type}. Please contact HR if you need to apply again.")
                    return redirect('apply_leave')

            if working_days > limit:
                messages.error(request, f"{leave_type} cannot exceed {limit} days.")
                return redirect('apply_leave')
        
        # --- Marriage Leave Validation ---
        if leave_type == 'Marriage Leave':
            if any(l.get('Type') == 'Marriage Leave' and l.get('Status') != 'Rejected' for l in existing_leaves):
                if not employee.get('AllowSecondMarriage'):
                    messages.error(request, "Marriage Leave can only be applied once in your career. Contact HR for exceptions.")
                    return redirect('apply_leave')
            if working_days > 10:
                messages.error(request, "Marriage Leave cannot exceed 10 working days.")
                return redirect('apply_leave')

        # --- Determine Approver based on Hierarchy ---
        hierarchy = ReportingHierarchyTable.scan(
            FilterExpression="EmployeeID = :eid",
            ExpressionAttributeValues={":eid": user_emp_id}
        )
        
        approver_id = None
        approver_role = 'HR ADMIN' # Default fallback
        
        if hierarchy:
            approver_id = hierarchy[0].get('ManagerID')
            # This is a bit expensive without GSI, but let's assume we can get it
            # Actually, we can just set the role based on who it's assigned to
            approver_role = 'Manager' if request.user.role == 'Employee' else 'HR ADMIN'
        else:
            # Fallback: Assign to ANY HR if no manager set
            all_users = UsersTable.scan()
            hr_users = [u for u in all_users if u.get('Role') == 'HR ADMIN']
            if hr_users:
                approver_id = hr_users[0].get('EmployeeID')
                approver_role = 'HR ADMIN'
            
        # --- File Upload Processing ---
        uploaded_file = request.FILES.get('leave_document')
        file_path = None
        
        is_sick_over_2 = leave_type == 'Sick Leave (SL)' and working_days > 2
        
        if is_sick_over_2:
            if not uploaded_file:
                messages.error(request, f"A supporting document is required for {leave_type}.")
                return redirect('apply_leave')
                
        if uploaded_file:
            if uploaded_file.size > 2 * 1024 * 1024:
                messages.error(request, "The supporting document must be less than 2MB.")
                return redirect('apply_leave')
                
            # Save file in static storage
            ext = uploaded_file.name.split('.')[-1]
            unique_filename = f"{user_emp_id}_{start_date}_{uuid.uuid4().hex[:8]}.{ext}"
            file_path = default_storage.save(f"leave_documents/{unique_filename}", uploaded_file)

        leave_item = {
            'EmployeeID': user_emp_id,
            'LeaveDate': start_date, 
            'EndDate': end_date,
            'Type': leave_type,
            'Reason': reason,
            'DaysCount': str(working_days),
            'Status': 'Pending',
            'IsHalfDay': is_half_day,
            'HalfDaySession': half_day_session,
            'ApproverRole': approver_role,
            'ApproverID': approver_id,
            'SubmittedAt': get_local_now().isoformat()
        }
        
        if file_path:
            leave_item['DocumentPath'] = file_path
            
        LeaveRequestsTable.put_item(leave_item)
        
        # --- Consume Override after successful application ---
        # Fetch fresh record to ensure we don't overwrite other changes and have latest override state
        fresh_employee = EmployeesTable.get_item({'EmployeeID': user_emp_id})
        
        if 'Maternity' in leave_type or 'Paternity' in leave_type:
            if fresh_employee.get('AllowSecondParental') is True:
                EmployeesTable.update_item(
                    Key={'EmployeeID': user_emp_id},
                    UpdateExpression="SET #asp = :f",
                    ExpressionAttributeNames={'#asp': 'AllowSecondParental'},
                    ExpressionAttributeValues={':f': False}
                )
        elif leave_type == 'Marriage Leave':
            if fresh_employee.get('AllowSecondMarriage') is True:
                EmployeesTable.update_item(
                    Key={'EmployeeID': user_emp_id},
                    UpdateExpression="SET #asm = :f",
                    ExpressionAttributeNames={'#asm': 'AllowSecondMarriage'},
                    ExpressionAttributeValues={':f': False}
                )
        
        # --- Send Notification to Approver ---
        if approver_id:
            emp_name = f"{request.user.first_name} {request.user.last_name}"
            send_notification(
                employee_id=approver_id,
                title="New Leave Application",
                message=f"{emp_name} has applied for {leave_type} from {start_date} to {end_date}.",
                n_type='Leave Request',
                icon='fa-calendar-plus',
                color='info',
                email_subject=f"Leave Application: {emp_name}",
                email_body=f"Hi,\n\n{emp_name} has submitted a new leave application for {leave_type}.\nDates: {start_date} to {end_date}\nReason: {reason}\n\nPlease log in to the Lurnexa portal to review and take action.\n\nBest regards,\nLurnexa HR Admin"
            )

        messages.success(request, f"Leave applied successfully for {working_days} working day(s) and sent for approval.")
        return redirect('leave_history')

class LeaveHistoryView(LoginRequiredMixin, ApprovedOnboardingMixin, TemplateView):
    template_name = 'leave/history.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Ensure leaves are refreshed if it's the 1st of the month
        employee = EmployeesTable.get_item({'EmployeeID': user.employee_id})
        if employee:
            refresh_monthly_leaves(employee)
            
        leaves = LeaveRequestsTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(user.employee_id)
        )
        
        # Filtering logic
        current_filter = self.request.GET.get('filter', 'all')
        now = get_local_now()
        this_year_str = str(now.year)
        last_year_str = str(now.year - 1)
        
        filtered_leaves = []
        for l in leaves:
            leave_date = l.get('LeaveDate', '')
            status = l.get('Status', '')
            
            if current_filter == 'this_year':
                if leave_date.startswith(this_year_str):
                    filtered_leaves.append(l)
            elif current_filter == 'last_year':
                if leave_date.startswith(last_year_str):
                    filtered_leaves.append(l)
            elif current_filter == 'approved':
                if status == 'Approved':
                    filtered_leaves.append(l)
            elif current_filter == 'pending':
                if status == 'Pending':
                    filtered_leaves.append(l)
            elif current_filter == 'rejected':
                if status == 'Rejected':
                    filtered_leaves.append(l)
            else:
                filtered_leaves.append(l)
                
        all_leaves = sorted(filtered_leaves, key=lambda x: x.get('LeaveDate', ''), reverse=True)
        
        paginator = Paginator(all_leaves, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context['leaves'] = page_obj
        context['total_count'] = len(all_leaves)
        context['current_filter'] = current_filter
        return context

class LeaveApprovalsView(ManagerRequiredMixin, TemplateView):
    template_name = 'leave/approvals.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_emp_id = self.request.user.employee_id
        
        # Filter Params
        q = self.request.GET.get('q', '').strip().lower()
        dept = self.request.GET.get('dept', '')
        date_range = self.request.GET.get('range', 'all')
        sort_order = self.request.GET.get('sort', 'desc')
        today = get_local_date()

        # Scan for leaves
        all_leaves = LeaveRequestsTable.scan()
        all_emps = EmployeesTable.scan()
        emp_obj_map = {e['EmployeeID']: e for e in all_emps}
        emp_name_map = {e['EmployeeID']: f"{e.get('FirstName', '')} {e.get('LastName', '')}" for e in all_emps}
        
        my_reportees = []
        if self.request.user.role == 'Manager':
            hierarchy = ReportingHierarchyTable.scan(
                FilterExpression="ManagerID = :mid",
                ExpressionAttributeValues={":mid": user_emp_id}
            )
            my_reportees = [h.get('EmployeeID') for h in hierarchy]
            
        relevant_leaves = []
        for l in all_leaves:
            # Role-based visibility
            is_relevant = False
            status = l.get('Status', 'Pending')
            
            if self.request.user.role in ['HR ADMIN', 'Super admin']:
                if status in ['Approved', 'Rejected']:
                    is_relevant = True
                elif status == 'Pending':
                    # Explicitly assigned or no specific manager set
                    if l.get('ApproverID') == user_emp_id or not l.get('ApproverID'):
                        is_relevant = True
            elif self.request.user.role == 'Manager':
                # STRICT RULE: Manager sees ONLY leaves of their direct reportees
                if l.get('EmployeeID') in my_reportees:
                    is_relevant = True
            
            if not is_relevant:
                continue

            # --- Apply Filters ---
            emp = emp_obj_map.get(l['EmployeeID'], {})
            l_name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}".lower()
            l_dept = emp.get('Department', '')
            
            if q and q not in l_name and q not in l['EmployeeID'].lower():
                continue
            if dept and l_dept != dept:
                continue
            
            l_date_str = l.get('LeaveDate', '')
            if date_range != 'all' and l_date_str:
                try:
                    l_date = datetime.datetime.strptime(l_date_str, '%Y-%m-%d').date()
                    if date_range == 'month' and l_date.strftime('%Y-%m') != today.strftime('%Y-%m'):
                        continue
                    elif date_range == '3months' and (today - l_date).days > 90:
                        continue
                    elif date_range == 'year' and l_date.year != today.year:
                        continue
                except: pass
            
            l['EmployeeName'] = emp_name_map.get(l['EmployeeID'], 'Unknown')
            relevant_leaves.append(l)

        pending_list = [l for l in relevant_leaves if l.get('Status') == 'Pending']
        processed_list = [l for l in relevant_leaves if l.get('Status') in ['Approved', 'Rejected']]
        
        pending_list.sort(key=lambda x: x.get('LeaveDate', ''), reverse=(sort_order == 'desc'))
        processed_list.sort(key=lambda x: x.get('LeaveDate', ''), reverse=(sort_order == 'desc'))
        
        context['departments'] = sorted(list(set(e.get('Department') for e in all_emps if e.get('Department'))))
        
        # Paginate Pending
        paginator_p = Paginator(pending_list, 10)
        page_p = self.request.GET.get('page_p')
        context['pending_leaves'] = paginator_p.get_page(page_p)
        context['pending_count'] = len(pending_list)
        
        # Paginate Processed
        paginator_h = Paginator(processed_list, 10)
        page_h = self.request.GET.get('page_h')
        # Mapping Processor Names
        for l in processed_list:
             pb_id = l.get('ProcessedBy') or l.get('ApproverID')
             if pb_id:
                 pb_emp = emp_obj_map.get(pb_id)
                 if pb_emp:
                     name = f"{pb_emp.get('FirstName', '')} {pb_emp.get('LastName', '')}".strip()
                     l['ProcessorName'] = name if name else pb_id
                 else:
                     l['ProcessorName'] = pb_id
             else:
                 l['ProcessorName'] = "System"

        context['processed_leaves'] = paginator_h.get_page(page_h)
        context['processed_count'] = len(processed_list)
        context['active_tab'] = self.request.GET.get('tab', 'pending')
        return context

class ApproveLeaveView(ManagerRequiredMixin, View):
    def get(self, request, emp_id, leave_date):
        # Clean inputs
        emp_id = str(emp_id).strip()
        leave_date = str(leave_date).strip()
        
        # 1. Fetch the leave request to get details
        leave_request = LeaveRequestsTable.get_item({'EmployeeID': emp_id, 'LeaveDate': leave_date})
        
        if not leave_request:
            messages.error(request, "Leave request not found.")
            return redirect('leave_approvals')
            
        if leave_request.get('Status') == 'Approved':
            messages.info(request, "This leave request is already approved.")
            return redirect('leave_approvals')

        # 2. Update Employee Balance
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if employee:
            leave_type = leave_request.get('Type', '')
            balance_field = None
            if 'Earned Leave' in leave_type or 'Paid Leave' in leave_type: balance_field = 'Balance_PL'
            elif 'Sick Leave' in leave_type: balance_field = 'Balance_SL'
            elif 'Casual Leave' in leave_type: balance_field = 'Balance_CL'
            elif 'Compensatory' in leave_type or 'Comp Off' in leave_type: balance_field = 'Balance_CO'
            
            if balance_field:
                if balance_field == 'Balance_CO':
                    try:
                        current_balance = float(employee.get('Balance_CO', 0.0))
                    except (TypeError, ValueError):
                        current_balance = 0.0
                else:
                    if balance_field == 'Balance_PL':
                        current_balance = float(employee.get('Balance_PL') or 0.0)
                    else:
                        fallback_type = 'SL' if balance_field == 'Balance_SL' else 'CL'
                        current_balance = float(employee.get(balance_field, get_initial_leave_balance(employee, fallback_type)))
                new_balance = max(0.0, current_balance - float(leave_request.get('DaysCount', 0)))
                
                # Update employee record
                EmployeesTable.update_item(
                    Key={'EmployeeID': emp_id},
                    UpdateExpression=f"SET {balance_field} = :val",
                    ExpressionAttributeValues={':val': str(new_balance)}
                )

        # 3. Mark Leave Request as Approved
        LeaveRequestsTable.update_item(
            Key={'EmployeeID': emp_id, 'LeaveDate': leave_date},
            UpdateExpression="SET #s = :val, ProcessedBy = :pb, ProcessedAt = :d",
            ExpressionAttributeNames={'#s': 'Status'},
            ExpressionAttributeValues={
                ':val': 'Approved',
                ':pb': request.user.employee_id,
                ':d': get_local_now().isoformat()
            }
        )
        
        # --- Send Notification to Employee ---
        try:
            emp_name = f"{employee.get('FirstName', '')} {employee.get('LastName', '')}" if employee else emp_id
            leave_type = leave_request.get('Type', 'Leave')
            end_date = leave_request.get('EndDate', leave_date)
            
            print(f"DEBUG: Calling send_notification for {emp_id} | Email: {employee.get('Email') if employee else 'NONE'} | Type: {leave_type}")
            send_notification(
                employee_id=emp_id,
                title="Leave Approved",
                message=f"Your {leave_type} leave from {leave_date} has been approved.",
                n_type='Leave',
                icon='fa-calendar-check',
                color='success',
                email_subject="Leave Request Approved",
                email_body=f"Hi {emp_name},\n\nYour leave request for {leave_type} from {leave_date} to {end_date} has been APPROVED.\n\nBest regards,\nLurnexa HR Admin"
            )
            print(f"DEBUG: send_notification call finished for {emp_id}")
        except Exception as e:
            print(f"ERROR in ApproveLeaveView notification: {e}")
            import traceback
            traceback.print_exc()

        messages.success(request, "Leave request approved and balance updated.")
        return redirect('leave_approvals')

class RejectLeaveView(ManagerRequiredMixin, View):
    def get(self, request, emp_id, leave_date):
        # Clean inputs
        emp_id = str(emp_id).strip()
        leave_date = str(leave_date).strip()
        
        LeaveRequestsTable.update_item(
            Key={'EmployeeID': emp_id, 'LeaveDate': leave_date},
            UpdateExpression="SET #s = :val, ProcessedBy = :pb, ProcessedAt = :d",
            ExpressionAttributeNames={'#s': 'Status'},
            ExpressionAttributeValues={
                ':val': 'Rejected',
                ':pb': request.user.employee_id,
                ':d': get_local_now().isoformat()
            }
        )
        
        # --- Send Notification to Employee ---
        try:
            employee = EmployeesTable.get_item({'EmployeeID': emp_id})
            emp_name = f"{employee.get('FirstName', '')} {employee.get('LastName', '')}" if employee else emp_id
            
            print(f"DEBUG: Calling send_notification for REJECTION for {emp_id}")
            send_notification(
                employee_id=emp_id,
                title="Leave Rejected",
                message=f"Your leave request from {leave_date} has been rejected.",
                n_type='Leave',
                icon='fa-calendar-times',
                color='danger',
                email_subject="Leave Request Rejected",
                email_body=f"Hi {emp_name},\n\nYour leave request for {leave_date} has been REJECTED.\n\nPlease contact your manager for more details.\n\nBest regards,\nLurnexa HR Admin"
            )
            print(f"DEBUG: send_notification rejection finished for {emp_id}")
        except Exception as e:
            print(f"ERROR in RejectLeaveView notification: {e}")

        messages.error(request, "Leave request rejected.")
        return redirect('leave_approvals')

class AdjustLeaveBalanceView(HRRequiredMixin, View):
    def post(self, request, emp_id):
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot adjust leave balances.")
            return redirect('employee_profile', emp_id=emp_id)

        balance_pl = request.POST.get('balance_pl')
        balance_sl = request.POST.get('balance_sl')
        balance_cl = request.POST.get('balance_cl')
        balance_co = request.POST.get('balance_co')
        # Checkboxes: 'on' if checked, absent if unchecked
        allow_parental = request.POST.get('allow_second_parental') == 'on'
        allow_marriage = request.POST.get('allow_second_marriage') == 'on'
        
        try:
            employee = EmployeesTable.get_item({'EmployeeID': emp_id})
            updates = {}
            if balance_pl is not None and balance_pl != '':
                updates['Balance_PL'] = str(float(balance_pl))
            if balance_sl is not None and balance_sl != '':
                updates['Balance_SL'] = str(float(balance_sl))
            if balance_cl is not None and balance_cl != '':
                updates['Balance_CL'] = str(float(balance_cl))
            if balance_co is not None and balance_co != '':
                updates['Balance_CO'] = str(float(balance_co))
                if employee:
                    from attendance.utils import get_active_compoff_balance
                    co_details = get_active_compoff_balance(employee)
                    current_active = co_details['active_balance']
                    difference = float(balance_co) - current_active
                    if abs(difference) > 0.001:
                        adjustments = employee.get('COAdjustments', [])
                        adjustments.append({
                            'Date': get_local_date().isoformat(),
                            'Amount': str(round(difference, 2))
                        })
                        updates['COAdjustments'] = adjustments
            
            # These must always be updated to match the current checkbox state
            updates['AllowSecondParental'] = True if allow_parental else False
            updates['AllowSecondMarriage'] = True if allow_marriage else False
            
            if updates:
                expr_parts = []
                attr_names = {}
                attr_vals = {}
                
                for i, (key, value) in enumerate(updates.items()):
                    expr_parts.append(f"#k{i} = :v{i}")
                    attr_names[f"#k{i}"] = key
                    attr_vals[f":v{i}"] = value
                
                UpdateExpression = "SET " + ", ".join(expr_parts)
                
                EmployeesTable.update_item(
                    Key={'EmployeeID': emp_id},
                    UpdateExpression=UpdateExpression,
                    ExpressionAttributeNames=attr_names,
                    ExpressionAttributeValues=attr_vals
                )
                messages.success(request, f"Leave balances and permissions updated for {emp_id}.")
            else:
                messages.warning(request, "No changes provided.")
        except Exception as e:
            messages.error(request, f"Error updating balances: {str(e)}")
            
        return redirect('employee_profile', emp_id=emp_id)


class EncashEarnedLeaveView(HRRequiredMixin, View):
    def post(self, request, emp_id):
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot process leave encashments.")
            return redirect('employee_profile', emp_id=emp_id)

        try:
            employee = EmployeesTable.get_item({'EmployeeID': emp_id})
            if not employee:
                messages.error(request, "Employee not found.")
                return redirect('employee_directory')

            if employee.get('EmploymentType') == 'Intern':
                messages.error(request, "Interns do not have Earned Leaves and cannot process encashment.")
                return redirect('employee_profile', emp_id=emp_id)

            balance_pl = float(employee.get('Balance_PL') or 0.0)
            if balance_pl <= 0:
                messages.error(request, "Employee has no Earned Leave balance to encash.")
                return redirect('employee_profile', emp_id=emp_id)

            salary_pa = safe_float(employee.get('SalaryPA'))
            monthly_salary = salary_pa / 12.0
            daily_salary = monthly_salary / 30.0
            total_payout = balance_pl * daily_salary

            # Reset EL to 0
            EmployeesTable.update_item(
                Key={'EmployeeID': emp_id},
                UpdateExpression="SET Balance_PL = :pl",
                ExpressionAttributeValues={':pl': '0.0'}
            )

            # Send Notification and Email to Employee
            emp_name = f"{employee.get('FirstName', '')} {employee.get('LastName', '')}".strip()
            send_notification(
                employee_id=emp_id,
                title="Earned Leave Encashed 💰",
                message=f"HR has processed encashment for {balance_pl} Earned Leaves. Total payout: ₹{total_payout:,.2f}.",
                n_type='Payroll',
                icon='fa-money-bill-wave',
                color='success',
                email_subject="Earned Leave Encashment Processed",
                email_body=(
                    f"Hi {emp_name or 'Employee'},\n\n"
                    f"We would like to inform you that your accrued Earned Leave balance of {balance_pl} days has been successfully encashed.\n\n"
                    f"Encashment Details:\n"
                    f"- Earned Leaves encashed: {balance_pl} days\n"
                    f"- Daily salary rate: ₹{daily_salary:,.2f}\n"
                    f"- Total Payout Amount: ₹{total_payout:,.2f}\n\n"
                    f"Your Earned Leave balance has been reset to 0.0.\n\n"
                    f"Best regards,\n"
                    f"Lurnexa HR Admin"
                )
            )

            messages.success(request, f"Successfully processed encashment for {balance_pl} Earned Leaves. Total payout: ₹{total_payout:,.2f}. Balance reset to 0.0.")
        except Exception as e:
            messages.error(request, f"Error processing encashment: {str(e)}")

        return redirect('employee_profile', emp_id=emp_id)

