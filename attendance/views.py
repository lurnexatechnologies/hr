from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.contrib import messages
from django.views import View
from django.views.generic import TemplateView
from auth_custom.mixins import LoginRequiredMixin, HRRequiredMixin
from core.dynamodb_service import (
    AttendanceTable, EmployeesTable, LeaveRequestsTable, 
    SettingsTable, WFHRequestsTable, ReportingHierarchyTable, UsersTable
)
from core.utils import send_notification, get_local_now, get_local_date
import uuid
from boto3.dynamodb.conditions import Key
import datetime

class ClockInView(LoginRequiredMixin, View):
    def post(self, request):
        now = get_local_now()
        today = now.date().isoformat()
        now_time_str = now.strftime("%H:%M")
        eid = request.user.employee_id
        
        # Fetch employee for shift info
        employee = EmployeesTable.get_item({'EmployeeID': eid})
        shift = employee.get('Shift', 'Day Shift')
        
        # 1. Check if user is on leave today
        all_leaves = LeaveRequestsTable.scan()
        on_leave = False
        for l in all_leaves:
            if l.get('EmployeeID') == eid and l.get('Status') == 'Approved':
                try:
                    if l.get('LeaveDate') <= today <= l.get('EndDate'):
                        on_leave = True
                        break
                except:
                    continue
        
        if on_leave:
            messages.error(request, "Clock-in restricted. You are currently on an approved leave today.")
            return redirect('attendance_history')

        # 2. Check Office Timing Restrictions
        timings = SettingsTable.get_item({'SettingKey': 'office_timings'})
        if timings:
            if shift == 'Night Shift':
                start_time_str = timings.get('NightStartTime', '22:00')
                end_time_str = timings.get('NightEndTime', '06:00')
            else:
                start_time_str = timings.get('StartTime', '09:00')
                end_time_str = timings.get('EndTime', '18:00')
            
            try:
                start_time = datetime.datetime.strptime(start_time_str, "%H:%M").time()
                end_time = datetime.datetime.strptime(end_time_str, "%H:%M").time()
                current_time = now.time()
                
                is_valid = False
                if start_time <= end_time:
                    # Normal shift (Day)
                    if start_time <= current_time <= end_time:
                        is_valid = True
                else:
                    # Overnight shift (Night)
                    if current_time >= start_time or current_time <= end_time:
                        is_valid = True
                
                if not is_valid:
                    messages.error(request, f"Clock-in restricted. Your shift ({shift}) hours are {start_time_str} to {end_time_str}.")
                    return redirect('attendance_history')
            except Exception as e:
                print(f"Error validating timings: {e}")

        # 3. Proceed with Clock-In
        record = AttendanceTable.get_item({'EmployeeID': eid, 'RecordDate': today})
        if record:
            messages.error(request, "Already clocked in today.")
        else:
            item = {
                'EmployeeID': eid,
                'RecordDate': today,
                'ClockIn': now_time_str,
                'ClockOut': None,
                'Status': 'Present'
            }
            AttendanceTable.put_item(item)
            messages.success(request, f"Clocked in successfully at {now_time_str}.")
            
        return redirect('attendance_history')

class ClockOutView(LoginRequiredMixin, View):
    def post(self, request):
        now = get_local_now()
        today = now.date().isoformat()
        yesterday = (now.date() - datetime.timedelta(days=1)).isoformat()
        now_time = now.strftime("%H:%M")
        eid = request.user.employee_id

        # 1. Check if user is on leave today
        all_leaves = LeaveRequestsTable.scan()
        on_leave = False
        for l in all_leaves:
            if l.get('EmployeeID') == eid and l.get('Status') == 'Approved':
                try:
                    if l.get('LeaveDate') <= today <= l.get('EndDate'):
                        on_leave = True
                        break
                except:
                    continue
        
        if on_leave:
            messages.error(request, "Clock-out restricted. You are currently on an approved leave today.")
            return redirect('attendance_history')

        # 2. Proceed with Clock-Out
        # For night shift, the record might be from yesterday
        record_today = AttendanceTable.get_item({'EmployeeID': eid, 'RecordDate': today})
        record_yesterday = AttendanceTable.get_item({'EmployeeID': eid, 'RecordDate': yesterday})
        
        target_record = None
        target_date = None
        
        if record_today and not record_today.get('ClockOut'):
            target_record = record_today
            target_date = today
        elif record_yesterday and not record_yesterday.get('ClockOut'):
            # Only consider yesterday's record if it's an open night shift
            employee = EmployeesTable.get_item({'EmployeeID': eid})
            if employee.get('Shift') == 'Night Shift':
                target_record = record_yesterday
                target_date = yesterday
        
        if not target_record:
            if record_today and record_today.get('ClockOut'):
                messages.error(request, "Already clocked out today.")
            else:
                messages.error(request, "You haven't clocked in for an active shift.")
        else:
            AttendanceTable.update_item(
                Key={'EmployeeID': eid, 'RecordDate': target_date},
                UpdateExpression="SET ClockOut = :val",
                ExpressionAttributeValues={':val': now_time}
            )
            
            # --- Credit Comp-Off if it's a weekend or public holiday ---
            try:
                from attendance.utils import check_and_credit_compoff
                check_and_credit_compoff(eid, target_date)
            except Exception as e:
                print(f"Error checking/crediting compoff on clock-out: {e}")

            messages.success(request, f"Clocked out successfully at {now_time}.")
            
        return redirect('attendance_history')

class AttendanceHistoryView(LoginRequiredMixin, TemplateView):
    template_name = 'attendance/history.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        local_today = get_local_date()
        today = local_today.isoformat()
        records = AttendanceTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(self.request.user.employee_id)
        )
        # Add hours calculation and dynamic status
        for r in records:
            # Format date directly in Python for reliable template display
            raw_date = r.get('RecordDate')
            r['DisplayDate'] = raw_date # Fallback
            if raw_date:
                for fmt in ('%Y-%m-%d', '%d-%m-%Y'):
                    try:
                        dt = datetime.datetime.strptime(raw_date, fmt)
                        r['DisplayDate'] = dt.strftime('%Y-%m-%d')
                        break
                    except:
                        continue

            # Handle Total Hours
            if r.get('ClockIn') and r.get('ClockOut'):
                try:
                    fmt = "%H:%M"
                    t1 = datetime.datetime.strptime(r['ClockIn'], fmt)
                    t2 = datetime.datetime.strptime(r['ClockOut'], fmt)
                    diff = t2 - t1
                    r['TotalHours'] = round(diff.total_seconds() / 3600, 2)
                except:
                    r['TotalHours'] = 0
            else:
                r['TotalHours'] = "--"
            
            # Handle Status override if currently working
            if r.get('ClockIn') and not r.get('ClockOut') and r.get('RecordDate') == today:
                r['DisplayStatus'] = 'In Progress'
            else:
                r['DisplayStatus'] = r.get('Status', 'Present')

        all_records = sorted(records, key=lambda x: x.get('RecordDate', ''), reverse=True)
        
        paginator = Paginator(all_records, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context['records'] = page_obj
        context['total_count'] = len(all_records)
        
        # Check if on leave
        all_leaves = LeaveRequestsTable.scan()
        on_leave = False
        for l in all_leaves:
            if l.get('EmployeeID') == self.request.user.employee_id and l.get('Status') == 'Approved':
                try:
                    if l.get('LeaveDate') <= today <= l.get('EndDate'):
                        on_leave = True
                        break
                except:
                    continue
        
        # Search in all_records to ensure active card appears on all paginated pages
        today_record = next((r for r in all_records if r.get('RecordDate') == today), None)
        yesterday = (local_today - datetime.timedelta(days=1)).isoformat()
        yesterday_record = next((r for r in all_records if r.get('RecordDate') == yesterday), None)
        
        employee = EmployeesTable.get_item({'EmployeeID': self.request.user.employee_id})
        is_night_shift = employee.get('Shift') == 'Night Shift'

        context['can_clock_in'] = not today_record and not on_leave
        
        active_record = None
        if today_record and not today_record.get('ClockOut'):
            active_record = today_record
        elif is_night_shift and yesterday_record and not yesterday_record.get('ClockOut'):
            active_record = yesterday_record
            
        context['active_record'] = active_record
        context['can_clock_out'] = active_record is not None and not on_leave
        context['today_record'] = today_record
        context['is_on_leave'] = on_leave

        # Formatted dates for template display
        context['active_shift_date'] = None
        if active_record:
            raw = active_record.get('RecordDate')
            if raw:
                for fmt in ('%Y-%m-%d', '%d-%m-%Y'):
                    try:
                        dt = datetime.datetime.strptime(raw, fmt)
                        context['active_shift_date'] = dt.strftime('%Y-%m-%d')
                        break
                    except: continue
                if not context['active_shift_date']:
                    context['active_shift_date'] = raw
        
        context['today_shift_date'] = today_record.get('DisplayDate') if today_record else None

        # --- WFH Requests ---
        wfh_requests = WFHRequestsTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(self.request.user.employee_id)
        )
        
        # Add formatted strings to WFH requests
        for w in wfh_requests:
            raw_wfh = w.get('WFHDate')
            w['DisplayDate'] = raw_wfh
            if raw_wfh:
                for fmt in ('%Y-%m-%d', '%d-%m-%Y'):
                    try:
                        w['DisplayDate'] = datetime.datetime.strptime(raw_wfh, fmt).strftime('%Y-%m-%d')
                        break
                    except: continue

            raw_end = w.get('EndDate')
            w['DisplayEndDate'] = raw_end
            if raw_end:
                for fmt in ('%Y-%m-%d', '%d-%m-%Y'):
                    try:
                        w['DisplayEndDate'] = datetime.datetime.strptime(raw_end, fmt).strftime('%Y-%m-%d')
                        break
                    except: continue

            raw_req = w.get('RequestDate')
            w['DisplayReqDate'] = raw_req
            if raw_req:
                for fmt in ('%Y-%m-%d', '%d-%m-%Y'):
                    try:
                        w['DisplayReqDate'] = datetime.datetime.strptime(raw_req, fmt).strftime('%Y-%m-%d')
                        break
                    except: continue

        all_wfh_requests = sorted(wfh_requests, key=lambda x: x.get('RequestDate', ''), reverse=True)
        paginator_wfh = Paginator(all_wfh_requests, 10)
        page_wfh = self.request.GET.get('page_wfh')
        
        context['wfh_requests'] = paginator_wfh.get_page(page_wfh)
        context['wfh_count'] = len(all_wfh_requests)
        
        return context

class ApplyWFHView(LoginRequiredMixin, View):
    def post(self, request):
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        reason = request.POST.get('reason')
        user_emp_id = request.user.employee_id
        
        if not start_date or not end_date or not reason:
            messages.error(request, "Start Date, End Date, and Reason are required.")
            return redirect('attendance_history')
            
        if end_date < start_date:
            messages.error(request, "End Date cannot be before Start Date.")
            return redirect('attendance_history')
            
        # 1. Check for overlapping WFH requests (Simple check for StartDate overlap)
        existing = WFHRequestsTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(user_emp_id)
        )
        for req in existing:
            if req.get('Status') == 'Rejected': continue
            r_start = req.get('WFHDate')
            r_end = req.get('EndDate') or r_start
            if (start_date <= r_end) and (end_date >= r_start):
                messages.error(request, f"You already have a WFH request overlapping with {start_date} to {end_date}.")
                return redirect('attendance_history')

        # 1a. Check for overlapping Approved Leaves
        all_leaves = LeaveRequestsTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(user_emp_id)
        )
        for l in all_leaves:
            if l.get('Status') == 'Approved':
                l_start = l.get('LeaveDate')
                l_end = l.get('EndDate') or l_start
                if l_start and l_end:
                    if (start_date <= l_end) and (end_date >= l_start):
                        messages.error(request, f"You already have an approved leave from {l_start} to {l_end}.")
                        return redirect('attendance_history')

        # 2. Determine Approval Path
        hierarchy = ReportingHierarchyTable.scan(
            FilterExpression="EmployeeID = :eid",
            ExpressionAttributeValues={":eid": user_emp_id}
        )
        
        manager_id = None
        if hierarchy:
            manager_id = hierarchy[0].get('ManagerID')
            
        user_role = request.user.role
        
        if user_role == 'Super admin':
            status = 'Approved' # Self-approved
            approver_id = user_emp_id
        elif user_role == 'HR ADMIN':
            status = 'Pending Manager Approval' # Super admin is the manager
            approver_id = manager_id
            if not approver_id:
                # Fallback to any Super admin
                sa_users = [u for u in UsersTable.scan() if u.get('Role') == 'Super admin']
                if sa_users: approver_id = sa_users[0].get('EmployeeID')
        elif user_role == 'Manager':
            status = 'Pending HR ADMIN Approval'
            approver_id = manager_id # Reporting HR
            if not approver_id:
                hr_users = [u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN']
                if hr_users: approver_id = hr_users[0].get('EmployeeID')
        else: # Employee
            if manager_id:
                # Check if reporting to HR directly
                mgr_role = 'Manager'
                mgr_users = UsersTable.scan(FilterExpression="EmployeeID = :eid", ExpressionAttributeValues={":eid": manager_id})
                if mgr_users: mgr_role = mgr_users[0].get('Role')
                
                if mgr_role == 'HR ADMIN':
                    status = 'Pending HR ADMIN Approval'
                else:
                    status = 'Pending Manager Approval'
                approver_id = manager_id
            else:
                status = 'Pending HR ADMIN Approval'
                hr_users = [u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN']
                if hr_users: approver_id = hr_users[0].get('EmployeeID')
        
        req_id = str(uuid.uuid4())
        item = {
            'EmployeeID': user_emp_id,
            'RequestID': req_id,
            'WFHDate': start_date, # Primary date
            'EndDate': end_date,
            'Reason': reason,
            'Status': status,
            'ApproverID': approver_id,
            'RequestDate': get_local_date().isoformat(),
            'OriginalRole': user_role
        }
        WFHRequestsTable.put_item(item)
        
        # Notify Approver
        if approver_id:
            emp_name = f"{request.user.first_name} {request.user.last_name}"
            send_notification(
                employee_id=approver_id,
                title="New WFH Request",
                message=f"{emp_name} has applied for WFH on {start_date}.",
                n_type='WFH',
                icon='fa-house-laptop',
                color='primary',
                email_subject=f"WFH Request: {emp_name}",
                email_body=f"Hi,\n\n{emp_name} has applied for Work From Home on {start_date}.\nReason: {reason}\n\nPlease review the request in your dashboard.\n\nBest regards,\nLurnexa HR Admin"
            )

        messages.success(request, f"WFH request submitted for {start_date}. Status: {status}")
        return redirect('attendance_history')

class HRAttendanceView(HRRequiredMixin, TemplateView):
    template_name = 'attendance/hr_attendance.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today_obj = get_local_date()
        today_str = today_obj.isoformat()
        
        # Get selected date or default to today
        view_date = self.request.GET.get('date', '').strip()
        if not view_date:
            view_date = today_str
            
        leave_type_filter = self.request.GET.get('leave_type', '')
        search_query = self.request.GET.get('q', '').strip().lower()
        
        # Prevent viewing future dates
        if view_date > today_str:
            messages.warning(self.request, "Cannot view attendance for future dates.")
            view_date = today_str
            
        # Office Timings for the modal
        timings = SettingsTable.get_item({'SettingKey': 'office_timings'})
        context['office_timings'] = timings or {
            'StartTime': '09:00', 
            'EndTime': '18:00',
            'NightStartTime': '22:00',
            'NightEndTime': '06:00'
        }
        
        # 1. Fetch all employees (Excluding Super admin)
        all_users = UsersTable.scan()
        all_emp_raw = EmployeesTable.scan()
        employees = []
        for emp in all_emp_raw:
            user = next((u for u in all_users if u.get('UserID') == emp.get('UserID')), None)
            if user and user.get('Role') == 'Super admin':
                continue
                
            employees.append(emp)
        
        # 2. Fetch attendance records for selected date
        all_attendance = AttendanceTable.scan()
        selected_day_attendance = {r['EmployeeID']: r for r in all_attendance if r.get('RecordDate') == view_date}
        
        # 3. Fetch approved leaves for selected date
        all_leaves = LeaveRequestsTable.scan()
        
        # All available standard leave types for the filter dropdown
        context['leave_types'] = [
            'Casual Leave', 'Sick Leave', 'Earned Leave',
            'Maternity Leave', 'Paternity Leave', 'Marriage Leave', 'Unpaid Leave'
        ]
        context['selected_leave_type'] = leave_type_filter

        selected_day_leaves = {}
        for l in all_leaves:
            if l.get('Status') == 'Approved':
                try:
                    start = l.get('LeaveDate')
                    end = l.get('EndDate')
                    if start <= view_date <= end:
                        selected_day_leaves[l.get('EmployeeID')] = l
                except:
                    continue
        
        present_list = []
        on_leave_list = []
        all_members_list = []
        
        total_workforce = 0
        
        for emp in employees:
            eid = emp['EmployeeID']
            joined_date = emp.get('JoinedDate')
            
            record = selected_day_attendance.get(eid)
            leave_info = selected_day_leaves.get(eid)
            
            # Skip employees who have not joined yet relative to the viewed date
            # UNLESS they actually have a record for this day
            if joined_date and joined_date > view_date and not record and not leave_info:
                continue
                
            lwd_str = emp.get('LastWorkingDate')
            if lwd_str and view_date > lwd_str and not record:
                continue
                
            user = next((u for u in all_users if u.get('UserID') == emp.get('UserID')), None)
            is_user_active = user.get('IsActive', True) if user else True
            if not is_user_active and view_date >= today_str and not record:
                continue
                
            status = emp.get('OnboardingStatus')
            if status == 'Resigned' and view_date >= today_str and not record:
                continue
                
            total_workforce += 1
            
            if search_query:
                fname = emp.get('FirstName', '').lower()
                lname = emp.get('LastName', '').lower()
                eid_str = emp.get('EmployeeID', '').lower()
                full_name = f"{fname} {lname}"
                if search_query not in fname and search_query not in lname and search_query not in eid_str and search_query not in full_name:
                    continue
                
            emp_name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}"
            
            record = selected_day_attendance.get(eid)
            leave_info = selected_day_leaves.get(eid)
            
            status_data = {
                'id': eid,
                'name': emp_name,
                'shift': emp.get('Shift', 'Day Shift'),
                'clock_in': '--:--',
                'clock_out': '--:--',
                'hours': 0,
                'status': 'Unpaid',
                'leave_type': None
            }

            if record:
                # Calculate hours if clocked out
                hours = 0
                if record.get('ClockIn') and record.get('ClockOut'):
                    try:
                        fmt = "%H:%M"
                        t1 = datetime.datetime.strptime(record['ClockIn'], fmt)
                        t2 = datetime.datetime.strptime(record['ClockOut'], fmt)
                        diff = t2 - t1
                        hours = round(diff.total_seconds() / 3600, 2)
                    except:
                        pass
                
                status_data.update({
                    'clock_in': record.get('ClockIn'),
                    'clock_out': record.get('ClockOut') or '--:--',
                    'hours': hours,
                    'status': 'Present'
                })
            elif leave_info:
                status_data.update({
                    'status': 'On Leave',
                    'leave_type': leave_info.get('Type', 'Approved Leave')
                })
            else:
                status_data.update({
                    'status': 'On Leave',
                    'leave_type': 'Unpaid Leave'
                })

            # If not filtered out, append to respective lists
            if status_data['status'] == 'Present':
                present_list.append(status_data)
            elif status_data['status'] == 'On Leave':
                if not leave_type_filter:
                    on_leave_list.append(status_data)
                else:
                    lt_db = status_data.get('leave_type', '').lower()
                    lt_query = leave_type_filter.lower()
                    match = False
                    if lt_query == 'sick leave' and ('sick' in lt_db or '(sl)' in lt_db): match = True
                    elif lt_query == 'casual leave' and ('casual' in lt_db or '(cl)' in lt_db): match = True
                    elif lt_query == 'earned leave' and ('earned' in lt_db or '(el)' in lt_db): match = True
                    elif lt_query == 'paid leave' and ('paid' in lt_db or '(pl)' in lt_db): match = True
                    elif lt_query == 'unpaid leave' and ('unpaid' in lt_db or 'lop' in lt_db): match = True
                    elif lt_query.split(' ')[0] in lt_db: match = True
                    
                    if match:
                        on_leave_list.append(status_data)
            
            all_members_list.append(status_data)
        
        # Pagination for HR Attendance Tabs
        paginator_all = Paginator(all_members_list, 10)
        page_all = self.request.GET.get('page_all')
        context['all_members_list'] = paginator_all.get_page(page_all)
        context['all_count'] = len(all_members_list)
        
        paginator_pres = Paginator(present_list, 10)
        page_pres = self.request.GET.get('page_pres')
        context['present_employees'] = paginator_pres.get_page(page_pres)
        context['present_count'] = len(present_list)
        
        paginator_leave = Paginator(on_leave_list, 10)
        page_leave = self.request.GET.get('page_leave')
        context['on_leave_employees'] = paginator_leave.get_page(page_leave)
        context['leave_count'] = len(on_leave_list)
        
        context['employees'] = employees
        context['total_workforce'] = total_workforce
        context['view_date'] = view_date
        context['today_str'] = today_str
        context['is_today'] = view_date == today_str
        context['search_query'] = self.request.GET.get('q', '')
        
        return context

class OfficeTimingSettingsView(HRRequiredMixin, View):
    def post(self, request):
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        night_start_time = request.POST.get('night_start_time')
        night_end_time = request.POST.get('night_end_time')
        
        SettingsTable.put_item({
            'SettingKey': 'office_timings',
            'StartTime': start_time,
            'EndTime': end_time,
            'NightStartTime': night_start_time,
            'NightEndTime': night_end_time,
            'UpdatedAt': get_local_now().isoformat()
        })
        
        messages.success(request, "Office timings updated successfully.")
        return redirect('hr_attendance')

from django.http import HttpResponse
import csv

class DownloadAttendanceReportView(HRRequiredMixin, View):
    def get(self, request):
        target_date = request.GET.get('date')
        export_all = request.GET.get('export') == 'all'
        
        # 1. Fetch data (Excluding Super admin)
        all_users = UsersTable.scan()
        all_emp_raw = EmployeesTable.scan()
        employees = []
        today_str = get_local_date().isoformat()
        ref_date = target_date or today_str
        
        for emp in all_emp_raw:
            user = next((u for u in all_users if u.get('UserID') == emp.get('UserID')), None)
            if user and user.get('Role') == 'Super admin':
                continue
                
            if not export_all:
                joined_date = emp.get('JoinedDate')
                if joined_date and joined_date > ref_date:
                    continue
                    
                lwd_str = emp.get('LastWorkingDate')
                if lwd_str and ref_date > lwd_str:
                    continue
                    
                is_user_active = user.get('IsActive', True) if user else True
                if not is_user_active and ref_date >= today_str:
                    continue
                    
                status = emp.get('OnboardingStatus')
                if status == 'Resigned' and ref_date >= today_str:
                    continue
            else:
                is_user_active = user.get('IsActive', True) if user else True
                if not is_user_active:
                    continue
                status = emp.get('OnboardingStatus')
                if status == 'Resigned':
                    continue
                    
            employees.append(emp)
        all_attendance = AttendanceTable.scan()
        all_leaves = LeaveRequestsTable.scan()
        
        # 2. Prepare Response
        response = HttpResponse(content_type='text/csv')
        filename = f"attendance_report_{target_date}.csv" if target_date else "attendance_full_report.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        writer = csv.writer(response)
        writer.writerow(['Date', 'Employee Name', 'Employee ID', 'Shift', 'Status', 'Clock In', 'Clock Out', 'Total Hours'])
        
        if export_all:
            # Export everything sorted by date
            records = sorted(all_attendance, key=lambda x: x.get('RecordDate', ''), reverse=True)
            emp_map = {e['EmployeeID']: {'name': f"{e.get('FirstName', '')} {e.get('LastName', '')}", 'shift': e.get('Shift', 'Day Shift')} for e in employees}
            
            for r in records:
                eid = r.get('EmployeeID')
                emp_info = emp_map.get(eid, {'name': 'Unknown', 'shift': '--'})
                name = emp_info['name']
                shift = emp_info['shift']
                date = r.get('RecordDate', '--')
                status = r.get('Status', 'Present')
                cin = r.get('ClockIn', '--:--')
                cout = r.get('ClockOut', '--:--')
                
                hours = 0
                if cin and cout and cout != '--:--':
                    try:
                        fmt = "%H:%M"
                        t1 = datetime.datetime.strptime(cin, fmt)
                        t2 = datetime.datetime.strptime(cout, fmt)
                        hours = round((t2 - t1).total_seconds() / 3600, 2)
                    except: pass
                
                writer.writerow([date, name, eid, shift, status, cin, cout, hours])
        else:
            # Export specific day (existing logic improved)
            if not target_date:
                target_date = get_local_date().isoformat()
                
            target_attendance = {r['EmployeeID']: r for r in all_attendance if r.get('RecordDate') == target_date}
            target_leaves = {}
            for l in all_leaves:
                if l.get('Status') == 'Approved':
                    try:
                        start = l.get('LeaveDate')
                        end = l.get('EndDate')
                        if start and end and start <= target_date <= end:
                            target_leaves[l.get('EmployeeID')] = l.get('LeaveType', 'Approved Leave')
                    except: continue

            for emp in employees:
                eid = emp['EmployeeID']
                joined_date = emp.get('JoinedDate')
                
                # Skip if employee hadn't joined yet
                if joined_date and joined_date > target_date:
                    continue
                    
                name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}"
                record = target_attendance.get(eid)
                
                status = 'On Leave: Unpaid Leave'
                cin = '--:--'
                cout = '--:--'
                hours = 0
                
                if record:
                    status = 'Present'
                    cin = record.get('ClockIn')
                    cout = record.get('ClockOut') or '--:--'
                    if cin and cout != '--:--':
                        try:
                            fmt = "%H:%M"
                            t1 = datetime.datetime.strptime(cin, fmt)
                            t2 = datetime.datetime.strptime(cout, fmt)
                            hours = round((t2 - t1).total_seconds() / 3600, 2)
                        except: pass
                elif eid in target_leaves:
                    status = f"On Leave: {target_leaves[eid]}"
                
                shift = emp.get('Shift', 'Day Shift')
                writer.writerow([target_date, name, eid, shift, status, cin, cout, hours])
            
        return response

class ExportMyAttendanceView(LoginRequiredMixin, View):
    def get(self, request):
        eid = request.user.employee_id
        records = AttendanceTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(eid)
        )
        records = sorted(records, key=lambda x: x.get('RecordDate', ''), reverse=True)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="my_attendance_{eid}.csv"'
        
        writer = csv.writer(response)
        employee = EmployeesTable.get_item({'EmployeeID': eid})
        shift = employee.get('Shift', 'Day Shift')
        writer.writerow(['Date', 'Shift', 'Status', 'Clock In', 'Clock Out', 'Total Hours'])
        
        for r in records:
            date = r.get('RecordDate', '--')
            status = r.get('Status', 'Present')
            cin = r.get('ClockIn', '--:--')
            cout = r.get('ClockOut', '--:--')
            
            hours = 0
            if cin and cout and cout != '--:--':
                try:
                    fmt = "%H:%M"
                    t1 = datetime.datetime.strptime(cin, fmt)
                    t2 = datetime.datetime.strptime(cout, fmt)
                    hours = round((t2 - t1).total_seconds() / 3600, 2)
                except: pass
            
            writer.writerow([date, shift, status, cin, cout, hours])
            
        return response

class ImportAttendanceView(HRRequiredMixin, View):
    def post(self, request):
        if 'attendance_file' not in request.FILES:
            messages.error(request, "No file uploaded.")
            return redirect('hr_attendance')
        
        csv_file = request.FILES['attendance_file']
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Please upload a valid CSV file.")
            return redirect('hr_attendance')

        try:
            import csv
            decoded_file = csv_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)
            
            # Normalize headers (strip spaces)
            reader.fieldnames = [f.strip() for f in reader.fieldnames] if reader.fieldnames else []
            
            import_count = 0
            error_count = 0
            skipped_details = []
            
            for index, row in enumerate(reader, start=1):
                try:
                    # Strip spaces from all values
                    clean_row = {k.strip(): v.strip() if v else '' for k, v in row.items()}
                    
                    # Mapping based on user requested columns:
                    # Date, Employee Name, Employee ID, Shift, Status, Clock In, Clock Out
                    
                    raw_date = clean_row.get('Date')
                    eid = clean_row.get('Employee ID') or clean_row.get('EmployeeID')
                    clock_in = clean_row.get('Clock In') or clean_row.get('ClockIn')
                    clock_out = clean_row.get('Clock Out') or clean_row.get('ClockOut')
                    status = clean_row.get('Status', 'Present')

                    if not eid or not raw_date:
                        error_count += 1
                        skipped_details.append(f"Row {index}: Missing Employee ID or Date")
                        continue

                    # Handle Date format: Prioritize YYYY-MM-DD
                    try:
                        # Try YYYY-MM-DD first
                        date_obj = datetime.datetime.strptime(raw_date, '%Y-%m-%d').date()
                        iso_date = date_obj.isoformat()
                    except ValueError:
                        try:
                            # Fallback to DD-MM-YYYY
                            date_obj = datetime.datetime.strptime(raw_date, '%d-%m-%Y').date()
                            iso_date = date_obj.isoformat()
                        except ValueError:
                            error_count += 1
                            skipped_details.append(f"Row {index}: Invalid Date format '{raw_date}'. Use YYYY-MM-DD")
                            continue

                    # Validate if employee exists
                    emp = EmployeesTable.get_item({'EmployeeID': eid})
                    if not emp:
                        error_count += 1
                        skipped_details.append(f"Row {index}: Employee ID {eid} not found in database")
                        continue

                    # Put item into DynamoDB
                    item = {
                        'EmployeeID': eid,
                        'RecordDate': iso_date,
                        'ClockIn': clock_in if clock_in and clock_in != '--:--' else None,
                        'ClockOut': clock_out if clock_out and clock_out != '--:--' else None,
                        'Status': status
                    }
                    AttendanceTable.put_item(item)
                    
                    # Check and credit Comp-Off if it's a weekend or public holiday and status is Present or WFH
                    if status in ['Present', 'WFH']:
                        try:
                            from attendance.utils import check_and_credit_compoff
                            check_and_credit_compoff(eid, iso_date)
                        except Exception as e:
                            print(f"Error checking/crediting compoff on import: {e}")

                    import_count += 1
                except Exception as e:
                    error_count += 1
                    skipped_details.append(f"Row {index}: Unexpected error - {str(e)}")
            
            if import_count > 0:
                messages.success(request, f"Successfully imported {import_count} attendance records.")
            
            if error_count > 0:
                error_msg = f"Skipped {error_count} records. Reasons: " + ", ".join(skipped_details[:5])
                if len(skipped_details) > 5:
                    error_msg += f" ... and {len(skipped_details) - 5} more."
                messages.warning(request, error_msg)
                
        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")
            
        return redirect('hr_attendance')
