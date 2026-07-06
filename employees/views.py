from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.views import View
from django.views.generic import TemplateView
from auth_custom.mixins import LoginRequiredMixin, HRRequiredMixin, HRAdminOnlyMixin, ApprovedOnboardingMixin
from core.dynamodb_service import (
    EmployeesTable, UsersTable, ReportingHierarchyTable, OnboardingTokensTable,
    LeaveRequestsTable, AttendanceTable, PayslipsTable, ExpensesTable,
    ResignationsTable, LoginHistoryTable, NotificationsTable
)
from core.utils import save_uploaded_file, send_notification, safe_float, get_local_date, get_local_now
import uuid
import bcrypt
import datetime
from boto3.dynamodb.conditions import Key

def generate_next_employee_id():
    all_employees = EmployeesTable.scan()
    max_id = 0
    for emp in all_employees:
        eid = emp.get('EmployeeID', '')
        if eid.startswith('LT-26'):
            try:
                num = int(eid.replace('LT-26', ''))
                if num > max_id:
                    max_id = num
            except ValueError:
                pass
    if max_id == 0:
        return 'LT-26001'
    return f"LT-26{max_id + 1:03d}"

def get_managers_list(for_role=None):
    """Helper to get managers based on the role of the employee being edited."""
    all_users = UsersTable.scan()
    all_employees = EmployeesTable.scan()
    managers_list = []
    seen_ids = set()
    
    for u in all_users:
        emp_id = u.get('EmployeeID')
        role = u.get('Role')
        if not emp_id or emp_id in seen_ids:
            continue
            
        # 1. Super admin is only visible to HR ADMINs (Filtered in frontend)
        # if role == 'Super admin' and for_role != 'HR ADMIN':
        #     continue
            
        # 2. Managers and HR ADMINs are visible to everyone else
        if role in ['Manager', 'HR ADMIN', 'Super admin']:
            emp_data = next((e for e in all_employees if e.get('EmployeeID') == emp_id), None)
            if emp_data:
                seen_ids.add(emp_id)
                managers_list.append({
                    'EmployeeID': emp_data['EmployeeID'],
                    'Name': f"{emp_data['FirstName']} {emp_data['LastName']} ({role})"
                })
    return managers_list

class EmployeeDirectoryView(HRRequiredMixin, ApprovedOnboardingMixin, TemplateView):
    template_name = 'employees/directory.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_employees = EmployeesTable.scan()
        all_users = UsersTable.scan()
        
        # Filter out Resigned employees (passed LWD)
        active_employees = []
        today = get_local_date()
        for emp in all_employees:
            user = next((u for u in all_users if u.get('UserID') == emp.get('UserID')), None)
            is_user_active = user.get('IsActive', True) if user else True
            
            # Exclusion: Super admin should not be visible in directory to anyone
            role = user.get('Role', 'Employee') if user else 'Employee'
            if role == 'Super admin':
                continue

            emp['IsActive'] = is_user_active
            emp['SystemRole'] = role
            
            status = emp.get('OnboardingStatus')
            lwd_str = emp.get('LastWorkingDate')
            
            is_active_view = True
            
            # Filters: Resignation status
            if status in ['Resigned', 'Pending Review', 'Rejected', 'Pending']:
                is_active_view = False
            elif status == 'Accepted Resignation' and lwd_str:
                try:
                    lwd = datetime.datetime.strptime(lwd_str, '%Y-%m-%d').date()
                    if today > lwd:
                        is_active_view = False
                except:
                    pass
            
            if not is_active_view:
                continue
                
            active_employees.append(emp)

            
        # Extract unique Departments and Roles for filtering (from all active employees before search/filter)
        context['departments'] = sorted(list(set(emp.get('Department') for emp in active_employees if emp.get('Department'))))
        context['roles'] = sorted(list(set(emp.get('SystemRole') for emp in active_employees if emp.get('SystemRole'))))

        query = self.request.GET.get('q', '').strip().lower()
        if query:
            active_employees = [
                emp for emp in active_employees 
                if query in emp.get('FirstName', '').lower() or 
                   query in emp.get('LastName', '').lower() or 
                   query in emp.get('EmployeeID', '').lower() or
                   query in emp.get('Department', '').lower() or
                   query in emp.get('Designation', '').lower()
            ]
            
        selected_dept = self.request.GET.get('dept', '')
        selected_role = self.request.GET.get('role', '')
        
        if selected_dept:
            active_employees = [e for e in active_employees if e.get('Department') == selected_dept]
        if selected_role:
            active_employees = [e for e in active_employees if e.get('SystemRole') == selected_role]
        
        context['selected_dept'] = selected_dept
        context['selected_role'] = selected_role
            
        # Hierarchical Sort: HR ADMIN > HR > Manager > Employee > Intern
        def get_priority(e):
            role = e.get('SystemRole', 'Employee')
            is_intern = e.get('EmploymentType') == 'Intern'
            
            if role == 'HR ADMIN': return 0
            if role == 'HR': return 1
            if role == 'Manager': return 2
            if is_intern: return 4
            return 3 # Permanent Employee
            
        active_employees.sort(key=lambda x: (get_priority(x), x.get('FirstName', '').lower()))
            
        # Pagination
        paginator = Paginator(active_employees, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context['employees'] = page_obj
        context['total_count'] = len(active_employees)
        context['query'] = self.request.GET.get('q', '')
        return context

class ExEmployeeDirectoryView(HRRequiredMixin, ApprovedOnboardingMixin, TemplateView):
    template_name = 'employees/ex_directory.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_employees = EmployeesTable.scan()
        all_users = UsersTable.scan()
        today = get_local_date()
        ex_employees = []
        for emp in all_employees:
            user = next((u for u in all_users if u.get('UserID') == emp.get('UserID')), None)
            is_user_active = user.get('IsActive', True) if user else True
            emp['IsActive'] = is_user_active
            
            status = emp.get('OnboardingStatus')
            lwd_str = emp.get('LastWorkingDate')
            
            # Ex-employee is ONLY determined by Resignation status
            is_ex = False
            if status == 'Resigned':
                is_ex = True
            elif status == 'Accepted Resignation' and lwd_str:
                try:
                    lwd = datetime.datetime.strptime(lwd_str, '%Y-%m-%d').date()
                    if today > lwd:
                        is_ex = True
                except:
                    pass
            
            if is_ex:
                ex_employees.append(emp)
        
        query = self.request.GET.get('q', '').strip().lower()
        if query:
            ex_employees = [
                emp for emp in ex_employees 
                if query in emp.get('FirstName', '').lower() or 
                   query in emp.get('LastName', '').lower() or 
                   query in emp.get('EmployeeID', '').lower() or
                   query in emp.get('Department', '').lower() or
                   query in emp.get('Designation', '').lower()
            ]
        # Pagination
        paginator = Paginator(ex_employees, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context['employees'] = page_obj
        context['total_count'] = len(ex_employees)
        context['query'] = self.request.GET.get('q', '')
        return context

class MyTeamView(LoginRequiredMixin, TemplateView):
    template_name = 'employees/team.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_emp_id = self.request.user.employee_id
        user_role = self.request.user.role
        
        team_members = []
        reporting_manager = None

        # 1. Always look for who THIS user reports to
        hierarchy = ReportingHierarchyTable.scan(
            FilterExpression="EmployeeID = :eid",
            ExpressionAttributeValues={":eid": user_emp_id}
        )
        if hierarchy:
            manager_id = hierarchy[0].get('ManagerID')
            reporting_manager = EmployeesTable.get_item({'EmployeeID': manager_id})

        if user_role in ['Manager', 'HR ADMIN']:
            # Managers/HR see their direct reports
            reporting_lines = ReportingHierarchyTable.query(
                KeyConditionExpression=Key('ManagerID').eq(user_emp_id)
            )
            report_ids = [line.get('EmployeeID') for line in reporting_lines]
            today = datetime.date.today()
            for emp_id in report_ids:
                emp = EmployeesTable.get_item({'EmployeeID': emp_id})
                if emp:
                    status = emp.get('OnboardingStatus')
                    lwd_str = emp.get('LastWorkingDate')
                    
                    # Check account activation
                    user_rec = UsersTable.scan(FilterExpression="EmployeeID = :eid", ExpressionAttributeValues={":eid": emp_id})
                    is_user_active = user_rec[0].get('IsActive', True) if user_rec else True
                    
                    is_gone = not is_user_active
                    if not is_gone:
                        if status in ['Resigned', 'Pending Review', 'Rejected', 'Pending']:
                            is_gone = True
                        elif status == 'Accepted Resignation' and lwd_str:
                            try:
                                lwd = datetime.datetime.strptime(lwd_str, '%Y-%m-%d').date()
                                if today > lwd:
                                    is_gone = True
                            except:
                                pass
                    
                    if is_gone:
                        continue
                    team_members.append(emp)
            
            context['title_suffix'] = "Direct Reports"
        else:
            # Employees see their Colleagues (people reporting to the same manager)
            if reporting_manager:
                manager_id = reporting_manager['EmployeeID']
                reporting_lines = ReportingHierarchyTable.query(
                    KeyConditionExpression=Key('ManagerID').eq(manager_id)
                )
                report_ids = [line.get('EmployeeID') for line in reporting_lines]
                for emp_id in report_ids:
                    if emp_id == user_emp_id: continue # Skip self
                    emp = EmployeesTable.get_item({'EmployeeID': emp_id})
                    if emp and emp.get('OnboardingStatus') != 'Resigned':
                        team_members.append(emp)
            
            context['title_suffix'] = "Team Members"

        # 3. Apply Search Filter
        query = self.request.GET.get('q', '').strip().lower()
        if query:
            team_members = [
                emp for emp in team_members 
                if query in emp.get('FirstName', '').lower() or 
                   query in emp.get('LastName', '').lower() or 
                   query in emp.get('EmployeeID', '').lower() or
                   query in emp.get('Department', '').lower() or
                   query in emp.get('Designation', '').lower() or
                   query in emp.get('EmploymentType', '').lower() or
                   query in emp.get('EmploymentStatus', '').lower()
            ]

        # Pagination
        paginator = Paginator(team_members, 10)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context['employees'] = page_obj # Overwrite for template
        context['total_count'] = len(team_members)
        context['manager'] = reporting_manager
        context['query'] = query
        return context

class EmployeeProfileView(LoginRequiredMixin, ApprovedOnboardingMixin, TemplateView):
    template_name = 'employees/profile.html'

    def get(self, request, emp_id, *args, **kwargs):
        # 1. Block Super admin from their own (non-existent) profile
        if request.user.role == 'Super admin' and request.user.employee_id == emp_id:
            messages.error(request, "Super admin does not have a personal employee profile.")
            return redirect('index')

        # 2. Authorization: HR and Super admin see all, others see only self
        if request.user.role not in ['HR ADMIN', 'Super admin'] and request.user.employee_id != emp_id:
            messages.error(request, "Access Denied: You are not authorized to view this profile.")
            return redirect('employee_profile', emp_id=request.user.employee_id)

        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if not employee:
            messages.error(request, "Employee not found.")
            return redirect('index')
        
        # Fetch IsActive status from UsersTable
        user_record = UsersTable.get_item({'UserID': employee.get('UserID', '')})
        system_role = user_record.get('Role', 'Employee') if user_record else 'Employee'

        # Edit Authorization Rules:
        # 1. Super admin can edit everyone.
        # 2. HR Admin can edit everyone EXCEPT:
        #    - Themselves (self-profile edit blocked for HR Admin)
        #    - Other HR Admins (only Super Admin can edit HR Admin profiles)
        can_edit = False
        if request.user.role == 'Super admin':
            can_edit = True
        elif request.user.role == 'HR ADMIN':
            if emp_id != request.user.employee_id and system_role != 'HR ADMIN':
                can_edit = True
        
        # Fetch IsActive status from UsersTable
        user_record = UsersTable.get_item({'UserID': employee.get('UserID', '')})
        is_active = user_record.get('IsActive', True) if user_record else True

        # Fetch Leave Balances for HR to adjust
        existing_leaves = LeaveRequestsTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(emp_id)
        )
        
        # Pending leaves subtraction logic (same as dashboard)
        pending_pl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and ('Earned Leave' in l.get('Type', '') or 'Earned Leave' in l.get('LeaveType', '') or 'Paid Leave' in l.get('Type', '') or 'Paid Leave' in l.get('LeaveType', '')))
        pending_sl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and ('Sick Leave' in l.get('Type', '') or 'Sick Leave' in l.get('LeaveType', '')))
        pending_cl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and ('Casual Leave' in l.get('Type', '') or 'Casual Leave' in l.get('LeaveType', '')))
        from attendance.utils import get_active_compoff_balance
        co_details = get_active_compoff_balance(employee)
        balance_co = co_details['active_balance']
        effective_co = co_details['effective_balance']
        pending_co = co_details['pending_balance']

        # Proactively update the employee's Balance_CO attribute in the DB to keep it perfectly in sync with the dynamically calculated value
        if str(balance_co) != employee.get('Balance_CO'):
            try:
                EmployeesTable.update_item(
                    Key={'EmployeeID': emp_id},
                    UpdateExpression="SET Balance_CO = :val",
                    ExpressionAttributeValues={':val': str(balance_co)}
                )
                employee['Balance_CO'] = str(balance_co)
            except:
                pass

        from core.utils import get_initial_leave_balance
        balance_pl = float(employee.get('Balance_PL') or 0.0)
        balance_sl = float(employee.get('Balance_SL', get_initial_leave_balance(employee, 'SL')))
        balance_cl = float(employee.get('Balance_CL', get_initial_leave_balance(employee, 'CL')))
        salary_pa = safe_float(employee.get('SalaryPA'))
        el_daily_salary = (salary_pa / 12.0) / 30.0
        el_total_payout = balance_pl * el_daily_salary

        return self.render_to_response({
            'employee': employee,
            'can_edit': can_edit,
            'is_active': is_active,
            'system_role': user_record.get('Role', 'Employee') if user_record else 'Employee',
            'balance_pl': balance_pl,
            'balance_sl': balance_sl,
            'balance_cl': balance_cl,
            'balance_co': balance_co,
            'effective_pl': balance_pl - pending_pl,
            'effective_sl': balance_sl - pending_sl,
            'effective_cl': balance_cl - pending_cl,
            'effective_co': effective_co,
            'pending_pl': pending_pl,
            'pending_sl': pending_sl,
            'pending_cl': pending_cl,
            'pending_co': pending_co,
            'el_daily_salary': el_daily_salary,
            'el_total_payout': el_total_payout,
            'vault_fields': [
                ('PassportPhoto', 'Passport Photo', 'fa-image', 'primary'),
                ('AadharCard', 'Aadhar Card', 'fa-id-card', 'success'),
                ('PanCard', 'PAN Card', 'fa-address-card', 'warning'),
                ('Cert_10th', '10th Marksheet', 'fa-certificate', 'info'),
                ('Cert_Inter', 'Intermediate Marksheet', 'fa-certificate', 'info'),
                ('Cert_Degree', 'Degree Certificate', 'fa-certificate', 'info')
            ]
        })

class AddEmployeeView(HRRequiredMixin, View):
    def get(self, request):
        managers = get_managers_list(for_role='Employee')
        return render(request, 'employees/add_employee.html', {
            'managers': managers
        })

    def post(self, request):
        # Super admin view-only restriction
        if request.user.role == 'Super admin':
            messages.error(request, "Super admin has view-only access and cannot add new employees.")
            return redirect('employee_directory')

        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        if not email:
            messages.error(request, "Email is required.")
            return redirect('add_employee')
        role = request.POST.get('role', 'Employee')
        department = request.POST.get('department', '')
        shift = request.POST.get('shift', 'Day Shift')
        manager_id = request.POST.get('manager_id')
        custom_employee_id = request.POST.get('employee_id')
        designation = request.POST.get('designation', 'Employee')
        
        # New Details
        education = request.POST.get('education')
        mother_name = request.POST.get('mother_name')
        father_name = request.POST.get('father_name')
        city = request.POST.get('city')
        phone = request.POST.get('phone')
        address = request.POST.get('address')
        salary_pa = request.POST.get('salary_pa') or 0
        bank_name = request.POST.get('bank_name')
        account_number = request.POST.get('account_number')
        ifsc_code = request.POST.get('ifsc_code')
        spouse_name = request.POST.get('spouse_name')
        emergency_contact_name = request.POST.get('emergency_contact_name')
        emergency_relation = request.POST.get('emergency_relation')
        emergency_phone = request.POST.get('emergency_phone')
        joining_date = request.POST.get('joining_date') or datetime.date.today().isoformat()
        employment_type = request.POST.get('employment_type', 'Permanent')
        fulltime_date = '' if employment_type == 'Intern' else (request.POST.get('fulltime_date') or joining_date)
        dob = request.POST.get('dob')
        gender = request.POST.get('gender')
        is_pf_applicable = request.POST.get('is_pf_applicable') == 'on' if 'is_pf_applicable_present' in request.POST or 'is_pf_applicable' in request.POST else True
        internship_period = request.POST.get('internship_period', '0') if employment_type == 'Intern' else '0'
        employment_status = request.POST.get('employment_status', 'Full Time')
        probation_period = request.POST.get('probation_period', '0') if employment_status == 'Probation' else '0'
        
        aadhar_number = request.POST.get('aadhar_number', '').strip()
        pan_number = request.POST.get('pan_number', '').strip().upper()

        if not aadhar_number or not aadhar_number.isdigit() or len(aadhar_number) != 12:
            messages.error(request, "Invalid Aadhar Number. It must be exactly 12 digits.")
            return redirect('add_employee')

        import re
        if role == 'Super admin':
            sa_users = [u for u in UsersTable.scan() if u.get('Role') == 'Super admin']
            if sa_users:
                messages.error(request, "Only one Super admin can exist in the system.")
                return redirect('add_employee')

        # --- Age Validation (Min 21) ---
        if dob:
            try:
                dob_dt = datetime.datetime.strptime(dob, '%Y-%m-%d').date()
                today = datetime.date.today()
                age = today.year - dob_dt.year - ((today.month, today.day) < (dob_dt.month, dob_dt.day))
                if age < 21:
                    messages.error(request, f"Onboarding failed: Employee must be at least 21 years old (Current age: {age}).")
                    return redirect('add_employee')
            except ValueError:
                pass
        
        # New Certificate Fields
        # Save files
        passport_photo = save_uploaded_file(request.FILES.get('passport_photo'), 'employees/photos')
        aadhar_card = save_uploaded_file(request.FILES.get('aadhar_card'), 'employees/docs')
        pan_card = save_uploaded_file(request.FILES.get('pan_card'), 'employees/docs')
        
        cert_10th = save_uploaded_file(request.FILES.get('cert_10th'), 'employees/certs')
        cert_inter = save_uploaded_file(request.FILES.get('cert_inter'), 'employees/certs')
        cert_degree = save_uploaded_file(request.FILES.get('cert_degree'), 'employees/certs')
        
        # Professional Experience Docs (Optional)
        exp_letter = save_uploaded_file(request.FILES.get('exp_letter'), 'employees/docs')
        relieving_letter = save_uploaded_file(request.FILES.get('relieving_letter'), 'employees/docs')
        pf_letter = save_uploaded_file(request.FILES.get('pf_letter'), 'employees/docs')
        
        # Simple uniqueness check
        existing_user = UsersTable.query(
            IndexName='EmailIndex',
            KeyConditionExpression=Key('Email').eq(email)
        )
        if existing_user:
            messages.error(request, "User with this email already exists.")
            return redirect('add_employee')
            
        # Employee ID is now mandatory
        if not custom_employee_id:
            messages.error(request, "Employee ID is required.")
            return redirect('add_employee')

        # Check for duplicate Employee ID
        if EmployeesTable.get_item({'EmployeeID': custom_employee_id}):
            messages.error(request, f"Employee ID {custom_employee_id} already exists.")
            return redirect('add_employee')
            
        # Check for duplicate Phone Number
        if phone:
            existing_phone = EmployeesTable.scan(
                FilterExpression="Phone = :p",
                ExpressionAttributeValues={":p": phone}
            )
            if existing_phone:
                messages.error(request, f"Phone number {phone} is already registered to another employee.")
                return redirect('add_employee')
            
        user_id = str(uuid.uuid4())
        employee_id = custom_employee_id
        
        hashed_pw = bcrypt.hashpw('Password@123'.encode('utf-8')[:72], bcrypt.gensalt()).decode('utf-8')
        
        user_item = {
            'UserID': user_id,
            'Email': email,
            'Role': role,
            'PasswordHash': hashed_pw,
            'EmployeeID': employee_id,
            'IsActive': True
        }
        UsersTable.put_item(user_item)
        
        try:
            eff_date_str = fulltime_date or joining_date
            j_month = datetime.datetime.strptime(eff_date_str, '%Y-%m-%d').month if eff_date_str else datetime.date.today().month
            prorated_val = str(float(max(1, 12 - j_month + 1)))
        except Exception:
            prorated_val = '12.0'

        employee_item = {
            'EmployeeID': employee_id,
            'UserID': user_id,
            'Email': email,
            'FirstName': first_name,
            'LastName': last_name,
            'Department': department,
            'Shift': shift,
            'Designation': designation,
            'EmploymentType': employment_type,
            'InternshipPeriod': internship_period,
            'EmploymentStatus': employment_status,
            'ProbationPeriod': probation_period,
            'Education': education,
            'is_pf_applicable': is_pf_applicable,
            'MotherName': mother_name,
            'FatherName': father_name,
            'SpouseName': spouse_name,
            'EmergencyContactName': emergency_contact_name,
            'EmergencyContactRelation': emergency_relation,
            'EmergencyContactPhone': emergency_phone,
            'City': city,
            'Phone': phone,
            'Address': address,
            'SalaryPA': salary_pa,
            'BankName': bank_name,
            'AccountNumber': account_number,
            'IFSCCode': ifsc_code,
            'PassportPhoto': passport_photo,
            'AadharCard': aadhar_card,
            'AadharNumber': aadhar_number,
            'PanCard': pan_card,
            'PanNumber': pan_number,
            'Cert_10th': cert_10th,
            'Cert_Inter': cert_inter,
            'Cert_Degree': cert_degree,
            'ExperienceLetter': exp_letter,
            'RelievingLetter': relieving_letter,
            'PFLetter': pf_letter,
            'JoinedDate': joining_date,
            'FullTimeDate': fulltime_date,
            'DOB': dob,
            'Gender': gender,
            'IsExperienced': request.POST.get('is_experienced') == 'on',
            'PreviousCompany': request.POST.get('previous_company'),
            'LastDesignation': request.POST.get('last_designation'),
            'ExperienceYears': request.POST.get('experience_years'),
            'PrevLastWorkingDate': request.POST.get('last_working_date'),
            'PFNumber': request.POST.get('pf_number'),
            'UANNumber': request.POST.get('uan_number'),
            'OnboardingStatus': 'Approved',
            'DocumentStatuses': {
                'PassportPhoto': 'Approved' if passport_photo else None,
                'AadharCard': 'Approved' if aadhar_card else None,
                'PanCard': 'Approved' if pan_card else None,
                'Cert_10th': 'Approved' if cert_10th else None,
                'Cert_Inter': 'Approved' if cert_inter else None,
                'Cert_Degree': 'Approved' if cert_degree else None,
                'ExperienceLetter': 'Approved' if exp_letter else None,
                'RelievingLetter': 'Approved' if relieving_letter else None,
                'PFLetter': 'Approved' if pf_letter else None
            },
            'Balance_PL': '0.0',
            'Balance_SL': '0.0' if employment_type == 'Intern' else prorated_val,
            'Balance_CL': '0.0' if employment_type == 'Intern' else prorated_val,
            'Balance_CO': '0.0',
            'PF_Balance': '0.0' if is_pf_applicable else None,
            'LastLeaveRefresh': datetime.date.today().strftime('%Y-%m')
        }
        EmployeesTable.put_item(employee_item)
        
        # Save Reporting Hierarchy if manager is selected
        if manager_id:
            ReportingHierarchyTable.put_item({
                'ManagerID': manager_id,
                'EmployeeID': employee_id
            })
        
        messages.success(request, f"Employee {first_name} {last_name} created successfully with ID {employee_id}.")
        return redirect('employee_directory')

class EditEmployeeView(HRRequiredMixin, View):
    def get(self, request, emp_id):
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if not employee:
            messages.error(request, "Employee not found.")
            return redirect('employee_directory')
        
        # Ensure JoinedDate and FullTimeDate are not missing to prevent template lookup crashes
        if 'JoinedDate' not in employee:
            employee['JoinedDate'] = ''
        if 'FullTimeDate' not in employee:
            employee['FullTimeDate'] = '' if employee.get('EmploymentType') == 'Intern' else employee['JoinedDate']
        elif employee.get('EmploymentType') == 'Intern':
            employee['FullTimeDate'] = ''
        
        # Fetch current manager
        current_manager_link = ReportingHierarchyTable.scan(
            FilterExpression="EmployeeID = :eid",
            ExpressionAttributeValues={":eid": emp_id}
        )
        current_manager_id = current_manager_link[0]['ManagerID'] if current_manager_link else None
        
        user_record = next((u for u in UsersTable.scan() if u.get('EmployeeID') == emp_id), None)
        system_role = user_record.get('Role', 'Employee') if user_record else 'Employee'
        
        # Enforcement: HR Admins cannot edit self or other HR Admins
        if request.user.role == 'HR ADMIN':
            if emp_id == request.user.employee_id or system_role == 'HR ADMIN':
                messages.error(request, "Access Denied: Only Super Admin can modify HR Admin profiles.")
                return redirect('employee_profile', emp_id=emp_id)

        managers = get_managers_list(for_role=system_role)
        
        return render(request, 'employees/edit_employee.html', {
            'employee': employee,
            'system_role': system_role,
            'managers': managers,
            'current_manager_id': current_manager_id
        })

    def post(self, request, emp_id):
        user_record = next((u for u in UsersTable.scan() if u.get('EmployeeID') == emp_id), None)
        system_role = user_record.get('Role', 'Employee') if user_record else 'Employee'

        # Super admin edit rules:
        if request.user.role == 'Super admin':
            if system_role != 'HR ADMIN':
                messages.error(request, "Super admin can only modify HR Admin profiles.")
                return redirect('employee_profile', emp_id=emp_id)
        
        # HR Admin edit rules:
        elif request.user.role == 'HR ADMIN':
            if emp_id == request.user.employee_id or system_role == 'HR ADMIN':
                messages.error(request, "Access Denied: Only Super Admin can modify HR Admin profiles.")
                return redirect('employee_profile', emp_id=emp_id)

        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if not employee:
            messages.error(request, "Employee not found.")
            return redirect('employee_directory')

        new_emp_id = request.POST.get('new_employee_id')
        
        # Capture all updated fields
        update_data = {
            'FirstName': request.POST.get('first_name'),
            'LastName': request.POST.get('last_name'),
            'Email': request.POST.get('email'),
            'Department': request.POST.get('department'),
            'Designation': request.POST.get('designation'),
            'Education': request.POST.get('education'),
            'MotherName': request.POST.get('mother_name'),
            'FatherName': request.POST.get('father_name'),
            'SpouseName': request.POST.get('spouse_name'),
            'EmergencyContactName': request.POST.get('emergency_contact_name'),
            'EmergencyContactRelation': request.POST.get('emergency_relation'),
            'EmergencyContactPhone': request.POST.get('emergency_phone'),
            'City': request.POST.get('city'),
            'Phone': request.POST.get('phone'),
            'Address': request.POST.get('address'),
            'SalaryPA': request.POST.get('salary_pa'),
            'BankName': request.POST.get('bank_name'),
            'AccountNumber': request.POST.get('account_number'),
            'IFSCCode': request.POST.get('ifsc_code'),
            'JoinedDate': request.POST.get('joining_date'),
            'FullTimeDate': '' if request.POST.get('employment_type') == 'Intern' else (request.POST.get('fulltime_date') or request.POST.get('joining_date')),
            'DOB': request.POST.get('dob'),
            'Gender': request.POST.get('gender'),
            'is_pf_applicable': request.POST.get('is_pf_applicable') == 'on' if 'is_pf_applicable_present' in request.POST or 'is_pf_applicable' in request.POST else employee.get('is_pf_applicable', True),
            'EmploymentType': request.POST.get('employment_type'),
            'InternshipPeriod': request.POST.get('internship_period', '0'),
            'EmploymentStatus': request.POST.get('employment_status', 'Full Time'),
            'ProbationPeriod': request.POST.get('probation_period', '0'),
            'Shift': request.POST.get('shift', 'Day Shift'),
            'ManagerID': request.POST.get('manager_id'),
            'IsExperienced': request.POST.get('is_experienced') == 'on',
            'PreviousCompany': request.POST.get('previous_company'),
            'LastDesignation': request.POST.get('last_designation'),
            'ExperienceYears': request.POST.get('experience_years'),
            'PrevLastWorkingDate': request.POST.get('last_working_date'),
            'PFNumber': request.POST.get('pf_number'),
            'UANNumber': request.POST.get('uan_number'),
            'AadharNumber': request.POST.get('aadhar_number', '').strip(),
            'PanNumber': request.POST.get('pan_number', '').strip().upper(),
        }

        # --- Aadhar & PAN Validation ---
        aadhar_number = update_data.get('AadharNumber')
        pan_number = update_data.get('PanNumber')

        if not aadhar_number or not aadhar_number.isdigit() or len(aadhar_number) != 12:
            messages.error(request, "Invalid Aadhar Number. It must be exactly 12 digits.")
            return redirect('edit_employee', emp_id)

        import re
        if not pan_number or not re.match(r'^[A-Z0-9]{10}$', pan_number):
            messages.error(request, "Invalid PAN Number. It must be exactly 10 alphanumeric characters.")
            return redirect('edit_employee', emp_id)
        
        # --- Age Validation (Min 21) ---
        dob = update_data.get('DOB')
        if dob:
            try:
                dob_dt = datetime.datetime.strptime(dob, '%Y-%m-%d').date()
                today = get_local_date()
                age = today.year - dob_dt.year - ((today.month, today.day) < (dob_dt.month, dob_dt.day))
                if age < 21:
                    messages.error(request, f"Update failed: Employee must be at least 21 years old (Current age: {age}).")
                    return redirect('edit_employee', emp_id)
            except ValueError:
                pass

        # --- Email Uniqueness Check ---
        new_email = update_data.get('Email')
        if new_email and new_email != employee.get('Email'):
            existing_user = UsersTable.query(
                IndexName='EmailIndex',
                KeyConditionExpression=Key('Email').eq(new_email)
            )
            if existing_user:
                messages.error(request, f"Error: Email {new_email} is already taken by another user.")
                return redirect('edit_employee', emp_id=emp_id)

        # Handle photos/docs
        if request.FILES.get('passport_photo'):
            update_data['PassportPhoto'] = save_uploaded_file(request.FILES.get('passport_photo'), 'employees/photos')
        if request.FILES.get('aadhar_card'):
            update_data['AadharCard'] = save_uploaded_file(request.FILES.get('aadhar_card'), 'employees/docs')
        if request.FILES.get('pan_card'):
            update_data['PanCard'] = save_uploaded_file(request.FILES.get('pan_card'), 'employees/docs')
        if request.FILES.get('cert_10th'):
            update_data['Cert_10th'] = save_uploaded_file(request.FILES.get('cert_10th'), 'employees/certs')
        if request.FILES.get('cert_inter'):
            update_data['Cert_Inter'] = save_uploaded_file(request.FILES.get('cert_inter'), 'employees/certs')
        if request.FILES.get('cert_degree'):
            update_data['Cert_Degree'] = save_uploaded_file(request.FILES.get('cert_degree'), 'employees/certs')
        if request.FILES.get('exp_letter'):
            update_data['ExperienceLetter'] = save_uploaded_file(request.FILES.get('exp_letter'), 'employees/docs')
        if request.FILES.get('relieving_letter'):
            update_data['RelievingLetter'] = save_uploaded_file(request.FILES.get('relieving_letter'), 'employees/docs')
        if request.FILES.get('pf_letter'):
            update_data['PFLetter'] = save_uploaded_file(request.FILES.get('pf_letter'), 'employees/docs')

        # --- Single Super Admin Constraint ---
        new_role = request.POST.get('role')
        if new_role == 'Super admin':
            sa_users = [u for u in UsersTable.scan() if u.get('Role') == 'Super admin']
            if sa_users and sa_users[0].get('EmployeeID') != emp_id:
                messages.error(request, "Only one Super admin can exist in the system.")
                return redirect('edit_employee', emp_id)

        if new_emp_id and new_emp_id != emp_id:
            # Check for conflict
            if EmployeesTable.get_item({'EmployeeID': new_emp_id}):
                messages.error(request, f"Error: Employee ID {new_emp_id} is already taken.")
                return redirect('edit_employee', emp_id=emp_id)

        # Check for duplicate Phone Number (excluding current employee)
        new_phone = update_data.get('Phone')
        if new_phone and new_phone != employee.get('Phone'):
            existing_phone = EmployeesTable.scan(
                FilterExpression="Phone = :p AND EmployeeID <> :eid",
                ExpressionAttributeValues={":p": new_phone, ":eid": emp_id}
            )
            if existing_phone:
                messages.error(request, f"Phone number {new_phone} is already registered to another employee.")
                return redirect('edit_employee', emp_id=emp_id)

        if new_emp_id and new_emp_id != emp_id:
            # 1. Migrate Employee Table (Copy then Delete)
            new_employee = employee.copy()
            new_employee['EmployeeID'] = new_emp_id
            for key, value in update_data.items():
                if value is not None: new_employee[key] = value
            EmployeesTable.put_item(new_employee)
            EmployeesTable.delete_item({'EmployeeID': emp_id})

            # 2. Update User record
            user_id = employee.get('UserID')
            if user_id:
                user = UsersTable.get_item({'UserID': user_id})
                if user:
                    user['EmployeeID'] = new_emp_id
                    user['Email'] = update_data.get('Email')
                    user['Role'] = request.POST.get('role')
                    UsersTable.put_item(user)

            # 3. Update Reporting Hierarchy (Manage subordinates & manager links)
            # Link subordinates to new ID
            subordinates = ReportingHierarchyTable.query(KeyConditionExpression=Key('ManagerID').eq(emp_id))
            for sub in subordinates:
                ReportingHierarchyTable.put_item({'ManagerID': new_emp_id, 'EmployeeID': sub['EmployeeID']})
                ReportingHierarchyTable.delete_item({'ManagerID': emp_id, 'EmployeeID': sub['EmployeeID']})
            
            # Link employee to their manager with new ID
            manager_links = ReportingHierarchyTable.scan(FilterExpression="EmployeeID = :eid", ExpressionAttributeValues={":eid": emp_id})
            for link in manager_links:
                ReportingHierarchyTable.put_item({'ManagerID': link['ManagerID'], 'EmployeeID': new_emp_id})
                ReportingHierarchyTable.delete_item({'ManagerID': link['ManagerID'], 'EmployeeID': emp_id})

            messages.success(request, f"Employee ID successfully updated to {new_emp_id}.")
            return redirect('employee_profile', emp_id=new_emp_id)
        
        if not new_emp_id or new_emp_id == emp_id:
            # Check for Intern to Permanent transition
            prev_type = employee.get('EmploymentType')
            new_type = update_data.get('EmploymentType')
            
            if prev_type == 'Intern' and new_type != 'Intern':
                # Transitioning to Permanent/Probation - Initialize Leaves
                eff_date_str = update_data.get('FullTimeDate') or update_data.get('JoinedDate') or get_local_date().isoformat()
                try:
                    eff_month = datetime.datetime.strptime(eff_date_str, '%Y-%m-%d').month
                except:
                    eff_month = get_local_date().month
                months_count = 12 - eff_month + 1
                prorated_val = str(float(max(1, months_count)))
                employee['Balance_SL'] = prorated_val
                employee['Balance_CL'] = prorated_val
                employee['LastLeaveRefresh'] = get_local_date().strftime('%Y-%m')

                # Manual PF handling message
                messages.info(request, f"Employee transitioned from Internship. Leaves have been initialized from this month. Please ensure PF and UAN numbers are manually updated in EPFO and recorded here.")
                    
                # Notify HR (first HR found)
                hr_users = [u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN']
                if hr_users:
                    send_notification(
                        employee_id=hr_users[0].get('EmployeeID'),
                        title="Manual PF Setup Required",
                        message=f"Employee {employee.get('FirstName')} {employee.get('LastName')} transitioned from Intern. Please update PF/UAN details manually.",
                        n_type='PF',
                        icon='fa-user-plus',
                        color='info'
                    )

            # Regular Update
            doc_fields = ['PassportPhoto', 'AadharCard', 'PanCard', 'Cert_10th', 'Cert_Inter', 'Cert_Degree', 'ExperienceLetter', 'RelievingLetter', 'PFLetter']
            doc_statuses = employee.get('DocumentStatuses', {})
            if not isinstance(doc_statuses, dict): doc_statuses = {}

            for key, value in update_data.items():
                if value is not None: 
                    employee[key] = value
                    # If HR uploads a doc during edit, mark it as Approved
                    if key in doc_fields:
                        doc_statuses[key] = 'Approved'
            
            employee['DocumentStatuses'] = doc_statuses
            EmployeesTable.put_item(employee)
            
            user_id = employee.get('UserID')
            if user_id:
                user = UsersTable.get_item({'UserID': user_id})
                if user:
                    user['Email'] = update_data.get('Email')
                    user['Role'] = request.POST.get('role')
                    UsersTable.put_item(user)

            # Update Manager link
            manager_id = request.POST.get('manager_id')
            if manager_id:
                # Remove existing links for this employee
                existing = ReportingHierarchyTable.scan(
                    FilterExpression="EmployeeID = :eid",
                    ExpressionAttributeValues={":eid": emp_id}
                )
                for item in existing:
                    ReportingHierarchyTable.delete_item({'ManagerID': item['ManagerID'], 'EmployeeID': emp_id})
                
                # Add new link
                ReportingHierarchyTable.put_item({
                    'ManagerID': manager_id,
                    'EmployeeID': emp_id
                })

            messages.success(request, f"Profile for {employee['FirstName']} updated.")
            return redirect('employee_profile', emp_id=emp_id)

class DownloadSampleCSVView(HRRequiredMixin, View):
    def get(self, request):
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="bulk_onboarding_template.csv"'
        
        writer = csv.writer(response)
        # Header
        writer.writerow([
            'Target Email', 'Designation / Job Title', 'Annual Salary', 'Department', 
            'Work Shift', 'Employment Type', 'Employment Status', 'System Role', 'Joining Date'
        ])
        # Sample Rows
        writer.writerow([
            'john.doe@example.com', 'Software Engineer', '1200000', 'Engineering', 
            'Day Shift', 'Permanent', 'Full Time', 'Employee', '2024-01-15'
        ])
        writer.writerow([
            'jane.smith@example.com', 'Sales Executive', '800000', 'Sales', 
            'Day Shift', 'Permanent', 'Probation', 'Employee', '2024-02-01'
        ])
        
        return response

class BulkOnboardingLinkView(HRRequiredMixin, View):
    def post(self, request):
        if 'onboarding_file' not in request.FILES:
            messages.error(request, "No file uploaded.")
            return redirect('add_employee')
        
        file = request.FILES['onboarding_file']
        if not file.name.endswith('.csv'):
            messages.error(request, "Only CSV files are supported.")
            return redirect('add_employee')
            
        try:
            import csv
            import uuid
            import datetime
            from io import StringIO
            from django.core.mail import send_mail
            from django.conf import settings
            
            file_data = file.read().decode('utf-8-sig')
            csv_data = csv.reader(StringIO(file_data), delimiter=',')
            
            header = next(csv_data, None)
            
            success_count = 0
            
            for row in csv_data:
                if len(row) < 9: continue
                target_email = row[0].strip()
                if not target_email: continue
                
                designation = row[1].strip()
                salary_pa = row[2].strip()
                department = row[3].strip()
                shift = row[4].strip() or 'Day Shift'
                employment_type = row[5].strip() or 'Permanent'
                employment_status = row[6].strip() or 'Full Time'
                role = row[7].strip() or 'Employee'
                joining_date = row[8].strip() or get_local_date().isoformat()
                
                employee_id = f"TEMP-{uuid.uuid4().hex[:8].upper()}"
                token = str(uuid.uuid4())
                
                OnboardingTokensTable.put_item({
                    'Token': token,
                    'CreatedAt': get_local_now().isoformat(),
                    'TargetEmail': target_email,
                    'EmployeeID': employee_id,
                    'SalaryPA': salary_pa,
                    'Department': department,
                    'Shift': shift,
                    'Role': role,
                    'Designation': designation,
                    'EmploymentType': employment_type,
                    'InternshipPeriod': '0',
                    'EmploymentStatus': employment_status,
                    'ProbationPeriod': '0',
                    'ManagerID': '',
                    'JoinedDate': joining_date,
                    'Used': False
                })
                
                link = request.build_absolute_uri(f'/employees/self-onboarding/{token}/')
                
                subject = 'Welcome to Lurnexa - Your Onboarding Link'
                message = f"""Hello,

Welcome to the team! To complete your onboarding process, please click the link below and fill in your details:

{link}

Please note: This link can only be used once.

Best Regards,
HR Team, Lurnexa"""
                
                try:
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [target_email],
                        fail_silently=True,
                    )
                    success_count += 1
                except Exception:
                    pass
                    
            messages.success(request, f"Successfully generated and sent {success_count} onboarding invitations.")
        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")
            
        return redirect('add_employee')

class GenerateOnboardingLinkView(HRRequiredMixin, View):
    def post(self, request):
        target_email = request.POST.get('target_email')
        employee_id = f"TEMP-{uuid.uuid4().hex[:8].upper()}"
        
        if not target_email:
            messages.error(request, "Target email is required.")
            return redirect('add_employee')

        token = str(uuid.uuid4())
        OnboardingTokensTable.put_item({
            'Token': token,
            'CreatedAt': get_local_now().isoformat(),
            'TargetEmail': target_email,
            'EmployeeID': employee_id,
            'SalaryPA': request.POST.get('salary_pa'),
            'Department': request.POST.get('department'),
            'Shift': request.POST.get('shift', 'Day Shift'),
            'Role': request.POST.get('role'),
            'Designation': request.POST.get('designation'),
            'EmploymentType': request.POST.get('employment_type', 'Permanent'),
            'InternshipPeriod': request.POST.get('internship_period', '0'),
            'EmploymentStatus': request.POST.get('employment_status', 'Full Time'),
            'ProbationPeriod': request.POST.get('probation_period', '0'),
            'ManagerID': request.POST.get('manager_id'),
            'JoinedDate': request.POST.get('joining_date'),
            'FullTimeDate': '' if request.POST.get('employment_type') == 'Intern' else (request.POST.get('fulltime_date') or request.POST.get('joining_date')),
            'Used': False
        })
        
        # Build absolute URL
        link = request.build_absolute_uri(f'/employees/self-onboarding/{token}/')
        
        # Send Email
        subject = 'Welcome to Lurnexa - Your Onboarding Link'
        message = f"""
        Hello,

        Welcome to the team! To complete your onboarding process, please click the link below and fill in your details:

        {link}

        Please note: This link can only be used once.

        Best Regards,
        HR Team, Lurnexa
        """
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [target_email],
                fail_silently=False,
            )
            messages.success(request, f"Onboarding link sent to {target_email}.")
        except Exception as e:
            messages.warning(request, f"Link generated but email failed to send: {str(e)}")

        return render(request, 'employees/add_employee.html', {
            'onboarding_link': link,
            'target_email': target_email,
            'managers': get_managers_list()
        })
class SelfOnboardingView(View):
    def get(self, request, token):
        token_data = OnboardingTokensTable.get_item({'Token': token})
        if not token_data or token_data.get('Used'):
            return render(request, 'core/error.html', {'message': 'This link has already been used or is invalid.'})
        
        # Check Expiration (24 Hours)
        created_at_str = token_data.get('CreatedAt')
        if created_at_str:
            try:
                from django.utils import timezone as django_timezone
                created_at = datetime.datetime.fromisoformat(created_at_str)
                if created_at.tzinfo is None:
                    created_at = django_timezone.make_aware(created_at, django_timezone.get_current_timezone())
                if get_local_now() - created_at > datetime.timedelta(hours=24):
                    return render(request, 'core/error.html', {'message': 'This onboarding link has expired. Please contact HR for a new link.'})
            except Exception as e:
                print(f"Error checking token expiration: {e}")

        return render(request, 'employees/self_onboarding.html', {
            'token': token,
            'target_email': token_data.get('TargetEmail'),
            'assigned_id': token_data.get('EmployeeID'),
            'token_data': token_data
        })

    def post(self, request, token):
        token_data = OnboardingTokensTable.get_item({'Token': token})
        if not token_data or token_data.get('Used'):
            return render(request, 'core/error.html', {'message': 'This link has already been used or is invalid.'})

        # Check Expiration (24 Hours)
        created_at_str = token_data.get('CreatedAt')
        if created_at_str:
            try:
                from django.utils import timezone as django_timezone
                created_at = datetime.datetime.fromisoformat(created_at_str)
                if created_at.tzinfo is None:
                    created_at = django_timezone.make_aware(created_at, django_timezone.get_current_timezone())
                if get_local_now() - created_at > datetime.timedelta(hours=24):
                    return render(request, 'core/error.html', {'message': 'This onboarding link has expired. Please contact HR for a new link.'})
            except Exception as e:
                print(f"Error checking token expiration: {e}")

        email = request.POST.get('email')
        if not email:
            email = token_data.get('TargetEmail')
        if not email:
            messages.error(request, "Email is missing from the request.")
            return render(request, 'employees/self_onboarding.html', {'token': token})
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        dob = request.POST.get('dob')
        gender = request.POST.get('gender')

        aadhar_number = request.POST.get('aadhar_number', '').strip()
        pan_number = request.POST.get('pan_number', '').strip().upper()

        if not aadhar_number or not aadhar_number.isdigit() or len(aadhar_number) != 12:
            messages.error(request, "Invalid Aadhar Number. It must be exactly 12 digits.")
            return render(request, 'employees/self_onboarding.html', {'token': token})

        import re
        if not pan_number or not re.match(r'^[A-Z0-9]{10}$', pan_number):
            messages.error(request, "Invalid PAN Number. It must be exactly 10 alphanumeric characters.")
            return render(request, 'employees/self_onboarding.html', {'token': token})

        # --- Age Validation (Min 21) ---
        if dob:
            try:
                dob_dt = datetime.datetime.strptime(dob, '%Y-%m-%d').date()
                today = get_local_date()
                age = today.year - dob_dt.year - ((today.month, today.day) < (dob_dt.month, dob_dt.day))
                if age < 21:
                    messages.error(request, f"Onboarding failed: You must be at least 21 years old to join Lurnexa (Current age: {age}).")
                    return render(request, 'employees/self_onboarding.html', {'token': token})
            except ValueError:
                pass

        # Uniqueness checks
        existing_user = UsersTable.query(
            IndexName='EmailIndex',
            KeyConditionExpression=Key('Email').eq(email)
        )
        if existing_user:
            messages.error(request, "User with this email already exists.")
            return render(request, 'employees/self_onboarding.html', {'token': token})

        phone = request.POST.get('phone')
        if phone:
            existing_phone = EmployeesTable.scan(
                FilterExpression="Phone = :p",
                ExpressionAttributeValues={":p": phone}
            )
            if existing_phone:
                messages.error(request, f"Phone number {phone} is already registered.")
                return render(request, 'employees/self_onboarding.html', {'token': token})

        user_id = str(uuid.uuid4())
        # Use the employee_id assigned by HR in the token
        employee_id = token_data.get('EmployeeID')
        if not employee_id:
            return render(request, 'core/error.html', {'message': 'Invalid onboarding token: Employee ID missing.'})

        # Password Validation
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'employees/self_onboarding.html', {'token': token, 'target_email': email, 'assigned_id': token_data.get('EmployeeID')})

        # Stricter Password Policy: Min 8 chars, Uppercase, Lowercase, Number, Special Char
        password_regex = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$'
        if not re.match(password_regex, password):
            messages.error(request, "Password is too weak. It must be at least 8 characters long and include uppercase letters, lowercase letters, numbers, and special characters.")
            return render(request, 'employees/self_onboarding.html', {'token': token, 'target_email': email, 'assigned_id': token_data.get('EmployeeID')})

        hashed_pw = bcrypt.hashpw(password.encode('utf-8')[:72], bcrypt.gensalt()).decode('utf-8')

        user_item = {
            'UserID': user_id,
            'Email': email,
            'Role': token_data.get('Role', 'Employee'),
            'PasswordHash': hashed_pw,
            'EmployeeID': employee_id,
            'IsActive': True
        }
        UsersTable.put_item(user_item)

        employee_item = {
            'EmployeeID': employee_id,
            'UserID': user_id,
            'Email': email,
            'FirstName': first_name,
            'LastName': last_name,
            'Designation': token_data.get('Designation', 'Employee'),
            'EmploymentType': token_data.get('EmploymentType', 'Permanent'),
            'InternshipPeriod': token_data.get('InternshipPeriod', '0'),
            'EmploymentStatus': token_data.get('EmploymentStatus', 'Full Time'),
            'ProbationPeriod': token_data.get('ProbationPeriod', '0'),
            'Department': token_data.get('Department'),
            'Shift': token_data.get('Shift', 'Day Shift'),
            'SalaryPA': token_data.get('SalaryPA'),
            'FatherName': request.POST.get('father_name'),
            'MotherName': request.POST.get('mother_name'),
            'SpouseName': request.POST.get('spouse_name'),
            'EmergencyContactName': request.POST.get('emergency_contact_name'),
            'EmergencyContactRelation': request.POST.get('emergency_relation'),
            'EmergencyContactPhone': request.POST.get('emergency_phone'),
            'Phone': request.POST.get('phone'),
            'Address': request.POST.get('address'),
            'Education': request.POST.get('education'),
            'City': request.POST.get('city'),
            'BankName': request.POST.get('bank_name'),
            'AccountNumber': request.POST.get('account_number'),
            'IFSCCode': request.POST.get('ifsc_code'),
            'PassportPhoto': save_uploaded_file(request.FILES.get('passport_photo'), 'employees/photos'),
            'AadharCard': save_uploaded_file(request.FILES.get('aadhar_card'), 'employees/docs'),
            'AadharNumber': aadhar_number,
            'PanCard': save_uploaded_file(request.FILES.get('pan_card'), 'employees/docs'),
            'PanNumber': pan_number,
            'Cert_10th': save_uploaded_file(request.FILES.get('cert_10th'), 'employees/certs'),
            'Cert_Inter': save_uploaded_file(request.FILES.get('cert_inter'), 'employees/certs'),
            'Cert_Degree': save_uploaded_file(request.FILES.get('cert_degree'), 'employees/certs'),
            'ExperienceLetter': save_uploaded_file(request.FILES.get('exp_letter'), 'employees/docs'),
            'RelievingLetter': save_uploaded_file(request.FILES.get('relieving_letter'), 'employees/docs'),
            'PFLetter': save_uploaded_file(request.FILES.get('pf_letter'), 'employees/docs'),
            'JoinedDate': token_data.get('JoinedDate', get_local_date().isoformat()),
            'FullTimeDate': '' if token_data.get('EmploymentType') == 'Intern' else (token_data.get('FullTimeDate') or token_data.get('JoinedDate') or get_local_date().isoformat()),
            'DOB': request.POST.get('dob') or token_data.get('DOB'),
            'Gender': gender,
            'IsExperienced': request.POST.get('is_experienced') == 'on',
            'PreviousCompany': request.POST.get('previous_company'),
            'LastDesignation': request.POST.get('last_designation'),
            'ExperienceYears': request.POST.get('experience_years'),
            'PrevLastWorkingDate': request.POST.get('last_working_date'),
            'PFNumber': request.POST.get('pf_number'),
            'UANNumber': request.POST.get('uan_number'),
            'OnboardingStatus': 'Pending Review',
            'DocumentStatuses': {
                'PassportPhoto': 'Pending' if request.FILES.get('passport_photo') else None,
                'AadharCard': 'Pending' if request.FILES.get('aadhar_card') else None,
                'PanCard': 'Pending' if request.FILES.get('pan_card') else None,
                'Cert_10th': 'Pending' if request.FILES.get('cert_10th') else None,
                'Cert_Inter': 'Pending' if request.FILES.get('cert_inter') else None,
                'Cert_Degree': 'Pending' if request.FILES.get('cert_degree') else None,
                'ExperienceLetter': 'Pending' if request.FILES.get('exp_letter') else None,
                'RelievingLetter': 'Pending' if request.FILES.get('relieving_letter') else None,
                'PFLetter': 'Pending' if request.FILES.get('pf_letter') else None
            },
            'Balance_PL': '0.0',
            'Balance_SL': '0.0' if token_data.get('EmploymentType') == 'Intern' else str(float(max(1, 12 - int((token_data.get('FullTimeDate') or token_data.get('JoinedDate') or get_local_date().isoformat()).split('-')[1]) + 1))),
            'Balance_CL': '0.0' if token_data.get('EmploymentType') == 'Intern' else str(float(max(1, 12 - int((token_data.get('FullTimeDate') or token_data.get('JoinedDate') or get_local_date().isoformat()).split('-')[1]) + 1))),
            'Balance_CO': '0.0',
            'LastLeaveRefresh': get_local_date().strftime('%Y-%m')
        }
        EmployeesTable.put_item(employee_item)

        # Handle Reporting Hierarchy
        manager_id = token_data.get('ManagerID')
        if manager_id:
            ReportingHierarchyTable.put_item({
                'ManagerID': manager_id,
                'EmployeeID': employee_id
            })

        # Mark token as used
        token_data['Used'] = True
        OnboardingTokensTable.put_item(token_data)

        # Notify HR of new onboarding submission
        try:
            hr_users = [u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN']
            for hr in hr_users:
                send_notification(
                    employee_id=hr['EmployeeID'],
                    title='New Onboarding Verification',
                    message=f"New onboarding details submitted by {employee_item['FirstName']} {employee_item['LastName']} ({employee_id}). Please review.",
                    n_type='Onboarding',
                    icon='fa-user-check',
                    color='primary'
                )
        except Exception as e:
            print(f"Error notifying HR: {e}")

        # Send confirmation email to the employee
        try:
            from django.core.mail import send_mail
            from django.conf import settings
            subject = 'Onboarding Details Submitted Successfully'
            message = f"""Hello {employee_item['FirstName']},

You have successfully submitted your details for the onboarding process.
Our HR team will now check and approve your onboarding process. 
We will notify you once it's approved or if any further action is required from your side.

Best Regards,
HR Team, Lurnexa
"""
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"Error sending confirmation email to employee: {e}")

        return render(request, 'core/success.html', {
            'message': 'Onboarding details submitted! Your documents are now under HR review. You will be able to access the portal once approved.'
        })

class OnboardingRequestsView(HRAdminOnlyMixin, TemplateView):
    template_name = 'employees/onboarding_requests.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_employees = EmployeesTable.scan()
        context['pending_requests'] = [e for e in all_employees if e.get('OnboardingStatus') == 'Pending Review']
        context['rejected_requests'] = [e for e in all_employees if e.get('OnboardingStatus') == 'Rejected']
        return context

class ReviewOnboardingView(HRAdminOnlyMixin, TemplateView):
    template_name = 'employees/review_onboarding.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        emp_id = self.kwargs.get('emp_id')
        context['employee'] = EmployeesTable.get_item({'EmployeeID': emp_id})
        context['document_fields'] = [
            ('PassportPhoto', 'Passport Photo'),
            ('AadharCard', 'Aadhar Card'),
            ('PanCard', 'PAN Card'),
            ('Cert_10th', '10th Marksheet'),
            ('Cert_Inter', 'Intermediate Marksheet'),
            ('Cert_Degree', 'Degree Certificate'),
            ('ExperienceLetter', 'Experience Letter'),
            ('RelievingLetter', 'Relieving Letter'),
            ('PFLetter', 'PF Letter')
        ]
        return context

class ApproveOnboardingActionView(HRAdminOnlyMixin, View):
    def post(self, request, emp_id):
        import json
        action = request.POST.get('action') # 'approve' or 'reject'
        reason = request.POST.get('reason', '')
        doc_statuses_json = request.POST.get('doc_statuses', '{}')
        doc_statuses = json.loads(doc_statuses_json)
        
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if not employee:
            messages.error(request, "Employee not found.")
            return redirect('onboarding_requests')

        # Update individual document statuses (merge with existing)
        current_statuses = employee.get('DocumentStatuses', {})
        if not isinstance(current_statuses, dict):
            current_statuses = {}
        
        current_statuses.update(doc_statuses)
        employee['DocumentStatuses'] = current_statuses
        employee['RejectionReason'] = reason

        if action == 'approve':
            new_employee_id = request.POST.get('new_employee_id')
            if not new_employee_id:
                messages.error(request, "Employee ID is required for approval.")
                return redirect('review_onboarding', emp_id=emp_id)
                
            if EmployeesTable.get_item({'EmployeeID': new_employee_id}):
                messages.error(request, f"Employee ID {new_employee_id} is already in use.")
                return redirect('review_onboarding', emp_id=emp_id)

            # Check if ANY uploaded document is rejected or pending review
            uploaded_docs = [f for f, l in [
                ('PassportPhoto', 'P'), ('AadharCard', 'A'), ('PanCard', 'PA'), 
                ('Cert_10th', '10'), ('Cert_Inter', 'I'), ('Cert_Degree', 'D'),
                ('ExperienceLetter', 'E'), ('RelievingLetter', 'R'), ('PFLetter', 'PF')
            ] if employee.get(f)]
            
            all_approved = all(current_statuses.get(field) == 'Approved' for field in uploaded_docs)
            
            if all_approved:
                employee['OnboardingStatus'] = 'Approved'
                
                # Migrate to new Employee ID
                new_employee = employee.copy()
                new_employee['EmployeeID'] = new_employee_id
                EmployeesTable.put_item(new_employee)
                EmployeesTable.delete_item({'EmployeeID': emp_id})
                employee = new_employee
                emp_id = new_employee_id
                
                # Update User record
                user_id = employee.get('UserID')
                if user_id:
                    user = UsersTable.get_item({'UserID': user_id})
                    if user:
                        user['EmployeeID'] = new_employee_id
                        UsersTable.put_item(user)

                # Update Manager link
                manager_links = ReportingHierarchyTable.scan(FilterExpression="EmployeeID = :eid", ExpressionAttributeValues={":eid": emp_id})
                for link in manager_links:
                    ReportingHierarchyTable.put_item({'ManagerID': link['ManagerID'], 'EmployeeID': new_employee_id})
                    ReportingHierarchyTable.delete_item({'ManagerID': link['ManagerID'], 'EmployeeID': emp_id})
                
                messages.success(request, f"Onboarding for {employee['FirstName']} approved and activated with ID {new_employee_id}.")
            else:
                employee['OnboardingStatus'] = 'Rejected'
                messages.warning(request, f"Cannot activate {employee['FirstName']} as some documents are still rejected or pending review.")
                EmployeesTable.put_item(employee)
        else:
            employee['OnboardingStatus'] = 'Rejected'
            messages.warning(request, f"Onboarding for {employee['FirstName']} rejected.")
            EmployeesTable.put_item(employee)

        # --- Send Notification to Employee ---
        emp_email = employee.get('Email')
        if emp_email:
            if action == 'approve' and employee['OnboardingStatus'] == 'Approved':
                email_subj = "Onboarding Approved - Welcome to Lurnexa!"
                email_body = f"Hi {employee['FirstName']},\n\nCongratulations! Your onboarding details and documents have been verified and approved. You can now log in to the Lurnexa HR Admin portal using your credentials.\n\nLink: {request.build_absolute_uri('/')}\n\nWelcome to the team!\n\nBest regards,\nLurnexa HR Admin"
            elif action == 'reject' or employee['OnboardingStatus'] == 'Rejected':
                email_subj = "Onboarding Update - Action Required"
                email_body = f"Hi {employee['FirstName']},\n\nYour onboarding submission requires some updates. Please log in to the onboarding status page to review the feedback and re-submit your details or documents.\n\nReason/Feedback: {reason}\n\nBest regards,\nLurnexa HR Admin"
            
            try:
                send_notification(
                    employee_id=emp_id,
                    title="Onboarding Approved" if action == 'approve' and employee['OnboardingStatus'] == 'Approved' else "Onboarding Update",
                    message=f"Your onboarding has been {employee['OnboardingStatus'].lower()}.",
                    n_type='Onboarding',
                    icon='fa-user-check' if action == 'approve' else 'fa-user-times',
                    color='success' if action == 'approve' else 'danger',
                    email_subject=email_subj,
                    email_body=email_body
                )
            except Exception as e:
                print(f"Error sending onboarding email: {e}")
        
        return redirect('onboarding_requests')

class OnboardingStatusView(LoginRequiredMixin, TemplateView):
    template_name = 'employees/onboarding_status.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['employee'] = EmployeesTable.get_item({'EmployeeID': self.request.user.employee_id})
        context['document_fields'] = [
            ('PassportPhoto', 'Passport Photo'),
            ('AadharCard', 'Aadhar Card'),
            ('PanCard', 'PAN Card'),
            ('Cert_10th', '10th Marksheet'),
            ('Cert_Inter', 'Intermediate Marksheet'),
            ('Cert_Degree', 'Degree Certificate'),
            ('ExperienceLetter', 'Experience Letter'),
            ('RelievingLetter', 'Relieving Letter'),
            ('PFLetter', 'PF Letter')
        ]
        return context

class ReuploadDocumentsView(LoginRequiredMixin, View):
    def post(self, request):
        emp_id = request.user.employee_id
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        
        if not employee:
            return redirect('login')

        # Update only provided files - Match the field names in onboarding_status.html
        fields = ['PassportPhoto', 'AadharCard', 'PanCard', 'Cert_10th', 'Cert_Inter', 'Cert_Degree', 'ExperienceLetter', 'RelievingLetter', 'PFLetter']
        updated = False
        
        for field in fields:
            if request.FILES.get(field):
                folder = 'employees/photos' if field == 'PassportPhoto' else ('employees/certs' if field.startswith('Cert') else 'employees/docs')
                employee[field] = save_uploaded_file(request.FILES.get(field), folder)
                
                # Reset individual status to Pending for HR to review again
                if 'DocumentStatuses' not in employee:
                    employee['DocumentStatuses'] = {}
                employee['DocumentStatuses'][field] = 'Pending'
                updated = True

        if updated:
            employee['OnboardingStatus'] = 'Pending Review'
            # Clear rejection reason as new attempt is made
            employee['RejectionReason'] = ''
            EmployeesTable.put_item(employee)

            # Notify HR of document re-submission
            try:
                hr_users = [u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN']
                for hr in hr_users:
                    send_notification(
                        employee_id=hr['EmployeeID'],
                        title='Documents Re-submitted',
                        message=f"{employee['FirstName']} {employee['LastName']} ({employee['EmployeeID']}) has re-submitted documents for verification.",
                        n_type='Onboarding',
                        icon='fa-file-circle-check',
                        color='info'
                    )
            except Exception as e:
                print(f"Error notifying HR: {e}")

            messages.success(request, "Documents re-submitted successfully. HR will review them again.")
        
        return redirect('onboarding_status')

class ToggleActiveStatusView(HRRequiredMixin, View):
    def get(self, request, emp_id):
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if not employee:
            messages.error(request, "Employee not found.")
            return redirect('employee_directory')
        
        user_id = employee.get('UserID')
        if not user_id:
            messages.error(request, "User record not found for this employee.")
            return redirect('employee_directory')
            
        user = UsersTable.get_item({'UserID': user_id})
        if not user:
            messages.error(request, "User record not found.")
            return redirect('employee_directory')
            
        # Toggle IsActive
        is_active = user.get('IsActive', True)
        new_status = not is_active
        
        try:
            # Update Users Table
            UsersTable.update_item(
                Key={'UserID': user_id},
                UpdateExpression="SET IsActive = :val",
                ExpressionAttributeValues={':val': new_status}
            )
            
            # Update Employees Table to keep in sync
            update_expr = "SET IsActive = :val"
            expr_vals = {':val': new_status}
            
            # If activating an employee, handle status and LastWorkingDate
            if new_status: # Activating
                status = employee.get('OnboardingStatus')
                lwd_str = employee.get('LastWorkingDate')
                
                # Check if they have an LWD in the past
                is_past_lwd = False
                if lwd_str:
                    try:
                        lwd = datetime.datetime.strptime(lwd_str, '%Y-%m-%d').date()
                        if datetime.date.today() > lwd:
                            is_past_lwd = True
                    except:
                        pass
                
                # If they were resigned or have a past LWD, reset to Approved and clear LWD
                # This prevents the login auto-deactivation from triggering.
                if status in ['Resigned', 'Accepted Resignation'] or is_past_lwd:
                    update_expr += ", OnboardingStatus = :s, LastWorkingDate = :lwd"
                    expr_vals[':s'] = 'Approved'
                    expr_vals[':lwd'] = None
            
            EmployeesTable.update_item(
                Key={'EmployeeID': emp_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_vals
            )
            
            status_text = "activated" if new_status else "inactivated"
            messages.success(request, f"Profile for {employee.get('FirstName')} has been {status_text}.")
        except Exception as e:
            messages.error(request, f"Error updating status: {e}")
            
        # Redirect back to where we came from if possible
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect('employee_directory')

class MoveToExEmployeeView(HRRequiredMixin, View):
    def get(self, request, emp_id):
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if not employee:
            messages.error(request, "Employee not found.")
            return redirect('employee_directory')
            
        try:
            today_str = datetime.date.today().strftime('%Y-%m-%d')
            
            # Update Employees Table
            EmployeesTable.update_item(
                Key={'EmployeeID': emp_id},
                UpdateExpression="SET OnboardingStatus = :status, LastWorkingDate = :lwd, IsActive = :active",
                ExpressionAttributeValues={
                    ':status': 'Resigned',
                    ':lwd': today_str,
                    ':active': False
                }
            )
            
            # Update Users Table
            user_id = employee.get('UserID')
            if user_id:
                UsersTable.update_item(
                    Key={'UserID': user_id},
                    UpdateExpression="SET IsActive = :active",
                    ExpressionAttributeValues={':active': False}
                )
                
            messages.success(request, f"{employee.get('FirstName')} has been moved to Ex-Employees directory with Last Working Date set to today ({today_str}).")
        except Exception as e:
            messages.error(request, f"Error moving employee to ex-employee: {e}")
            
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect('employee_directory')

class DeleteEmployeeView(HRRequiredMixin, View):
    def post(self, request, emp_id):
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if not employee:
            messages.error(request, "Employee not found.")
            return redirect('employee_directory')
            
        user_id = employee.get('UserID')
        
        try:
            # 1. Delete from Employees Table
            EmployeesTable.delete_item({'EmployeeID': emp_id})
            
            # 2. Delete from Users Table
            if user_id:
                UsersTable.delete_item({'UserID': user_id})
            
            # 3. Delete from Reporting Hierarchy
            subordinates = ReportingHierarchyTable.query(KeyConditionExpression=Key('ManagerID').eq(emp_id))
            for sub in subordinates:
                ReportingHierarchyTable.delete_item({'ManagerID': emp_id, 'EmployeeID': sub['EmployeeID']})
            
            manager_links = ReportingHierarchyTable.scan(
                FilterExpression="EmployeeID = :eid",
                ExpressionAttributeValues={":eid": emp_id}
            )
            for link in manager_links:
                ReportingHierarchyTable.delete_item({'ManagerID': link['ManagerID'], 'EmployeeID': emp_id})
                
            # 4. Delete related data from other tables
            
            # Leave Requests
            leaves = LeaveRequestsTable.query(KeyConditionExpression=Key('EmployeeID').eq(emp_id))
            for l in leaves:
                LeaveRequestsTable.delete_item({'EmployeeID': emp_id, 'LeaveDate': l['LeaveDate']})
                
            # Attendance
            attendance = AttendanceTable.query(KeyConditionExpression=Key('EmployeeID').eq(emp_id))
            for a in attendance:
                AttendanceTable.delete_item({'EmployeeID': emp_id, 'RecordDate': a['RecordDate']})
                
            # Payslips
            payslips = PayslipsTable.query(KeyConditionExpression=Key('EmployeeID').eq(emp_id))
            for p in payslips:
                PayslipsTable.delete_item({'EmployeeID': emp_id, 'MonthYear': p['MonthYear']})
                
            # Expenses
            expenses = ExpensesTable.query(KeyConditionExpression=Key('EmployeeID').eq(emp_id))
            for e in expenses:
                ExpensesTable.delete_item({'EmployeeID': emp_id, 'RequestID': e['RequestID']})
                

            
            # Resignations
            ResignationsTable.delete_item({'EmployeeID': emp_id})
            
            # Login History
            if user_id:
                history = LoginHistoryTable.query(KeyConditionExpression=Key('UserID').eq(user_id))
                for h in history:
                    LoginHistoryTable.delete_item({'UserID': user_id, 'LoginTime': h['LoginTime']})
            
            # Notifications
            notifications = NotificationsTable.query(KeyConditionExpression=Key('EmployeeID').eq(emp_id))
            for n in notifications:
                NotificationsTable.delete_item({'EmployeeID': emp_id, 'Timestamp': n['Timestamp']})
                
            messages.success(request, f"Employee {employee.get('FirstName')} and all associated data have been permanently deleted.")
        except Exception as e:
            messages.error(request, f"Error during deletion: {e}")
            
        return redirect('employee_directory')

class EmployeeLettersView(LoginRequiredMixin, TemplateView):
    template_name = 'documents/employee_letters.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from core.dynamodb_service import EmployeeLettersTable
        from boto3.dynamodb.conditions import Key
        
        user_emp_id = self.request.user.employee_id
        try:
            letters = EmployeeLettersTable.query(KeyConditionExpression=Key('EmployeeID').eq(user_emp_id))
            # Sort letters by GeneratedDate descending
            letters.sort(key=lambda x: x.get('GeneratedDate', ''), reverse=True)
            context['letters'] = letters
        except Exception as e:
            print(f"Error fetching letters: {e}")
            context['letters'] = []
            
        return context

class PrintLetterView(LoginRequiredMixin, View):
    def get(self, request, letter_id):
        from core.dynamodb_service import EmployeeLettersTable
        from boto3.dynamodb.conditions import Key
        from django.http import HttpResponse, Http404
        
        # Allow HR Admin to view other employees' letters if emp_id query param is present
        emp_id = request.GET.get('emp_id')
        if not emp_id or request.user.role not in ['HR ADMIN', 'HR']:
            emp_id = request.user.employee_id

        try:
            # LetterID is RANGE key, EmployeeID is HASH key
            letter = EmployeeLettersTable.get_item({'EmployeeID': emp_id, 'LetterID': letter_id})
            if not letter:
                raise Http404("Letter not found.")
                
            file_path = letter.get('FilePath')
            if file_path:
                from django.core.files.storage import default_storage
                from django.http import FileResponse
                import mimetypes, os
                
                try:
                    file_obj = default_storage.open(file_path, 'rb')
                    content_type, _ = mimetypes.guess_type(file_path)
                    
                    # Force download
                    response = FileResponse(file_obj, content_type=content_type or 'application/octet-stream')
                    filename = os.path.basename(file_path)
                    response['Content-Disposition'] = f'attachment; filename="{filename}"'
                    return response
                except Exception as e:
                    print(f"Error opening file from storage: {e}")
                    raise Http404("Letter file not found.")
                
            # Fallback for old content-based letters if any remain
            content = letter.get('Content', '')
            if content:
                response = HttpResponse(content, content_type='text/html')
                response['Content-Disposition'] = f'attachment; filename="Letter_{letter_id}.html"'
                return response
                
            raise Http404("Letter content not found.")
        except Exception as e:
            print(f"Error printing letter: {e}")
            raise Http404("Letter not found.")


class VerifyPasswordView(LoginRequiredMixin, View):
    def post(self, request):
        from django.http import JsonResponse
        from django.contrib.auth.hashers import check_password
        import json
        import bcrypt
        
        try:
            data = json.loads(request.body)
            password = data.get('password')
        except Exception:
            password = request.POST.get('password')
            
        if not password:
            return JsonResponse({'valid': False, 'error': 'Password is required'}, status=400)
            
        user_rec = UsersTable.get_item({'UserID': request.user.user_id})
        if not user_rec:
            return JsonResponse({'valid': False, 'error': 'User not found'}, status=404)
            
        hashed = user_rec.get('PasswordHash', '')
        if not hashed:
            hashed = user_rec.get('Password', '')
            
        is_valid = False
        # 1. Try Django's check_password first
        if check_password(password, hashed):
            is_valid = True
        else:
            # 2. Fallback to raw bcrypt for legacy users
            try:
                # Ensure we are dealing with strings or bytes correctly
                hashed_bytes = hashed.encode('utf-8') if isinstance(hashed, str) else hashed
                if bcrypt.checkpw(password.encode('utf-8')[:72], hashed_bytes):
                    is_valid = True
            except Exception:
                pass
                
        if is_valid:
            return JsonResponse({'valid': True})
        else:
            return JsonResponse({'valid': False, 'error': 'Incorrect password'})


class UploadCertificateView(LoginRequiredMixin, View):
    def post(self, request, emp_id):
        import os
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if not employee:
            messages.error(request, "Employee not found.")
            return redirect(f"/employees/profile/{emp_id}/?tab=cert")

        # Access check: Only the employee themselves or HR Admin can upload
        if request.user.employee_id != emp_id and request.user.role != 'HR ADMIN':
            messages.error(request, "Unauthorized to upload certificates for this employee.")
            return redirect(f"/employees/profile/{emp_id}/?tab=cert")

        uploaded_file = request.FILES.get('certificate_file')
        cert_name = request.POST.get('certificate_name', '').strip()

        if not uploaded_file or not cert_name:
            messages.error(request, "Certificate name and file are required.")
            return redirect(f"/employees/profile/{emp_id}/?tab=cert")

        # Enforce 10MB limit
        if uploaded_file.size > 10 * 1024 * 1024:
            messages.error(request, "File size exceeds the 10MB limit.")
            return redirect(f"/employees/profile/{emp_id}/?tab=cert")

        # Enforce file extension check
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ['.pdf', '.png', '.jpg', '.jpeg']:
            messages.error(request, "Invalid file format. Only PDF, PNG, JPG, and JPEG are allowed.")
            return redirect(f"/employees/profile/{emp_id}/?tab=cert")

        # Save file to static/employees/certs
        file_path = save_uploaded_file(uploaded_file, 'employees/certs')
        if not file_path:
            messages.error(request, "Failed to save the uploaded file.")
            return redirect(f"/employees/profile/{emp_id}/?tab=cert")

        # Initialize certificates list if not exists
        certs = employee.get('Certificates', [])
        if not isinstance(certs, list):
            certs = []

        new_cert = {
            'CertificateID': str(uuid.uuid4()),
            'Name': cert_name,
            'FilePath': file_path,
            'UploadedAt': get_local_now().isoformat(),
            'Status': 'Pending',
            'RejectionReason': ''
        }
        certs.append(new_cert)
        employee['Certificates'] = certs
        EmployeesTable.put_item(employee)

        # Notify HR Admin
        try:
            hr_users = [u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN']
            for hr in hr_users:
                send_notification(
                    employee_id=hr.get('EmployeeID'),
                    title="Certificate Verification Required",
                    message=f"{employee.get('FirstName')} {employee.get('LastName')} uploaded a new certificate: {cert_name}.",
                    n_type="Certificate",
                    icon="fa-stamp",
                    color="warning"
                )
        except Exception as e:
            print(f"Error sending HR notification: {e}")

        messages.success(request, f"Certificate '{cert_name}' uploaded successfully and is pending HR approval.")
        return redirect(f"/employees/profile/{emp_id}/?tab=cert")


class CertificateApprovalsView(HRAdminOnlyMixin, TemplateView):
    template_name = 'employees/certificate_approvals.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_employees = EmployeesTable.scan()
        pending_requests = []

        for emp in all_employees:
            certs = emp.get('Certificates', [])
            if isinstance(certs, list):
                for cert in certs:
                    if isinstance(cert, dict) and cert.get('Status') == 'Pending':
                        pending_requests.append({
                            'EmployeeID': emp.get('EmployeeID'),
                            'FirstName': emp.get('FirstName'),
                            'LastName': emp.get('LastName'),
                            'PassportPhoto': emp.get('PassportPhoto'),
                            'Department': emp.get('Department'),
                            'CertificateID': cert.get('CertificateID'),
                            'Name': cert.get('Name'),
                            'FilePath': cert.get('FilePath'),
                            'UploadedAt': cert.get('UploadedAt')
                        })

        # Sort newest uploaded first
        pending_requests.sort(key=lambda x: x.get('UploadedAt', ''), reverse=True)
        context['pending_requests'] = pending_requests
        return context


class CertificateActionView(HRAdminOnlyMixin, View):
    def post(self, request, emp_id, cert_id):
        action = request.POST.get('action') # 'approve' or 'reject'
        reason = request.POST.get('reason', '').strip()

        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if not employee:
            messages.error(request, "Employee not found.")
            return redirect('certificate_approvals')

        certs = employee.get('Certificates', [])
        if not isinstance(certs, list):
            messages.error(request, "No certificates found.")
            return redirect('certificate_approvals')

        target_cert = None
        for cert in certs:
            if isinstance(cert, dict) and cert.get('CertificateID') == cert_id:
                target_cert = cert
                break

        if not target_cert:
            messages.error(request, "Certificate not found.")
            return redirect('certificate_approvals')

        if action == 'approve':
            target_cert['Status'] = 'Approved'
            target_cert['ApprovedAt'] = get_local_now().isoformat()
            target_cert['RejectionReason'] = ''
            messages.success(request, f"Certificate '{target_cert.get('Name')}' approved for {employee.get('FirstName')}.")
        elif action == 'reject':
            target_cert['Status'] = 'Rejected'
            target_cert['RejectionReason'] = reason or 'No reason provided.'
            messages.warning(request, f"Certificate '{target_cert.get('Name')}' rejected.")
        else:
            messages.error(request, "Invalid action.")
            return redirect('certificate_approvals')

        employee['Certificates'] = certs
        EmployeesTable.put_item(employee)

        # Notify employee
        try:
            send_notification(
                employee_id=emp_id,
                title="Certificate Approved" if action == 'approve' else "Certificate Rejected",
                message=f"Your certificate '{target_cert.get('Name')}' has been {'approved' if action == 'approve' else 'rejected'} by HR.",
                n_type="Certificate",
                icon="fa-circle-check" if action == 'approve' else "fa-circle-xmark",
                color="success" if action == 'approve' else "danger"
            )
        except Exception as e:
            print(f"Error sending employee notification: {e}")

        return redirect('certificate_approvals')


class DeleteCertificateView(LoginRequiredMixin, View):
    def post(self, request, emp_id, cert_id):
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if not employee:
            messages.error(request, "Employee not found.")
            return redirect(f"/employees/profile/{emp_id}/?tab=cert")

        # Access check: Only the employee themselves or HR Admin can delete
        if request.user.employee_id != emp_id and request.user.role != 'HR ADMIN':
            messages.error(request, "Unauthorized to delete certificates for this employee.")
            return redirect(f"/employees/profile/{emp_id}/?tab=cert")

        certs = employee.get('Certificates', [])
        if not isinstance(certs, list):
            messages.error(request, "No certificates found.")
            return redirect(f"/employees/profile/{emp_id}/?tab=cert")

        # Find target certificate
        target_cert = None
        for cert in certs:
            if isinstance(cert, dict) and cert.get('CertificateID') == cert_id:
                target_cert = cert
                break

        if not target_cert:
            messages.error(request, "Certificate not found.")
            return redirect(f"/employees/profile/{emp_id}/?tab=cert")

        # Enforce rule: Verified (Approved) certificates can only be deleted by HR ADMIN
        if target_cert.get('Status') == 'Approved' and request.user.role != 'HR ADMIN':
            messages.error(request, "Only HR Admin can delete verified certificates.")
            return redirect(f"/employees/profile/{emp_id}/?tab=cert")

        # Filter out the certificate to be deleted
        new_certs = [c for c in certs if isinstance(c, dict) and c.get('CertificateID') != cert_id]

        employee['Certificates'] = new_certs
        EmployeesTable.put_item(employee)

        messages.success(request, "Certificate deleted successfully.")
        return redirect(f"/employees/profile/{emp_id}/?tab=cert")


class AssetManagementView(HRRequiredMixin, TemplateView):
    template_name = 'employees/assets.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from core.dynamodb_service import AssetsTable, EmployeesTable
        
        # Get all registered assets
        assets = AssetsTable.scan()
        all_employees = EmployeesTable.scan()
        
        # Enrich asset data with assignee name
        import json
        for asset in assets:
            assigned_to = asset.get('AssignedTo')
            if assigned_to:
                emp = next((e for e in all_employees if e.get('EmployeeID') == assigned_to), None)
                if emp:
                    asset['AssigneeName'] = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}"
                else:
                    asset['AssigneeName'] = assigned_to
            else:
                asset['AssigneeName'] = 'Unassigned'
                
            history = asset.get('History', [])
            if not isinstance(history, list):
                history = []
            asset['HistoryJSON'] = json.dumps(history)
                
        context['assets'] = assets
        
        # Get all asset complaints & exchange requests
        from core.dynamodb_service import AssetRequestsTable
        asset_requests = []
        pending_requests_count = 0
        try:
            asset_requests = AssetRequestsTable.scan()
            asset_requests.sort(key=lambda x: x.get('CreatedAt', ''), reverse=True)
            pending_requests_count = sum(1 for r in asset_requests if r.get('Status') in ('Pending', 'In Progress'))
        except Exception as e:
            print(f"Error loading asset requests: {e}")
            
        context['asset_requests'] = asset_requests
        context['pending_requests_count'] = pending_requests_count
        
        # Filter active employees for assignment dropdown (include Approved and seed/None status, exclude Resigned/Pending/Super Admin)
        from core.dynamodb_service import UsersTable
        try:
            all_users = UsersTable.scan()
            sa_emp_ids = {u.get('EmployeeID') for u in all_users if u.get('Role') == 'Super admin'}
        except Exception:
            sa_emp_ids = set()

        context['active_employees'] = [
            e for e in all_employees
            if e.get('OnboardingStatus') not in ('Resigned', 'Pending Review', 'Rejected', 'Pending')
            and e.get('EmployeeID') not in sa_emp_ids
        ]
        return context

class AddAssetView(HRRequiredMixin, View):
    def post(self, request):
        from core.dynamodb_service import AssetsTable
        import uuid
        
        asset_name = request.POST.get('asset_name', '').strip()
        serial_no = request.POST.get('serial_no', '').strip()
        category = request.POST.get('category', '').strip()
        condition = request.POST.get('condition', 'Excellent').strip()
        
        if not asset_name or not serial_no or not category:
            messages.error(request, "Asset Name, Serial Number, and Category are required.")
            return redirect('asset_management')
            
        asset_id = f"AST-{category[:3].upper()}-{str(uuid.uuid4())[:8].upper()}"
        
        asset_item = {
            'AssetID': asset_id,
            'AssetName': asset_name,
            'SerialNo': serial_no,
            'Category': category,
            'Status': 'Available',
            'Condition': condition
        }
        
        try:
            AssetsTable.put_item(asset_item)
            messages.success(request, f"Asset '{asset_name}' ({serial_no}) registered successfully.")
        except Exception as e:
            messages.error(request, f"Error registering asset: {e}")
            
        return redirect('asset_management')

class AllocateAssetView(HRRequiredMixin, View):
    def post(self, request, asset_id):
        from core.dynamodb_service import AssetsTable, EmployeesTable
        from core.utils import get_local_date
        
        employee_id = request.POST.get('employee_id', '').strip()
        if not employee_id:
            messages.error(request, "Employee selection is required for allocation.")
            return redirect('asset_management')
            
        asset = AssetsTable.get_item({'AssetID': asset_id})
        if not asset:
            messages.error(request, "Asset not found.")
            return redirect('asset_management')
            
        employee = EmployeesTable.get_item({'EmployeeID': employee_id})
        if not employee:
            messages.error(request, "Employee not found.")
            return redirect('asset_management')
            
        try:
            alloc_date = get_local_date().strftime('%Y-%m-%d')
            asset['Status'] = 'Assigned'
            asset['AssignedTo'] = employee_id
            asset['AllocationDate'] = alloc_date
            
            # Append allocation to history list
            history = asset.get('History', [])
            if not isinstance(history, list):
                history = []
            history.append({
                'Action': 'Allocated',
                'EmployeeID': employee_id,
                'EmployeeName': f"{employee.get('FirstName', '')} {employee.get('LastName', '')}",
                'Date': alloc_date,
                'Condition': asset.get('Condition', 'Excellent')
            })
            asset['History'] = history
            
            AssetsTable.put_item(asset)
            messages.success(request, f"Asset allocated to {employee.get('FirstName')} successfully.")
        except Exception as e:
            messages.error(request, f"Error allocating asset: {e}")
            
        return redirect('asset_management')

class ReturnAssetView(HRRequiredMixin, View):
    def post(self, request, asset_id):
        from core.dynamodb_service import AssetsTable
        
        asset = AssetsTable.get_item({'AssetID': asset_id})
        if not asset:
            messages.error(request, "Asset not found.")
            return redirect('asset_management')
            
        try:
            condition = request.POST.get('condition')
            if condition in ('Excellent', 'Good', 'Fair', 'Needs Repair'):
                asset['Condition'] = condition
            else:
                condition = asset.get('Condition', 'Excellent')
                
            assigned_to = asset.get('AssignedTo', 'Unknown')
            assignee_name = 'Unknown'
            if assigned_to and assigned_to != 'Unknown':
                from core.dynamodb_service import EmployeesTable
                emp = EmployeesTable.get_item({'EmployeeID': assigned_to})
                if emp:
                    assignee_name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}"
            
            from core.utils import get_local_date
            ret_date = get_local_date().strftime('%Y-%m-%d')
            
            # Append return to history list
            history = asset.get('History', [])
            if not isinstance(history, list):
                history = []
            history.append({
                'Action': 'Returned',
                'EmployeeID': assigned_to,
                'EmployeeName': assignee_name,
                'Date': ret_date,
                'Condition': condition
            })
            asset['History'] = history
            
            asset['Status'] = 'Available'
            asset.pop('AssignedTo', None)
            asset.pop('AllocationDate', None)
            AssetsTable.put_item(asset)
            messages.success(request, "Asset marked as returned and is now available.")
        except Exception as e:
            messages.error(request, f"Error returning asset: {e}")
            
        return redirect('asset_management')

class UpdateAssetConditionView(HRRequiredMixin, View):
    def post(self, request, asset_id):
        from core.dynamodb_service import AssetsTable
        asset = AssetsTable.get_item({'AssetID': asset_id})
        if not asset:
            messages.error(request, "Asset not found.")
            return redirect('asset_management')
        
        condition = request.POST.get('condition')
        if condition in ('Excellent', 'Good', 'Fair', 'Needs Repair'):
            try:
                asset['Condition'] = condition
                AssetsTable.put_item(asset)
                messages.success(request, f"Asset condition updated to {condition} successfully.")
            except Exception as e:
                messages.error(request, f"Error updating condition: {e}")
        return redirect('asset_management')

class DeleteAssetView(HRRequiredMixin, View):
    def post(self, request, asset_id):
        from core.dynamodb_service import AssetsTable
        asset = AssetsTable.get_item({'AssetID': asset_id})
        if not asset:
            messages.error(request, "Asset not found.")
            return redirect('asset_management')
            
        if asset.get('Status') == 'Assigned':
            messages.error(request, "Cannot delete an asset that is currently assigned to an employee.")
            return redirect('asset_management')
            
        try:
            AssetsTable.delete_item({'AssetID': asset_id})
            messages.success(request, f"Asset '{asset.get('AssetName')}' deleted successfully.")
        except Exception as e:
            messages.error(request, f"Error deleting asset: {e}")
        return redirect('asset_management')

class MyAssetsView(LoginRequiredMixin, TemplateView):
    template_name = 'employees/my_assets.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from core.dynamodb_service import AssetsTable, AssetRequestsTable
        
        user_emp_id = self.request.user.employee_id
        
        # Scan for assets assigned to this user
        my_assets = []
        try:
            all_assets = AssetsTable.scan()
            my_assets = [a for a in all_assets if a.get('AssignedTo') == user_emp_id]
        except Exception as e:
            print(f"Error loading employee assets: {e}")
            
        # Scan for requests raised by this user
        my_requests = []
        try:
            all_requests = AssetRequestsTable.scan()
            my_requests = [r for r in all_requests if r.get('EmployeeID') == user_emp_id]
            my_requests.sort(key=lambda x: x.get('CreatedAt', ''), reverse=True)
        except Exception as e:
            print(f"Error loading employee requests: {e}")
            
        context['assets'] = my_assets
        context['my_requests'] = my_requests
        context['laptop_count'] = sum(1 for a in my_assets if a.get('Category') in ('Laptop', 'Mobile'))
        return context

class RaiseAssetRequestView(LoginRequiredMixin, View):
    def post(self, request):
        from core.dynamodb_service import AssetsTable, AssetRequestsTable, EmployeesTable
        from core.utils import get_local_date
        import uuid
        
        asset_id = request.POST.get('asset_id')
        request_type = request.POST.get('request_type') # 'Complaint' or 'Exchange'
        issue_category = request.POST.get('issue_category')
        description = request.POST.get('description', '').strip()
        
        if not asset_id or not request_type or not description:
            messages.error(request, "Missing required request parameters.")
            return redirect('my_assets')
            
        # Fetch asset to verify ownership
        asset = AssetsTable.get_item({'AssetID': asset_id})
        if not asset or asset.get('AssignedTo') != request.user.employee_id:
            messages.error(request, "Asset is not assigned to you or does not exist.")
            return redirect('my_assets')
            
        # Fetch employee details for recording
        emp_name = "Unknown"
        emp = EmployeesTable.get_item({'EmployeeID': request.user.employee_id})
        if emp:
            emp_name = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}"
            
        try:
            request_id = f"REQ-AST-{str(uuid.uuid4())[:8].upper()}"
            request_item = {
                'RequestID': request_id,
                'AssetID': asset_id,
                'AssetName': asset.get('AssetName', 'Unknown Asset'),
                'EmployeeID': request.user.employee_id,
                'EmployeeName': emp_name,
                'RequestType': request_type,
                'IssueCategory': issue_category,
                'IssueDescription': description,
                'Status': 'Pending',
                'CreatedAt': get_local_date().strftime('%Y-%m-%d'),
                'ResolutionNotes': ''
            }
            AssetRequestsTable.put_item(request_item)
            messages.success(request, f"Your {request_type.lower()} request has been submitted successfully.")
        except Exception as e:
            messages.error(request, f"Error raising request: {e}")
            
        return redirect('my_assets')

class HandleAssetRequestView(HRRequiredMixin, View):
    def post(self, request, request_id):
        from core.dynamodb_service import AssetRequestsTable, AssetsTable
        
        status = request.POST.get('status')
        resolution_notes = request.POST.get('resolution_notes', '').strip()
        
        if not status or not resolution_notes:
            messages.error(request, "Status and resolution notes are required.")
            return redirect('asset_management')
            
        # Get request
        employee_id = request.POST.get('employee_id')
        asset_req = None
        if employee_id:
            try:
                asset_req = AssetRequestsTable.get_item({'EmployeeID': employee_id, 'RequestID': request_id})
            except Exception:
                asset_req = None
        
        # Fallback to scanning if not found or employee_id was missing
        if not asset_req:
            try:
                all_reqs = AssetRequestsTable.scan()
                asset_req = next((r for r in all_reqs if r.get('RequestID') == request_id), None)
            except Exception as e:
                messages.error(request, f"Error scanning database: {e}")
                return redirect('asset_management')
                
        if not asset_req:
            messages.error(request, "Request not found.")
            return redirect('asset_management')
            
        try:
            asset_req['Status'] = status
            asset_req['ResolutionNotes'] = resolution_notes
            AssetRequestsTable.put_item(asset_req)
            
            # If request is Resolved/Approved AND it is an Exchange request
            if status == 'Resolved' and asset_req.get('RequestType') == 'Exchange':
                asset_id = asset_req.get('AssetID')
                asset = AssetsTable.get_item({'AssetID': asset_id})
                if asset and asset.get('Status') == 'Assigned':
                    # Unassign asset and make it Available with Needs Repair condition
                    from core.utils import get_local_date
                    ret_date = get_local_date().strftime('%Y-%m-%d')
                    
                    assigned_to = asset.get('AssignedTo', 'Unknown')
                    employee_name = asset_req.get('EmployeeName', 'Unknown')
                    
                    # Record return in history
                    history = asset.get('History', [])
                    if not isinstance(history, list):
                        history = []
                    history.append({
                        'Action': 'Returned (Exchange Approved)',
                        'EmployeeID': assigned_to,
                        'EmployeeName': employee_name,
                        'Date': ret_date,
                        'Condition': 'Needs Repair'
                    })
                    
                    asset['History'] = history
                    asset['Condition'] = 'Needs Repair'
                    asset['Status'] = 'Available'
                    asset.pop('AssignedTo', None)
                    asset.pop('AllocationDate', None)
                    AssetsTable.put_item(asset)
                    messages.success(request, f"Request resolved. Asset {asset_id} has been automatically unassigned and marked for repair/exchange.")
                else:
                    messages.success(request, "Request resolved successfully.")
            else:
                messages.success(request, f"Request status updated to {status} successfully.")
        except Exception as e:
            messages.error(request, f"Error processing request: {e}")
            
        return redirect('asset_management')



