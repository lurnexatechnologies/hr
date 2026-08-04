from django.shortcuts import render, redirect
from django.views import View
from django.contrib import messages
from django.http import JsonResponse
from auth_custom.mixins import LoginRequiredMixin, FeatureRequiredMixin
from core.dynamodb_service import TicketsTable, TicketCommentsTable, EmployeesTable
from core.utils import save_uploaded_file, send_notification, get_local_now, get_local_date
import uuid
import datetime

INDUSTRY_TICKET_CATEGORIES = {
    'RETAIL_SUPERMARKET': [
        {'key': 'POS_BREAKDOWN', 'label': 'POS Billing Terminal Breakdown / Screen Glitch'},
        {'key': 'CASH_TILL_DISCREPANCY', 'label': 'Cash Counter Till Discrepancy / Balancing Issue'},
        {'key': 'BARCODE_SCANNER_FAIL', 'label': 'Barcode Scanner / Price Label Reader Failure'},
        {'key': 'STOCK_DAMAGE_LOSS', 'label': 'Stock Damage / Inventory Shrinkage Alert'},
        {'key': 'STORE_FLOOR_MAINTENANCE', 'label': 'Store Floor Light / A.C. Maintenance Request'}
    ],
    'HEALTHCARE': [
        {'key': 'ICU_EQUIPMENT_FAIL', 'label': 'ICU / Ventilator / Clinical Equipment Malfunction'},
        {'key': 'BIOMEDICAL_EMERGENCY', 'label': 'Biomedical Engineering Immediate Repair Request'},
        {'key': 'PHARMACY_STOCK_DELAY', 'label': 'Pharmacy / Emergency Medicine Stock Delay'},
        {'key': 'DOCTOR_SHIFT_OVERRIDE', 'label': 'Doctor Emergency Callout / Shift Swap Issue'},
        {'key': 'INFECTION_HYGIENE_HAZARD', 'label': 'Infection Control / Waste Sanitation Hazard Alert'}
    ],
    'AUTO_RETAIL': [
        {'key': 'TEST_DRIVE_VEHICLE_SERVICING', 'label': 'Test-Drive Vehicle Breakdown / Servicing Request'},
        {'key': 'CRM_LEAD_DISPUTE', 'label': 'CRM Customer Lead Ownership Dispute'},
        {'key': 'COMMISSION_CALCULATION_QUERY', 'label': 'Vehicle Sales Commission Calculation Query'},
        {'key': 'FUEL_VOUCHER_ISSUE', 'label': 'Fuel Allowance / Voucher Claim Issue'}
    ],
    'TILES_MFG': [
        {'key': 'KILN_PRESS_MACHINERY_STOP', 'label': 'Kiln / Hydraulic Press Machinery Breakdown'},
        {'key': 'GATE_PASS_GLITCH', 'label': 'Factory Gate Pass / Biometric Punch Error'},
        {'key': 'RAW_MATERIAL_QUALITY_DEFECT', 'label': 'Raw Material Clay / Glaze Quality Defect'},
        {'key': 'SAFETY_PPE_REPLACEMENT', 'label': 'Safety Equipment (PPE) Damage / Replacement Request'}
    ],
    'POULTRY_PROCESSING': [
        {'key': 'COLD_STORAGE_TEMP_ALARM', 'label': 'Cold Storage Locker Temperature Hazard Alarm'},
        {'key': 'PROCESSING_LINE_STOP', 'label': 'Processing Line Conveyor Belt Mechanical Failure'},
        {'key': 'HYGIENE_STATION_FAILURE', 'label': 'Hygiene Station Water / Chemical Supply Issue'},
        {'key': 'FSSAI_COMPLIANCE_QUERY', 'label': 'FSSAI Food Safety Audit Query'}
    ],
    'AGRI_SEEDS': [
        {'key': 'SEED_LAB_INSTRUMENT_ERROR', 'label': 'Seed Testing Lab Specialist Instrument Error'},
        {'key': 'HARVEST_TRANSPORT_DELAY', 'label': 'Harvest Season Batch Transport Truck Breakdown'},
        {'key': 'FIELD_GEOFENCE_CHECKIN_FAIL', 'label': 'Farm Field Geofence Mobile Check-in Error'}
    ],
    'SOFTWARE_IT': [
        {'key': 'LAPTOP_HARDWARE_DEFECT', 'label': 'Laptop / Developer Workstation Hardware Defect'},
        {'key': 'VPN_SERVER_ACCESS_REQUEST', 'label': 'VPN / AWS Server Permission Access Request'},
        {'key': 'SOFTWARE_LICENSE_REQUEST', 'label': 'Dev Tool / IDE Software License Request'},
        {'key': 'SECURITY_CLEARANCE', 'label': 'IP Clearance / NDA Verification Query'}
    ],
    'EDUCATION_SCHOOL_COLLEGE': [
        {'key': 'EXAM_HALL_DUTY_CONFLICT', 'label': 'Examination Invigilation / Duty Roster Conflict'},
        {'key': 'LMS_GRADING_PORTAL_GLITCH', 'label': 'LMS / Student Marks Entry Portal Access Glitch'},
        {'key': 'CLASSROOM_AV_PROJECTOR_FAIL', 'label': 'Classroom Smartboard / Projector Breakdown'},
        {'key': 'LAB_EQUIPMENT_MAINTENANCE', 'label': 'Science / Computer Lab Equipment Repair Request'},
        {'key': 'EVALUATION_ALLOWANCE_QUERY', 'label': 'Exam Paper Evaluation / Extra Lecture Allowance Query'}
    ],
    'UNIVERSAL': [
        {'key': 'PAYSLIP_CALCULATION_QUERY', 'label': 'Payslip / Salary Calculation Query'},
        {'key': 'LOP_REVERSAL_REQUEST', 'label': 'LOP (Leave Deduction) Reversal Request'},
        {'key': 'EXPENSE_CLAIM_QUERY', 'label': 'Expense Claim Approval Delay Query'},
        {'key': 'LEAVE_BALANCE_CORRECTION', 'label': 'Leave Balance / Leave Policy Clarification'},
        {'key': 'GENERAL_ADMIN_SUPPORT', 'label': 'General Facilities & Admin Support'}
    ]
}

def get_ticket_categories_for_industry(industry_type):
    """Retrieve dynamic ticket categories combining industry presets + universal categories."""
    ind_cats = INDUSTRY_TICKET_CATEGORIES.get(industry_type, [])
    univ_cats = INDUSTRY_TICKET_CATEGORIES['UNIVERSAL']
    return ind_cats + univ_cats

def get_ticket_categories_for_industry(industry_type):
    """Retrieve dynamic ticket categories combining industry presets + universal categories."""
    ind_cats = INDUSTRY_TICKET_CATEGORIES.get(industry_type, [])
    univ_cats = INDUSTRY_TICKET_CATEGORIES['UNIVERSAL']
    return ind_cats + univ_cats


class TicketListView(LoginRequiredMixin, View):
    def get(self, request):
        user_emp_id = getattr(request.user, 'employee_id', None)
        org_id = getattr(request.user, 'org_id', None)
        user_role = getattr(request.user, 'role', 'Employee')

        try:
            all_tickets = [t for t in TicketsTable.scan() if t.get('OrgID') == org_id]
        except Exception:
            all_tickets = []

        if user_role in ['HR ADMIN', 'Manager', 'Super admin', 'Admin']:
            tickets = all_tickets
        else:
            tickets = [t for t in all_tickets if t.get('EmployeeID') == user_emp_id]

        status_filter = request.GET.get('status', 'ALL')
        if status_filter != 'ALL':
            tickets = [t for t in tickets if t.get('Status') == status_filter]

        # Multi-filter: Department Filter
        dept_filter = request.GET.get('dept', '').strip()
        if dept_filter:
            tickets = [t for t in tickets if t.get('AssignedDepartment') == dept_filter]

        # Multi-filter: Priority Filter
        priority_filter = request.GET.get('priority', '').strip()
        if priority_filter:
            tickets = [t for t in tickets if t.get('Priority') == priority_filter]

        # Search Query Filter
        query = request.GET.get('q', '').strip().lower()
        if query:
            tickets = [
                t for t in tickets if
                query in t.get('TicketID', '').lower() or
                query in t.get('Subject', '').lower() or
                query in t.get('Description', '').lower() or
                query in t.get('EmployeeID', '').lower()
            ]

        tickets = sorted(tickets, key=lambda x: x.get('CreatedAt', ''), reverse=True)

        # Extract available departments for filter dropdown
        departments = sorted(list(set([t.get('AssignedDepartment') for t in all_tickets if t.get('AssignedDepartment')])))

        return render(request, 'tickets/ticket_list.html', {
            'tickets': tickets,
            'status_filter': status_filter,
            'dept_filter': dept_filter,
            'priority_filter': priority_filter,
            'search_query': query,
            'departments': departments,
            'open_count': len([t for t in all_tickets if t.get('Status') == 'Open']),
            'in_progress_count': len([t for t in all_tickets if t.get('Status') == 'In Progress']),
            'resolved_count': len([t for t in all_tickets if t.get('Status') in ['Resolved', 'Closed']])
        })


class CreateTicketView(LoginRequiredMixin, View):
    def get(self, request):
        org_id = getattr(request.user, 'org_id', None)
        industry_type = 'SOFTWARE_IT'
        if org_id:
            try:
                from core.dynamodb_service import OrganizationsTable
                org_item = OrganizationsTable.get_item({'OrgID': org_id})
                if org_item:
                    industry_type = org_item.get('IndustryType', 'SOFTWARE_IT')
            except Exception:
                pass

        categories = get_ticket_categories_for_industry(industry_type)

        return render(request, 'tickets/create_ticket.html', {
            'categories': categories,
            'industry_type': industry_type
        })

    def post(self, request):
        user_emp_id = getattr(request.user, 'employee_id', None)
        org_id = getattr(request.user, 'org_id', None)

        subject = request.POST.get('subject', '').strip()
        category = request.POST.get('category', 'GENERAL_ADMIN_SUPPORT')
        priority = request.POST.get('priority', 'Medium')
        description = request.POST.get('description', '').strip()
        assigned_dept = request.POST.get('assigned_department', 'IT Support')

        if not subject or not description:
            messages.error(request, "Subject and Description are required.")
            return self.get(request)

        attachment_url = save_uploaded_file(request.FILES.get('attachment'), 'tickets/docs')

        ticket_id = f"TICK-{uuid.uuid4().hex[:6].upper()}"

        ticket_item = {
            'TicketID': ticket_id,
            'OrgID': org_id,
            'EmployeeID': user_emp_id,
            'Category': category,
            'Priority': priority,
            'Subject': subject,
            'Description': description,
            'AttachmentURL': attachment_url,
            'Status': 'Open',
            'AssignedDepartment': assigned_dept,
            'AssignedTo': 'Unassigned',
            'CreatedAt': get_local_now().isoformat(),
            'UpdatedAt': get_local_now().isoformat()
        }

        try:
            TicketsTable.put_item(ticket_item)
            # Dispatch notification to user
            send_notification(
                user_emp_id,
                f"Ticket #{ticket_id} Raised",
                f"Your ticket '{subject}' has been submitted to {assigned_dept}."
            )
            messages.success(request, f"Ticket #{ticket_id} created successfully!")
        except Exception as e:
            messages.error(request, f"Error raising ticket: {e}")

        return redirect('ticket_list')


class TicketDetailView(LoginRequiredMixin, View):
    def get(self, request, ticket_id):
        try:
            ticket = TicketsTable.get_item({'TicketID': ticket_id})
        except Exception:
            ticket = None

        if not ticket:
            messages.error(request, "Ticket not found.")
            return redirect('ticket_list')

        # Check permission: Creator or Resolver
        user_emp_id = getattr(request.user, 'employee_id', None)
        user_role = getattr(request.user, 'role', 'Employee')

        if user_role not in ['HR ADMIN', 'Manager', 'Super admin'] and ticket.get('EmployeeID') != user_emp_id:
            messages.error(request, "Permission denied. You can only view your own tickets.")
            return redirect('ticket_list')

        try:
            all_comments = [c for c in TicketCommentsTable.scan() if c.get('TicketID') == ticket_id]
            comments = sorted(all_comments, key=lambda x: x.get('CreatedAt', ''))
        except Exception:
            comments = []

        now_iso = get_local_now().isoformat()
        ticket['IsOverdue'] = (ticket.get('Status') not in ['Resolved', 'Closed']) and (ticket.get('SLADueTime', '') < now_iso)

        # Fetch org active employees for resolver assignment dropdown
        org_id = getattr(request.user, 'org_id', None)
        try:
            org_employees = [
                e for e in EmployeesTable.scan()
                if e.get('OrgID') == org_id and e.get('Status') == 'Active'
            ]
            org_employees = sorted(org_employees, key=lambda x: f"{x.get('FirstName', '')} {x.get('LastName', '')}")
        except Exception:
            org_employees = []

        return render(request, 'tickets/ticket_detail.html', {
            'ticket': ticket,
            'comments': comments,
            'org_employees': org_employees
        })


class AddTicketCommentView(LoginRequiredMixin, View):
    def post(self, request, ticket_id):
        user_emp_id = getattr(request.user, 'employee_id', None)
        message_text = request.POST.get('message', '').strip()
        is_internal = request.POST.get('is_internal') == 'on'

        if not message_text:
            messages.error(request, "Comment message cannot be empty.")
            return redirect('ticket_detail', ticket_id=ticket_id)

        attachment_url = save_uploaded_file(request.FILES.get('attachment'), 'tickets/comments')

        comment_id = str(uuid.uuid4())
        author_name = f"{getattr(request.user, 'first_name', '')} {getattr(request.user, 'last_name', '')}".strip() or user_emp_id

        comment_item = {
            'CommentID': comment_id,
            'TicketID': ticket_id,
            'AuthorID': user_emp_id,
            'AuthorName': author_name,
            'Message': message_text,
            'AttachmentURL': attachment_url,
            'IsInternalNote': is_internal,
            'CreatedAt': get_local_now().isoformat()
        }

        try:
            TicketCommentsTable.put_item(comment_item)
            messages.success(request, "Comment added to ticket thread.")

            # Real-time notifications: notify ticket owner if reply by resolver/admin, or notify assignee if reply by ticket owner
            ticket = TicketsTable.get_item({'TicketID': ticket_id})
            if ticket and not is_internal:
                ticket_owner = ticket.get('EmployeeID')
                assigned_to = ticket.get('AssignedTo')
                
                if user_emp_id != ticket_owner and ticket_owner:
                    send_notification(
                        ticket_owner,
                        f"New Update on Ticket #{ticket_id}",
                        f"{author_name} posted a update on your ticket: '{ticket.get('Subject')}'"
                    )
                elif user_emp_id == ticket_owner and assigned_to and assigned_to != 'Unassigned':
                    send_notification(
                        assigned_to,
                        f"User Reply on Ticket #{ticket_id}",
                        f"Ticket creator posted a response on '{ticket.get('Subject')}'"
                    )
        except Exception as e:
            messages.error(request, f"Error posting comment: {e}")

        return redirect('ticket_detail', ticket_id=ticket_id)


class UpdateTicketStatusView(LoginRequiredMixin, View):
    def post(self, request, ticket_id):
        user_role = getattr(request.user, 'role', 'Employee')
        user_emp_id = getattr(request.user, 'employee_id', None)

        if user_role not in ['HR ADMIN', 'Manager', 'Super admin']:
            messages.error(request, "Permission denied. Only HR Admins and Managers can update ticket status.")
            return redirect('ticket_detail', ticket_id=ticket_id)

        new_status = request.POST.get('status')
        assigned_to = request.POST.get('assigned_to', user_emp_id)

        try:
            ticket = TicketsTable.get_item({'TicketID': ticket_id})
            if ticket:
                prev_status = ticket.get('Status')
                prev_assignee = ticket.get('AssignedTo')

                ticket['Status'] = new_status
                ticket['AssignedTo'] = assigned_to
                ticket['UpdatedAt'] = get_local_now().isoformat()
                TicketsTable.put_item(ticket)
                messages.success(request, f"Ticket #{ticket_id} updated to '{new_status}'.")

                # Send real-time notification to ticket owner
                ticket_owner = ticket.get('EmployeeID')
                if ticket_owner:
                    send_notification(
                        ticket_owner,
                        f"Ticket #{ticket_id} Status Updated",
                        f"Your ticket '{ticket.get('Subject')}' status has been updated to '{new_status}'."
                    )

                # Send real-time notification to newly assigned resolver
                if assigned_to and assigned_to != prev_assignee and assigned_to != 'Unassigned':
                    send_notification(
                        assigned_to,
                        f"Ticket Assigned to You (#{ticket_id})",
                        f"You have been assigned to resolve ticket '{ticket.get('Subject')}'."
                    )
        except Exception as e:
            messages.error(request, f"Error updating ticket status: {e}")

        return redirect('ticket_detail', ticket_id=ticket_id)


class SubmitTicketRatingView(LoginRequiredMixin, View):
    def post(self, request, ticket_id):
        user_emp_id = getattr(request.user, 'employee_id', None)
        rating_val = request.POST.get('rating', '5')
        feedback_val = request.POST.get('feedback', '').strip()

        try:
            ticket = TicketsTable.get_item({'TicketID': ticket_id})
            if not ticket:
                messages.error(request, "Ticket not found.")
                return redirect('ticket_list')

            if ticket.get('EmployeeID') != user_emp_id:
                messages.error(request, "Only the ticket creator can rate resolution satisfaction.")
                return redirect('ticket_detail', ticket_id=ticket_id)

            ticket['CSATRating'] = int(rating_val)
            ticket['CSATFeedback'] = feedback_val
            ticket['UpdatedAt'] = get_local_now().isoformat()
            TicketsTable.put_item(ticket)

            messages.success(request, "Thank you! Your resolution rating & feedback have been submitted.")
        except Exception as e:
            messages.error(request, f"Error saving rating: {e}")

        return redirect('ticket_detail', ticket_id=ticket_id)

