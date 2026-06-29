from django.shortcuts import render, redirect, reverse
from django.core.paginator import Paginator
from django.contrib import messages
from django.views import View
from django.views.generic import TemplateView
from auth_custom.mixins import LoginRequiredMixin, ApprovedOnboardingMixin, ManagerRequiredMixin, HRRequiredMixin
from core.dynamodb_service import (
    UsersTable, EmployeesTable, LeaveRequestsTable, AttendanceTable, 
    PayslipsTable, ExpensesTable, ResignationsTable, 
    ReportingHierarchyTable, LoginHistoryTable, WFHRequestsTable
)
from core.utils import save_uploaded_file, send_notification, get_lurnexa_logo_base64, get_authorized_signature_stamp_base64
from boto3.dynamodb.conditions import Key
import datetime
import uuid
import json
from django.template.loader import render_to_string
import io
from xhtml2pdf import pisa

def link_callback(uri, rel):
    """
    Convert HTML images or stylesheets to absolute paths so xhtml2pdf can find them.
    """
    import os
    from django.conf import settings
    from django.contrib.staticfiles import finders

    # Clean up the URI by removing static/media prefixes to get the relative path
    if uri.startswith(settings.STATIC_URL):
        rel_path = uri[len(settings.STATIC_URL):]
    elif uri.startswith(settings.MEDIA_URL):
        rel_path = uri[len(settings.MEDIA_URL):]
    else:
        rel_path = uri

    # Try to find using Django staticfiles finders
    result = finders.find(rel_path)
    if result:
        if not isinstance(result, (list, tuple)):
            result = [result]
        s_file = result[0]
    else:
        s_media = os.path.join(settings.MEDIA_ROOT, rel_path)
        s_static = os.path.join(settings.STATIC_ROOT, rel_path)

        if os.path.exists(s_media):
            s_file = s_media
        elif os.path.exists(s_static):
            s_file = s_static
        else:
            return uri

    # Make sure that file actually exists
    if not os.path.isfile(s_file):
        return uri
    return s_file

def html_to_pdf_bytes(html_content):
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer, link_callback=link_callback)
    if not pisa_status.err:
        return pdf_buffer.getvalue()
    return None

def save_employee_letter_if_not_exists(emp_id, letter_type, html_content):
    try:
        from core.dynamodb_service import EmployeeLettersTable
        from boto3.dynamodb.conditions import Key
        import uuid
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        existing_letters = EmployeeLettersTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(emp_id)
        )
        existing = next((l for l in existing_letters if l.get('LetterType') == letter_type), None)
        if not existing:
            letter_id = str(uuid.uuid4())
            file_path = f"letters/{letter_id}.html"
            default_storage.save(file_path, ContentFile(html_content.encode('utf-8')))
            
            letter_item = {
                'EmployeeID': emp_id,
                'LetterID': letter_id,
                'LetterType': letter_type,
                'GeneratedDate': datetime.datetime.now().isoformat(),
                'FilePath': file_path
            }
            EmployeeLettersTable.put_item(letter_item)
            print(f"SUCCESS: Saved {letter_type} to EmployeeLettersTable for {emp_id}")
    except Exception as e:
        print(f"Error saving employee letter to table: {e}")

class ExpensesView(LoginRequiredMixin, ApprovedOnboardingMixin, View):
    def get(self, request):
        records = ExpensesTable.query(KeyConditionExpression=Key('EmployeeID').eq(request.user.employee_id))
        sorted_records = sorted(records, key=lambda x: x.get('Date', ''), reverse=True)
        
        paginator = Paginator(sorted_records, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        return render(request, 'workflows/expenses.html', {
            'records': page_obj,
            'total_count': len(sorted_records)
        })

    def post(self, request):
        amount = request.POST.get('amount')
        category = request.POST.get('category')
        description = request.POST.get('description')
        receipt = request.FILES.get('receipt')
        req_id = str(uuid.uuid4())
        
        user_emp_id = request.user.employee_id
        
        # Determine Hierarchy
        hierarchy = ReportingHierarchyTable.scan(
            FilterExpression="EmployeeID = :eid",
            ExpressionAttributeValues={":eid": user_emp_id}
        )
        
        manager_id = None
        if hierarchy:
            manager_id = hierarchy[0].get('ManagerID')
        
        # Determine the initial status and approver based on roles
        user_role = request.user.role
        manager_role = None
        if manager_id:
            # Check manager's role in UsersTable
            mgr_users = UsersTable.scan(
                FilterExpression="EmployeeID = :eid",
                ExpressionAttributeValues={":eid": manager_id}
            )
            if mgr_users:
                manager_role = mgr_users[0].get('Role')

        if user_role == 'Super admin':
            status = 'Approved' # Self-approved
            approver_id = user_emp_id
        elif user_role == 'HR ADMIN':
            status = 'Pending Manager Approval' # Super admin is the manager
            approver_id = manager_id
            if not approver_id:
                sa_users = [u for u in UsersTable.scan() if u.get('Role') == 'Super admin']
                if sa_users: approver_id = sa_users[0].get('EmployeeID')
        elif user_role == 'Manager':
            status = 'Pending HR ADMIN Approval'
            approver_id = manager_id
            if not approver_id:
                hr_users = [u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN']
                if hr_users: approver_id = hr_users[0].get('EmployeeID')
        else: # Employee
            if manager_role == 'HR ADMIN':
                status = 'Pending HR ADMIN Approval'
                approver_id = manager_id
            elif manager_id:
                status = 'Pending Manager Approval'
                approver_id = manager_id
            else:
                status = 'Pending HR ADMIN Approval'
                hr_users = [u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN']
                if hr_users: approver_id = hr_users[0].get('EmployeeID')

        receipt_name = None
        if receipt:
            receipt_name = save_uploaded_file(receipt, 'receipts')

        item = {
            'EmployeeID': user_emp_id,
            'RequestID': req_id,
            'Amount': amount,
            'Category': category,
            'Description': description,
            'Status': status,
            'Date': datetime.date.today().isoformat(),
            'ReceiptImage': receipt_name,
            'ApproverID': approver_id,
            'ManagerID': manager_id
        }
        ExpensesTable.put_item(item)
        
        # --- Send Notification to Approver ---
        if approver_id:
            emp_name = f"{request.user.first_name} {request.user.last_name}"
            send_notification(
                employee_id=approver_id,
                title="New Expense Claim",
                message=f"{emp_name} has submitted an expense claim of ₹{amount} for {category}.",
                n_type='Expense',
                icon='fa-file-invoice-dollar',
                color='info',
                email_subject=f"Expense Claim: {emp_name}",
                email_body=f"Hi,\n\n{emp_name} has submitted a new expense claim.\nCategory: {category}\nAmount: ₹{amount}\nDescription: {description}\n\nPlease log in to the Lurnexa portal to review and take action.\n\nBest regards,\nLurnexa HR Admin"
            )

        messages.success(request, f"Expense claim submitted. Current Status: {status}")
        return redirect('expenses_view')



class ResignationView(LoginRequiredMixin, ApprovedOnboardingMixin, View):
    def get(self, request):
        record = ResignationsTable.get_item({'EmployeeID': request.user.employee_id})
        
        # Default LWD is 60 days from today (standard notice period)
        min_lwd_date = datetime.date.today() + datetime.timedelta(days=60)
        min_lwd = min_lwd_date.isoformat()
        
        return render(request, 'workflows/resignation.html', {
            'record': record,
            'min_lwd': min_lwd,
            'is_hr': request.user.role == 'HR ADMIN'
        })

    def post(self, request):
        emp_id = getattr(request.user, 'employee_id', None)
        if not emp_id:
            messages.error(request, "Employee ID not found. Please contact HR.")
            return redirect('resignation_view')

        reason = request.POST.get('reason')
        lwd = request.POST.get('lwd')
        comments = request.POST.get('comments')
        
        if not reason or not lwd:
            messages.error(request, "Reason and Last Working Day are required.")
            return redirect('resignation_view')

        # --- TENURE CHECK (Default 60 Days) ---
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if employee and employee.get('JoinedDate'):
            try:
                joined_date = datetime.datetime.strptime(employee.get('JoinedDate'), '%Y-%m-%d').date()
                tenure_days = (datetime.date.today() - joined_date).days
                if tenure_days < 60:
                    wait_days = 60 - tenure_days
                    messages.error(request, f"Resignation can be applied after 60 days of service only. You can apply in {wait_days} day{'s' if wait_days > 1 else ''}.")
                    return redirect('resignation_view')
            except Exception:
                pass

        # --- REJECTION COOLING OFF PERIOD CHECK (3 Days) ---
        existing_record = ResignationsTable.get_item({'EmployeeID': emp_id})
        if existing_record and existing_record.get('Status') == 'Rejected':
            rejected_on_str = existing_record.get('RejectedOn')
            if rejected_on_str:
                try:
                    rejected_on = datetime.datetime.fromisoformat(rejected_on_str).date()
                    days_since_rejection = (datetime.date.today() - rejected_on).days
                    if days_since_rejection < 3:
                        wait_days = 3 - days_since_rejection
                        messages.error(request, f"Your previous resignation was rejected. You can apply again in {wait_days} day{'s' if wait_days > 1 else ''}.")
                        return redirect('resignation_view')
                except Exception:
                    pass

        try:
            # Determine Approver
            hierarchy = ReportingHierarchyTable.scan(
                FilterExpression="EmployeeID = :eid",
                ExpressionAttributeValues={":eid": emp_id}
            )
            approver_id = None
            if hierarchy:
                approver_id = hierarchy[0].get('ManagerID')
            else:
                hr_users = [u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN']
                if hr_users: approver_id = hr_users[0].get('EmployeeID')

            item = {
                'EmployeeID': emp_id,
                'Reason': reason,
                'LastWorkingDay': lwd,
                'Comments': comments,
                'Status': 'Pending HR ADMIN Review',
                'SubmittedOn': datetime.date.today().isoformat(),
                'ApproverID': approver_id
            }
            ResignationsTable.put_item(item)
            
            # --- Send Notification to HR/Approver ---
            if approver_id:
                emp_name = f"{request.user.first_name} {request.user.last_name}"
                send_notification(
                    employee_id=approver_id,
                    title="New Resignation Request",
                    message=f"{emp_name} has submitted a resignation request for LWD: {lwd}.",
                    n_type='Resignation',
                    icon='fa-user-minus',
                    color='warning',
                    email_subject=f"Resignation Request: {emp_name}",
                    email_body=f"Hi,\n\n{emp_name} has submitted a new resignation request.\nReason: {reason}\nProposed Last Working Day: {lwd}\nComments: {comments}\n\nPlease log in to the Lurnexa portal to review and take action.\n\nBest regards,\nLurnexa HR Admin"
                )

            messages.success(request, f"Your resignation has been submitted successfully for LWD: {lwd}")
        except Exception as e:
            messages.error(request, f"Database Error: {str(e)}")
            
        return redirect('resignation_view')

class ExpenseApprovalsView(ManagerRequiredMixin, TemplateView):
    template_name = 'workflows/expense_approvals.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_emp_id = self.request.user.employee_id
        user_role = self.request.user.role
        
        all_expenses = ExpensesTable.scan()
        all_employees = EmployeesTable.scan()
        emp_obj_map = {e['EmployeeID']: e for e in all_employees}
        
        # Filter Params
        q = self.request.GET.get('q', '').strip().lower()
        dept = self.request.GET.get('dept', '')
        date_range = self.request.GET.get('range', 'all')
        sort_order = self.request.GET.get('sort', 'desc')
        today = datetime.date.today()
        
        pending = []
        processed = []
        
        for exp in all_expenses:
            status = exp.get('Status')
            emp = emp_obj_map.get(exp['EmployeeID'], {})
            exp['EmployeeName'] = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}"
            exp['Department'] = emp.get('Department', '')

            # --- Apply Filters ---
            if q and q not in exp['EmployeeName'].lower() and q not in exp['EmployeeID'].lower():
                continue
            if dept and exp['Department'] != dept:
                continue
            
            exp_date_str = exp.get('Date', '')
            if date_range != 'all' and exp_date_str:
                try:
                    exp_date = datetime.datetime.strptime(exp_date_str, '%Y-%m-%d').date()
                    if date_range == 'month' and exp_date.strftime('%Y-%m') != today.strftime('%Y-%m'):
                        continue
                    elif date_range == '3months' and (today - exp_date).days > 90:
                        continue
                    elif date_range == 'year' and exp_date.year != today.year:
                        continue
                except: pass

            if user_role == 'Super admin':
                if exp.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                    pending.append(exp)
                elif status in ['Approved', 'Rejected']:
                    processed.append(exp)
            elif user_role == 'HR ADMIN':
                if status == 'Manager Approved' or status == 'Pending HR ADMIN Approval':
                    pending.append(exp)
                elif exp.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                    pending.append(exp)
                elif status in ['Approved', 'Rejected']:
                    processed.append(exp)
            else: # Manager
                if exp.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                    pending.append(exp)
                elif exp.get('ApproverID') == user_emp_id and status != 'Pending Manager Approval':
                    processed.append(exp)

        context['departments'] = sorted(list(set(e.get('Department') for e in all_employees if e.get('Department'))))

        # Sort
        pending.sort(key=lambda x: x.get('Date', ''), reverse=(sort_order == 'desc'))
        processed.sort(key=lambda x: x.get('Date', ''), reverse=(sort_order == 'desc'))

        # Paginate Pending
        paginator_p = Paginator(pending, 10)
        page_p = self.request.GET.get('page_p')
        context['pending_expenses'] = paginator_p.get_page(page_p)
        context['pending_count'] = len(pending)
        
        # Mapping Processor Names
        for exp in processed:
             pb_id = exp.get('ProcessedBy') or exp.get('ApprovedByHR') or exp.get('ApprovedByManager') or exp.get('RejectedBy')
             if pb_id:
                 pb_emp = emp_obj_map.get(pb_id)
                 if pb_emp:
                     name = f"{pb_emp.get('FirstName', '')} {pb_emp.get('LastName', '')}".strip()
                     exp['ProcessorName'] = name if name else pb_id
                 else:
                     exp['ProcessorName'] = pb_id
             else:
                 exp['ProcessorName'] = "System"

        # Paginate Processed
        paginator_h = Paginator(processed, 10)
        page_h = self.request.GET.get('page_h')
        context['processed_expenses'] = paginator_h.get_page(page_h)
        context['processed_count'] = len(processed)
        context['active_tab'] = self.request.GET.get('tab', 'pending')
        return context

class ApproveExpenseView(ManagerRequiredMixin, View):
    def get(self, request, emp_id, req_id):
        user_role = request.user.role
        expense = ExpensesTable.get_item({'EmployeeID': emp_id, 'RequestID': req_id})
        
        if not expense:
            messages.error(request, "Expense record not found.")
            return redirect('expense_approvals')

        new_status = 'Approved'
        msg = "Expense claim fully approved."
        # Check applicant's role
        applicant_users = UsersTable.scan(
            FilterExpression="EmployeeID = :eid",
            ExpressionAttributeValues={":eid": emp_id}
        )
        applicant_role = applicant_users[0].get('Role') if applicant_users else 'Employee'
        
        if user_role in ['HR ADMIN', 'Super admin']:
            new_status = 'Approved'
            est_date = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
            update_expr = "SET #s = :s, ApprovedByHR = :u, HRApprovalDate = :d, PaymentStatus = :ps, EstimatedTransferDate = :etd, ProcessedBy = :pb"
            expr_vals = {
                ':s': new_status,
                ':u': request.user.employee_id,
                ':d': datetime.date.today().isoformat(),
                ':ps': 'Scheduled',
                ':etd': est_date,
                ':pb': request.user.employee_id
            }
        else:
            # Manager Approval
            if applicant_role == 'HR ADMIN':
                new_status = 'Approved'
                msg = "Expense claim fully approved. (Manager approval is final for HR)"
                est_date = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
                update_expr = "SET #s = :s, ApprovedByManager = :u, ManagerApprovalDate = :d, PaymentStatus = :ps, EstimatedTransferDate = :etd, ProcessedBy = :pb"
                expr_vals = {
                    ':s': new_status,
                    ':u': request.user.employee_id,
                    ':d': datetime.date.today().isoformat(),
                    ':ps': 'Scheduled',
                    ':etd': est_date,
                    ':pb': request.user.employee_id
                }
            else:
                new_status = 'Manager Approved'
                msg = "Expense claim approved by you. Sent to HR for final approval."
                update_expr = "SET #s = :s, ApprovedByManager = :u, ManagerApprovalDate = :d, ProcessedBy = :pb"
                expr_vals = {
                    ':s': new_status,
                    ':u': request.user.employee_id,
                    ':d': datetime.date.today().isoformat(),
                    ':pb': request.user.employee_id
                }

        ExpensesTable.update_item(
            Key={'EmployeeID': emp_id, 'RequestID': req_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={'#s': 'Status'},
            ExpressionAttributeValues=expr_vals
        )
        
        # --- Send Notification to Employee ---
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        emp_name = f"{employee.get('FirstName')} {employee.get('LastName')}" if employee else emp_id
        
        if user_role in ['HR ADMIN', 'Super admin']:
            notif_title = "Expense Fully Approved"
            notif_msg = f"Your expense claim of ₹{expense.get('Amount')} has been fully approved by HR."
            email_subj = "Expense Claim Fully Approved"
            email_body = f"Hi {emp_name},\n\nYour expense claim of ₹{expense.get('Amount')} has been fully approved by HR and will be processed soon.\n\nBest regards,\nLurnexa HR Admin"
        else:
            if applicant_role == 'HR ADMIN':
                notif_title = "Expense Fully Approved"
                notif_msg = f"Your expense claim of ₹{expense.get('Amount')} has been fully approved by your manager."
                email_subj = "Expense Claim Fully Approved"
                email_body = f"Hi {emp_name},\n\nYour expense claim of ₹{expense.get('Amount')} has been fully approved by your manager and will be processed soon.\n\nBest regards,\nLurnexa HR Admin"
            else:
                notif_title = "Expense Manager Approved"
                notif_msg = f"Your expense claim of ₹{expense.get('Amount')} was approved by your manager and sent to HR."
                email_subj = "Expense Claim Manager Approval"
                email_body = f"Hi {emp_name},\n\nYour expense claim of ₹{expense.get('Amount')} has been approved by your manager and is now pending final HR approval.\n\nBest regards,\nLurnexa HR Admin"
            
        send_notification(
            employee_id=emp_id,
            title=notif_title,
            message=notif_msg,
            n_type='Expense',
            icon='fa-check-double' if user_role in ['HR ADMIN', 'Super admin'] else 'fa-user-check',
            color='success' if user_role in ['HR ADMIN', 'Super admin'] else 'primary',
            email_subject=email_subj,
            email_body=email_body
        )

        messages.success(request, msg)
        return redirect('expense_approvals')

class RejectExpenseView(ManagerRequiredMixin, View):
    def get(self, request, emp_id, req_id):
        ExpensesTable.update_item(
            Key={'EmployeeID': emp_id, 'RequestID': req_id},
            UpdateExpression="SET #s = :val, RejectedBy = :u, RejectionDate = :d, ProcessedBy = :pb",
            ExpressionAttributeNames={'#s': 'Status'},
            ExpressionAttributeValues={
                ':val': 'Rejected',
                ':u': request.user.employee_id,
                ':d': datetime.date.today().isoformat(),
                ':pb': request.user.employee_id
            }
        )
        
        # --- Send Notification to Employee ---
        expense = ExpensesTable.get_item({'EmployeeID': emp_id, 'RequestID': req_id})
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        emp_name = f"{employee.get('FirstName')} {employee.get('LastName')}" if employee else emp_id
        
        send_notification(
            employee_id=emp_id,
            title="Expense Claim Rejected",
            message=f"Your expense claim of ₹{expense.get('Amount') if expense else ''} has been rejected.",
            n_type='Expense',
            icon='fa-file-circle-xmark',
            color='danger',
            email_subject="Expense Claim Rejected",
            email_body=f"Hi {emp_name},\n\nYour expense claim for ₹{expense.get('Amount') if expense else ''} has been REJECTED.\n\nPlease contact your manager or HR for more details.\n\nBest regards,\nLurnexa HR Admin"
        )

        messages.error(request, "Expense request rejected.")
        return redirect('expense_approvals')

class ProcessPaymentView(HRRequiredMixin, View):
    def get(self, request, emp_id, req_id):
        ExpensesTable.update_item(
            Key={'EmployeeID': emp_id, 'RequestID': req_id},
            UpdateExpression="SET PaymentStatus = :p, PaymentDate = :d, ProcessedBy = :pb",
            ExpressionAttributeValues={
                ':p': 'Paid',
                ':d': datetime.date.today().isoformat(),
                ':pb': request.user.employee_id
            }
        )
        
        # Notify Employee
        expense = ExpensesTable.get_item({'EmployeeID': emp_id, 'RequestID': req_id})
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        emp_name = f"{employee.get('FirstName')} {employee.get('LastName')}" if employee else emp_id

        send_notification(
            employee_id=emp_id,
            title="Expense Reimbursed",
            message=f"Amount of ₹{expense.get('Amount')} has been transferred to your bank account.",
            n_type='Expense',
            icon='fa-building-columns',
            color='success',
            email_subject="Expense Reimbursement Processed",
            email_body=f"Hi {emp_name},\n\nGood news! Your expense reimbursement for ₹{expense.get('Amount')} has been processed and the funds have been transferred to your bank account.\n\nBest regards,\nLurnexa HR Admin"
        )
        
        messages.success(request, "Payment processed and employee notified.")
        return redirect(f"{reverse('expense_approvals')}?tab=history")

class ResignationApprovalsView(HRRequiredMixin, TemplateView):
    template_name = 'workflows/resignation_approvals.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_resignations = ResignationsTable.scan()
        all_employees = EmployeesTable.scan()
        emp_map = {e['EmployeeID']: e for e in all_employees}
        today = datetime.date.today()
        
        # Get Filter Params
        query = self.request.GET.get('q', '').strip().lower()
        dept_filter = self.request.GET.get('dept', '')
        range_filter = self.request.GET.get('range', 'all')
        sort_order = self.request.GET.get('sort', 'desc')
        active_tab = self.request.GET.get('tab', 'pending')

        # Calculate unique departments for filter dropdown
        context['departments'] = sorted(list(set(e.get('Department') for e in all_employees if e.get('Department'))))
        context['active_tab'] = active_tab

        pending = []
        history = []
        
        all_users = UsersTable.scan()
        user_role_map = {u.get('EmployeeID'): u.get('Role') for u in all_users if u.get('EmployeeID')}
        user_role = self.request.user.role

        for r in all_resignations:
            emp_id = r.get('EmployeeID')
            resigner_role = user_role_map.get(emp_id)
            employee_data = emp_map.get(emp_id, {})
            
            status = r.get('Status')
            
            # Hierarchy Logic:
            # 1. Super admin only sees HR ADMIN resignations in Pending, but sees EVERYTHING in History
            if user_role == 'Super admin':
                if status == 'Pending HR ADMIN Review' and resigner_role != 'HR ADMIN':
                    continue
            
            # 2. HR ADMIN sees Employees and Managers, but NOT other HR ADMINs (managed by SA)
            elif user_role == 'HR ADMIN':
                if resigner_role in ['HR ADMIN', 'Super admin']:
                    continue

            # --- Applied Filters ---
            emp_name = f"{employee_data.get('FirstName', '')} {employee_data.get('LastName', '')}".lower()
            emp_dept = employee_data.get('Department', '')
            submitted_on_str = r.get('SubmittedOn', '')

            # 1. Search Filter
            if query and query not in emp_name and query not in emp_id.lower():
                continue
            
            # 2. Department Filter
            if dept_filter and emp_dept != dept_filter:
                continue
            
            # 3. Date Range Filter
            if range_filter != 'all':
                if not submitted_on_str:
                    continue
                try:
                    sub_date = datetime.date.fromisoformat(submitted_on_str)
                    if range_filter == 'month' and (today - sub_date).days > 30:
                        continue
                    if range_filter == '3months' and (today - sub_date).days > 90:
                        continue
                    if range_filter == 'year' and sub_date.year != today.year:
                        continue
                except Exception:
                    continue

            r['EmployeeName'] = f"{employee_data.get('FirstName', '')} {employee_data.get('LastName', '')}" if employee_data else emp_id
            r['PhoneNumber'] = employee_data.get('Phone', 'N/A')
            r['is_pf_applicable'] = employee_data.get('is_pf_applicable', False)
            lwd_str = r.get('LastWorkingDay')
            status = r.get('Status')
            
            if status == 'Pending HR ADMIN Review':
                pending.append(r)
            
            # Check for inactivation logic
            if status == 'Accepted Resignation' and lwd_str:
                try:
                    lwd = datetime.datetime.strptime(lwd_str, '%Y-%m-%d').date()
                    if today > lwd:
                        emp = next((e for e in all_employees if e.get('EmployeeID') == emp_id), None)
                        if emp and emp.get('IsActive', True):
                            EmployeesTable.update_item(
                                Key={'EmployeeID': emp_id},
                                UpdateExpression="SET IsActive = :val",
                                ExpressionAttributeValues={":val": False}
                            )
                            user_id = emp.get('UserID')
                            if user_id:
                                UsersTable.update_item(
                                    Key={'UserID': user_id},
                                    UpdateExpression="SET IsActive = :val",
                                    ExpressionAttributeValues={":val": False}
                                )
                        r['IsInactive'] = True
                        
                    if today >= (lwd + datetime.timedelta(days=7)):
                        r['CanDelete'] = True
                except Exception:
                    pass
            
            if status != 'Pending HR ADMIN Review':
                history.append(r)
        
        # Sort
        pending.sort(key=lambda x: x.get('SubmittedOn', ''), reverse=(sort_order == 'desc'))
        history.sort(key=lambda x: x.get('SubmittedOn', ''), reverse=(sort_order == 'desc'))
                
        paginator_p = Paginator(pending, 10)
        context['pending_resignations'] = paginator_p.get_page(self.request.GET.get('page_p'))
        context['pending_count'] = len(pending)
        
        # Mapping Processor Names
        for r in history:
             pb_id = r.get('ProcessedBy') or r.get('ApprovedBy') or r.get('RejectedBy')
             if pb_id:
                 pb_emp = emp_map.get(pb_id)
                 if pb_emp:
                     name = f"{pb_emp.get('FirstName', '')} {pb_emp.get('LastName', '')}".strip()
                     r['ProcessorName'] = name if name else pb_id
                 else:
                     r['ProcessorName'] = pb_id
             else:
                 r['ProcessorName'] = "System"

        paginator_h = Paginator(history, 10)
        context['processed_resignations'] = paginator_h.get_page(self.request.GET.get('page_h'))
        context['processed_count'] = len(history)
        
        return context

class ProcessResignationView(HRRequiredMixin, View):
    def get(self, request, emp_id, action):
        status = 'Accepted Resignation' if action == 'approve' else 'Rejected'
        update_expr = "SET #s = :val, ProcessedBy = :pb"
        expr_vals = {':val': status, ':pb': request.user.employee_id}
        
        if status == 'Rejected':
            update_expr += ", RejectedOn = :d"
            expr_vals[':d'] = datetime.datetime.now().isoformat()

        ResignationsTable.update_item(
            Key={'EmployeeID': emp_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={'#s': 'Status'},
            ExpressionAttributeValues=expr_vals
        )

        # --- Send Notification to Employee ---
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        emp_full_name = f"{employee.get('FirstName', '')} {employee.get('LastName', '')}" if employee else emp_id
        
        res_record = ResignationsTable.get_item({'EmployeeID': emp_id})
        lwd = res_record.get('LastWorkingDay') if res_record else None
        lwd_fmt = lwd
        if lwd:
            try:
                lwd_fmt = datetime.datetime.strptime(lwd, '%Y-%m-%d').strftime('%B %d, %Y')
            except Exception:
                pass

        attachments = []
        if status == 'Accepted Resignation':
            notif_title = "Resignation Accepted"
            notif_msg = f"Your resignation request has been accepted. Your Last Working Day is confirmed as {lwd_fmt}." if lwd_fmt else "Your resignation request has been accepted. Your Last Working Day is confirmed."
            email_subj = "Resignation Request Accepted"
            email_body = f"Hi {emp_full_name},\n\nYour resignation request has been accepted by HR. Your Last Working Day has been confirmed as {lwd_fmt}.\n\nPlease complete any pending offboarding tasks.\n\nBest regards,\nLurnexa HR Admin" if lwd_fmt else f"Hi {emp_full_name},\n\nYour resignation request has been accepted by HR. Your Last Working Day has been confirmed.\n\nPlease complete any pending offboarding tasks.\n\nBest regards,\nLurnexa HR Admin"
        else:
            notif_title = "Resignation Rejected"
            notif_msg = f"Your resignation request has been rejected. Please contact HR for details."
            email_subj = "Resignation Request Rejected"
            email_body = f"Hi {emp_full_name},\n\nYour resignation request has been rejected by HR. Please reach out to your HR representative or manager for further clarification.\n\nBest regards,\nLurnexa HR Admin"

        send_notification(
            employee_id=emp_id,
            title=notif_title,
            message=notif_msg,
            n_type='Resignation',
            icon='fa-check-circle' if status == 'Accepted Resignation' else 'fa-times-circle',
            color='success' if status == 'Accepted Resignation' else 'danger',
            email_subject=email_subj,
            email_body=email_body,
            attachments=attachments if attachments else None
        )
        
        if status == 'Accepted Resignation':
            res_record = ResignationsTable.get_item({'EmployeeID': emp_id})
            lwd = res_record.get('LastWorkingDay') if res_record else None
            
            # --- SYNC STATUS TO EMPLOYEES TABLE ---
            today = datetime.date.today()
            emp = EmployeesTable.get_item({'EmployeeID': emp_id})
            if emp:
                upd_expr = "SET OnboardingStatus = :s, LastWorkingDate = :lwd"
                vals = {':s': 'Accepted Resignation', ':lwd': lwd}
                
                is_past_lwd = False
                if lwd:
                    try:
                        lwd_date = datetime.datetime.strptime(lwd, '%Y-%m-%d').date()
                        if today > lwd_date:
                            is_past_lwd = True
                    except:
                        pass

                if is_past_lwd:
                    upd_expr += ", IsActive = :a"
                    vals[':a'] = False
                    user_id = emp.get('UserID')
                    if user_id:
                        UsersTable.update_item(Key={'UserID': user_id}, UpdateExpression="SET IsActive = :a", ExpressionAttributeValues={':a': False})
                
                EmployeesTable.update_item(Key={'EmployeeID': emp_id}, UpdateExpression=upd_expr, ExpressionAttributeValues=vals)

            messages.success(request, f"Resignation for {emp_id} has been accepted. Access will expire after {lwd}.")
        else:
            messages.error(request, f"Resignation for {emp_id} has been rejected.")
            
        return redirect('resignation_approvals')

class DeleteEmployeeView(HRRequiredMixin, View):
    def get(self, request, emp_id):
        emp = EmployeesTable.get_item({'EmployeeID': emp_id})
        if not emp:
            messages.error(request, "Employee not found.")
            return redirect('resignation_approvals')
            
        user_id = emp.get('UserID')
        if user_id: UsersTable.delete_item({'UserID': user_id})
        EmployeesTable.delete_item({'EmployeeID': emp_id})
        ResignationsTable.delete_item({'EmployeeID': emp_id})
        
        for table in [AttendanceTable, LeaveRequestsTable, PayslipsTable, ExpensesTable]:
            try:
                items = table.query(KeyConditionExpression=Key('EmployeeID').eq(emp_id))
                for item in items:
                    key = {'EmployeeID': emp_id}
                    if 'RecordDate' in item: key['RecordDate'] = item['RecordDate']
                    elif 'LeaveDate' in item: key['LeaveDate'] = item['LeaveDate']
                    elif 'MonthYear' in item: key['MonthYear'] = item['MonthYear']
                    elif 'RequestID' in item: key['RequestID'] = item['RequestID']
                    table.delete_item(key)
            except: pass

        messages.success(request, f"All data for employee {emp_id} has been permanently deleted.")
        return redirect('resignation_approvals')

class WFHApprovalsView(ManagerRequiredMixin, TemplateView):
    template_name = 'workflows/wfh_approvals.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_emp_id = self.request.user.employee_id
        user_role = self.request.user.role
        all_wfh = WFHRequestsTable.scan()
        all_employees = EmployeesTable.scan()
        emp_obj_map = {e['EmployeeID']: e for e in all_employees}
        
        # Filter Params
        q = self.request.GET.get('q', '').strip().lower()
        dept = self.request.GET.get('dept', '')
        date_range = self.request.GET.get('range', 'all')
        sort_order = self.request.GET.get('sort', 'desc')
        today = datetime.date.today()
        
        pending, history = [], []
        for w in all_wfh:
            emp = emp_obj_map.get(w['EmployeeID'], {})
            w['EmployeeName'] = f"{emp.get('FirstName', '')} {emp.get('LastName', '')}"
            w['Department'] = emp.get('Department', '')
            status = w.get('Status')
            
            # --- Apply Filters ---
            if q and q not in w['EmployeeName'].lower() and q not in w['EmployeeID'].lower():
                continue
            if dept and w['Department'] != dept:
                continue
            
            w_date_str = w.get('WFHDate', '')
            if date_range != 'all' and w_date_str:
                try:
                    w_date = datetime.datetime.strptime(w_date_str, '%Y-%m-%d').date()
                    if date_range == 'month' and w_date.strftime('%Y-%m') != today.strftime('%Y-%m'):
                        continue
                    elif date_range == '3months' and (today - w_date).days > 90:
                        continue
                    elif date_range == 'year' and w_date.year != today.year:
                        continue
                except: pass

            if user_role == 'Super admin':
                if w.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                    pending.append(w)
                elif status in ['Approved', 'Rejected']:
                    history.append(w)
            elif user_role == 'HR ADMIN':
                if status == 'Pending HR ADMIN Approval':
                    pending.append(w)
                elif w.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                    pending.append(w)
                elif status in ['Approved', 'Rejected']:
                    history.append(w)
            else: # Manager
                if w.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                    pending.append(w)
                elif w.get('ApproverID') == user_emp_id and status != 'Pending Manager Approval':
                    history.append(w)
        
        context['departments'] = sorted(list(set(e.get('Department') for e in all_employees if e.get('Department'))))

        # Sort
        pending.sort(key=lambda x: x.get('WFHDate', ''), reverse=(sort_order == 'desc'))
        history.sort(key=lambda x: x.get('WFHDate', ''), reverse=(sort_order == 'desc'))

        context['pending_wfh'] = Paginator(pending, 10).get_page(self.request.GET.get('page_p'))
        context['pending_count'] = len(pending)
        # Mapping Processor Names
        for w in history:
             pb_id = w.get('ProcessedBy') or w.get('ApprovedBy') or w.get('RejectedBy')
             if pb_id:
                 pb_emp = emp_obj_map.get(pb_id)
                 if pb_emp:
                     name = f"{pb_emp.get('FirstName', '')} {pb_emp.get('LastName', '')}".strip()
                     w['ProcessorName'] = name if name else pb_id
                 else:
                     w['ProcessorName'] = pb_id
             else:
                 w['ProcessorName'] = "System"

        context['history_wfh'] = Paginator(history, 10).get_page(self.request.GET.get('page_h'))
        context['history_count'] = len(history)
        context['active_tab'] = self.request.GET.get('tab', 'pending')
        return context

class ApproveWFHView(ManagerRequiredMixin, View):
    def get(self, request, emp_id, req_id):
        user_role = request.user.role
        wfh = WFHRequestsTable.get_item({'EmployeeID': emp_id, 'RequestID': req_id})
        if not wfh: return redirect('wfh_approvals')
        
        new_status = 'Approved'
        msg = "WFH request fully approved."
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        if user_role not in ['HR ADMIN', 'Super admin'] and wfh.get('OriginalRole') not in ['HR ADMIN', 'Super admin']:
            new_status = 'Pending HR ADMIN Approval'
            msg = "Approved by you. Sent to HR."
        
        # Always update the status in DynamoDB
        WFHRequestsTable.update_item(
            Key={'EmployeeID': emp_id, 'RequestID': req_id}, 
            UpdateExpression="SET #s = :val, ApprovedBy = :u, ApprovalDate = :d, ProcessedBy = :pb", 
            ExpressionAttributeNames={'#s': 'Status'}, 
            ExpressionAttributeValues={
                ':val': new_status, 
                ':u': request.user.employee_id, 
                ':d': datetime.date.today().isoformat(),
                ':pb': request.user.employee_id
            }
        )
        
        if new_status == 'Approved':
            # Create Attendance Records for the date range (excluding weekends)
            start_str = wfh.get('WFHDate')
            end_str = wfh.get('EndDate') or start_str
            
            try:
                start_dt = datetime.datetime.strptime(start_str, '%Y-%m-%d').date()
                end_dt = datetime.datetime.strptime(end_str, '%Y-%m-%d').date()
                
                curr = start_dt
                while curr <= end_dt:
                    # Skip Weekends (5=Saturday, 6=Sunday)
                    if curr.weekday() < 5:
                        AttendanceTable.put_item({
                            'EmployeeID': emp_id, 
                            'RecordDate': curr.isoformat(), 
                            'ClockIn': '09:00', 
                            'ClockOut': '18:00', 
                            'Status': 'WFH' # Match payroll logic
                        })
                    curr += datetime.timedelta(days=1)
            except Exception as e:
                print(f"Error creating WFH attendance: {e}")
        
        # Notify Employee
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        emp_name = f"{employee.get('FirstName')} {employee.get('LastName')}" if employee else emp_id
        
        email_subj = "WFH Request Update"
        email_body = f"Hi {emp_name},\n\nYour Work From Home request for {wfh.get('WFHDate')} has been {new_status}.\n\nBest regards,\nLurnexa HR Admin"

        send_notification(
            employee_id=emp_id, 
            title="WFH Update", 
            message=f"Your request for {wfh.get('WFHDate')} is {new_status}", 
            n_type='WFH', 
            icon='fa-check-double', 
            color='success',
            email_subject=email_subj,
            email_body=email_body
        )
        messages.success(request, msg)
        return redirect('wfh_approvals')

class RejectWFHView(ManagerRequiredMixin, View):
    def get(self, request, emp_id, req_id):
        WFHRequestsTable.update_item(Key={'EmployeeID': emp_id, 'RequestID': req_id}, UpdateExpression="SET #s = :val, RejectedBy = :u, RejectionDate = :d, ProcessedBy = :pb", ExpressionAttributeNames={'#s': 'Status'}, ExpressionAttributeValues={':val': 'Rejected', ':u': request.user.employee_id, ':d': datetime.date.today().isoformat(), ':pb': request.user.employee_id})
        # Notify Employee
        wfh = WFHRequestsTable.get_item({'EmployeeID': emp_id, 'RequestID': req_id})
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        emp_name = f"{employee.get('FirstName')} {employee.get('LastName')}" if employee else emp_id

        send_notification(
            employee_id=emp_id, 
            title="WFH Rejected", 
            message=f"Your WFH request for {wfh.get('WFHDate') if wfh else ''} was rejected.", 
            n_type='WFH', 
            icon='fa-house-circle-xmark', 
            color='danger',
            email_subject="WFH Request Rejected",
            email_body=f"Hi {emp_name},\n\nYour Work From Home request for {wfh.get('WFHDate') if wfh else ''} has been REJECTED.\n\nPlease contact your manager for more details.\n\nBest regards,\nLurnexa HR Admin"
        )
        messages.error(request, "Rejected.")
        return redirect('wfh_approvals')

class GenerateExperienceLetterView(HRRequiredMixin, TemplateView):
    template_name = 'workflows/experience_letter.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        emp_id = self.kwargs.get('emp_id')
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        resignation = ResignationsTable.get_item({'EmployeeID': emp_id})
        
        if not employee or not resignation:
            return context # Will handle error in template or view
            
        context['employee'] = employee
        context['resignation'] = resignation
        context['today'] = datetime.date.today().strftime('%B %d, %Y')
        context['logo_base64'] = get_lurnexa_logo_base64()
        context['signature_stamp_base64'] = get_authorized_signature_stamp_base64()
        try:
            context['joined_date_fmt'] = datetime.datetime.strptime(employee['JoinedDate'], '%Y-%m-%d').strftime('%B %d, %Y')
        except Exception:
            context['joined_date_fmt'] = context['today']
        try:
            context['lwd_fmt'] = datetime.datetime.strptime(resignation['LastWorkingDay'], '%Y-%m-%d').strftime('%B %d, %Y')
        except Exception:
            context['lwd_fmt'] = context['today']
        return context



class GeneratePFLetterView(HRRequiredMixin, TemplateView):
    template_name = 'workflows/pf_letter.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        emp_id = self.kwargs.get('emp_id')
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        resignation = ResignationsTable.get_item({'EmployeeID': emp_id})
        
        if not employee or not resignation:
            return context
            
        context['employee'] = employee
        context['resignation'] = resignation
        context['today'] = datetime.date.today().strftime('%B %d, %Y')
        context['logo_base64'] = get_lurnexa_logo_base64()
        context['signature_stamp_base64'] = get_authorized_signature_stamp_base64()
        try:
            context['lwd_fmt'] = datetime.datetime.strptime(resignation['LastWorkingDay'], '%Y-%m-%d').strftime('%B %d, %Y')
        except Exception:
            context['lwd_fmt'] = context['today']
        return context


