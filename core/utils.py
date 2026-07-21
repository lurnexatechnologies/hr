import os
import datetime
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.mail import EmailMessage
import threading
from core.dynamodb_service import EmployeesTable, NotificationsTable

DEFAULT_LEAVE_POLICIES = {
    'Permanent': {
        'SL_Limit': 12.0,
        'CL_Limit': 12.0,
        'PL_Limit': 0.0,
        'AllowedTypes': [
            'Earned Leave (EL)',
            'Sick Leave (SL)',
            'Casual Leave (CL)',
            'Compensatory Off (Comp Off)',
            'Marriage Leave',
            'Maternity Leave',
            'Paternity Leave',
            'Unpaid Leave'
        ]
    },
    'Probation': {
        'SL_Limit': 12.0,
        'CL_Limit': 12.0,
        'PL_Limit': 0.0,
        'AllowedTypes': [
            'Sick Leave (SL)',
            'Casual Leave (CL)',
            'Unpaid Leave'
        ]
    },
    'Intern': {
        'SL_Limit': 0.0,
        'CL_Limit': 0.0,
        'PL_Limit': 0.0,
        'AllowedTypes': [
            'Unpaid Leave'
        ]
    }
}

def send_notification(employee_id, title, message, n_type='System', icon='fa-bell', color='primary', email_subject=None, email_body=None, attachments=None, org_id=None):
    """
    Sends a notification to an employee. 
    Saves to DynamoDB and optionally sends an email in a background thread.
    """
    
    timestamp = get_local_now().isoformat()

    # Resolve org_id if not explicitly provided
    if not org_id:
        from core.middleware import get_current_request
        request = get_current_request()
        if request and hasattr(request, 'user') and getattr(request.user, 'org_id', None):
            org_id = request.user.org_id
        else:
            try:
                emp = EmployeesTable.get_item({'EmployeeID': employee_id})
                if emp:
                    org_id = emp.get('OrgID')
            except Exception:
                pass
    
    # 1. Save to DynamoDB
    notification_item = {
        'EmployeeID': employee_id,
        'Timestamp': timestamp,
        'Title': title,
        'Message': message,
        'Type': n_type,
        'Icon': icon,
        'Color': color,
        'IsRead': False
    }
    if org_id:
        notification_item['OrgID'] = org_id

    try:
        NotificationsTable.put_item(notification_item)
    except Exception as e:
        print(f"Error saving notification: {e}")

    # Resolve sender avatar url from the request/session context (must do on the parent request thread)
    from core.middleware import get_current_request
    request = get_current_request()
    sender_avatar_url = None
    if request:
        if request.user and request.user.is_authenticated:
            photo = getattr(request.user, 'passport_photo', None)
            if photo:
                if photo.startswith('http'):
                    sender_avatar_url = photo
                else:
                    sender_avatar_url = request.build_absolute_uri(settings.MEDIA_URL + photo)
        if not sender_avatar_url:
            sender_avatar_url = request.build_absolute_uri(settings.STATIC_URL + 'img/namelesslogolurnexa.png')

    # 1.5 Send Firebase Push Notification asynchronously in a background thread
    def _send_fcm_thread(emp_id, n_title, n_message, notification_type, timestamp):
        try:
            import firebase_admin
            from firebase_admin import messaging
            from core.dynamodb_service import DeviceTokensTable
            from boto3.dynamodb.conditions import Key
            
            # Skip if firebase is not initialized
            if not firebase_admin._apps:
                print("DEBUG: Firebase Admin SDK not initialized, skipping push notification.")
                return
                
            clean_eid = str(emp_id).strip()
            # Query all device tokens for this employee
            tokens_data = DeviceTokensTable.query(
                KeyConditionExpression=Key('EmployeeID').eq(clean_eid)
            )
            if not tokens_data:
                print(f"DEBUG: No device tokens found for employee {clean_eid}, skipping push.")
                return
                
            tokens_list = [t for t in tokens_data if t.get('DeviceToken')]
            if not tokens_list:
                return

            print(f"DEBUG: [FCM] Sending push to employee {clean_eid} | Title: {n_title} | Tokens count: {len(tokens_list)}")
            
            route_map = {
                'Leave Request': '/leave/approvals/',
                'Leave': '/leave/history/',
                'Attendance': '/attendance/my_records/',
                'WFH Request': '/workflows/wfh/approvals/',
                'WFH': '/attendance/history/',
                'Expense Request': '/workflows/expenses/approvals/',
                'Expense': '/workflows/expenses/',
                'Payroll': '/payroll/payslips/',
                'Payslip': '/payroll/payslips/',
                'Announcement': '/core/notifications/',
                'Policy': '/core/policies/',
                'Resignation Request': '/workflows/resignation/approvals/',
                'Resignation': '/workflows/resignation/',
                'Onboarding': '/employees/directory/',
                'Offboarding': '/employees/directory/',
                'Promotion': '/employees/profile/',
                'Salary Revision': '/employees/profile/',
                'Appraisal': '/core/okrs/',
                'Performance': '/core/okrs/',
                'OKRs': '/core/okrs/',
                'Task': '/core/okrs/',
                'Task Assignment': '/core/okrs/',
                'Birthday': '/core/notifications/',
                'Work Anniversary': '/core/notifications/',
                'Asset Request': '/employees/assets/',
                'Asset Allocation': '/employees/my-assets/',
                'Asset': '/employees/my-assets/',
                'Assets': '/employees/my-assets/',
                'Certificate Request': '/employees/certificates/approvals/',
                'Certificate': '/employees/profile/',
                'Certificates': '/employees/profile/'
            }
            target_route = route_map.get(notification_type, '/core/notifications/')
            # Create message payload for each device token
            for t_item in tokens_list:
                token = t_item.get('DeviceToken')
                platform = str(t_item.get('Platform', 'android')).lower()
                try:
                    # Construct message
                    if platform == 'android':
                        message_payload = messaging.Message(
                            notification=messaging.Notification(
                                title=str(n_title),
                                body=str(n_message)
                            ),
                            android=messaging.AndroidConfig(
                                notification=messaging.AndroidNotification(
                                    sound='default',
                                    notification_channel_id='fcm_default_channel'
                                )
                            ),
                            data={
                                'title': str(n_title),
                                'body': str(n_message),
                                'type': str(notification_type),
                                'route': str(target_route),
                                'sender_avatar_url': str(sender_avatar_url or ''),
                                'timestamp': str(timestamp)
                            },
                            token=token
                        )
                    else:
                        # Send notification payload for iOS and other platforms
                        message_payload = messaging.Message(
                            notification=messaging.Notification(
                                title=n_title,
                                body=n_message,
                            ),
                            apns=messaging.APNSConfig(
                                payload=messaging.APNSPayload(
                                    aps=messaging.Aps(
                                        sound='default'
                                    )
                                )
                            ),
                            data={
                                'title': str(n_title),
                                'body': str(n_message),
                                'type': str(notification_type),
                                'route': str(target_route),
                                'sender_avatar_url': str(sender_avatar_url or ''),
                                'timestamp': str(timestamp)
                            },
                            token=token
                        )
                    messaging.send(message_payload)
                    print(f"DEBUG: [FCM] Push sent successfully to device token: {token[:15]}...")
                except messaging.UnregisteredError:
                    # Token is invalid or expired, delete it from DynamoDB
                    print(f"DEBUG: [FCM] Token {token[:15]}... is unregistered. Deleting from DB.")
                    try:
                        DeviceTokensTable.delete_item({'EmployeeID': clean_eid, 'DeviceToken': token})
                    except Exception as e:
                        print(f"ERROR: Failed to delete invalid token from DB: {e}")
                except Exception as e:
                    print(f"ERROR: Failed sending FCM message to token: {e}")
        except Exception as e:
            print(f"ERROR in _send_fcm_thread: {e}")

    fcm_thread = threading.Thread(
        target=_send_fcm_thread,
        args=(employee_id, title, message, n_type, timestamp)
    )
    fcm_thread.daemon = True
    fcm_thread.start()

    # 2. Send Email if requested
    if email_subject and email_body:
        # Fetch employee email
        try:
            # Strip any whitespace from employee_id
            clean_eid = str(employee_id).strip()
            employee = EmployeesTable.get_item({'EmployeeID': clean_eid})
            if employee and employee.get('Email'):
                recipient_email = employee.get('Email')
                
                # Internal function to send mail with error logging
                def _send_email_thread(subject, body, from_email, recipient_list, atts=None):
                    try:
                        print(f"DEBUG: [Thread] Attempting to send email to {recipient_list} | Subject: {subject}")
                        email = EmailMessage(
                            subject=subject,
                            body=body,
                            from_email=from_email,
                            to=recipient_list,
                        )
                        if atts:
                            for filename, content, mimetype in atts:
                                email.attach(filename, content, mimetype)
                        email.send(fail_silently=False)
                        print(f"DEBUG: [Thread] Email sent successfully to {recipient_list}")
                    except Exception as e:
                        print(f"ERROR: [Thread] Failed to send email to {recipient_list}: {e}")
                        import traceback
                        traceback.print_exc()

                # Start the background thread
                thread = threading.Thread(
                    target=_send_email_thread,
                    args=(email_subject, email_body, settings.DEFAULT_FROM_EMAIL, [recipient_email], attachments)
                )
                thread.daemon = True
                thread.start()
            else:
                print(f"DEBUG: No email found for employee {clean_eid}, skipping email notification.")
        except Exception as e:
            print(f"Error in send_notification email block: {e}")

def get_days_count(leave_request):
    """
    Safely retrieves the number of days for a leave request,
    falling back to date difference or 1.0 if not specified.
    """
    val = leave_request.get('DaysCount')
    if val is not None and str(val).strip() != '':
        try:
            return float(val)
        except ValueError:
            pass
    try:
        start_str = leave_request.get('LeaveDate')
        end_str = leave_request.get('EndDate') or start_str
        start = datetime.datetime.strptime(start_str, '%Y-%m-%d').date()
        end = datetime.datetime.strptime(end_str, '%Y-%m-%d').date()
        return float((end - start).days + 1)
    except Exception:
        return 1.0

def get_initial_leave_balance(employee, leave_type):
    """
    Calculates the initial leave balance for SL and CL.
    Prorated from joining/full-time month to December of the joining/full-time year for new employees.
    If joined/full-time in a previous year, gets the full configured limit.
    """
    org_id = employee.get('OrgID')
    emp_type = 'Permanent'
    if employee.get('EmploymentType') == 'Intern':
        emp_type = 'Intern'
    elif employee.get('EmploymentStatus') == 'Probation':
        emp_type = 'Probation'

    # Fallback default limits
    sl_limit = 12.0
    cl_limit = 12.0
    if emp_type == 'Intern':
        sl_limit = 0.0
        cl_limit = 0.0

    if org_id:
        try:
            from core.dynamodb_service import OrganizationsTable
            org = OrganizationsTable.get_item({'OrgID': org_id})
            if org and 'LeavePolicies' in org and emp_type in org['LeavePolicies']:
                policy = org['LeavePolicies'][emp_type]
                sl_limit = float(policy.get('SL_Limit', sl_limit))
                cl_limit = float(policy.get('CL_Limit', cl_limit))
        except Exception as e:
            print(f"Error fetching org policy in get_initial_leave_balance: {e}")

    limit = 0.0
    if leave_type == 'SL':
        limit = sl_limit
    elif leave_type == 'CL':
        limit = cl_limit
    else:
        return 0.0

    effective_date_str = employee.get('FullTimeDate') or employee.get('JoinedDate')
    if not effective_date_str:
        return limit

    try:
        effective_date = datetime.datetime.strptime(effective_date_str, '%Y-%m-%d').date()
        today = get_local_date()
        
        if effective_date.year < today.year:
            return limit
        else:
            months_count = 12 - effective_date.month + 1
            prorated = (limit * months_count) / 12.0
            return float(max(0.0, min(limit, round(prorated, 1))))
    except Exception as e:
        print(f"Error calculating initial leave: {e}")
        return limit

def refresh_monthly_leaves(employee):
    """
    Refreshes leave balances (SL, CL) on the 1st day of the month.
    - On Jan 1st, resets SL and CL to 12.0 (previous year's balance disappears).
    - On every month's 1st day, accrues Earned Leave (EL) based on last month's working days / 20.
    """
    today = get_local_date()
    if today.day != 1:
        return False # Only on the 1st

    # Interns do not accrue paid/earned leaves
    if employee.get('EmploymentType') == 'Intern':
        return False

    # Inactive or resigned (ex-employees) should not have their leaves updated
    if not employee.get('IsActive', True):
        return False

    # Check if today is before the employee's Full-time Date (or JoinedDate)
    effective_date_str = employee.get('FullTimeDate') or employee.get('JoinedDate')
    if effective_date_str:
        try:
            effective_date = datetime.datetime.strptime(effective_date_str, '%Y-%m-%d').date()
            if today < effective_date:
                return False
        except Exception as e:
            print(f"Error checking effective date: {e}")

    emp_id = employee.get('EmployeeID')
    current_month = today.strftime('%Y-%m')
    last_refresh = employee.get('LastLeaveRefresh')

    if last_refresh == current_month:
        return False # Already refreshed this month

    is_new_year = today.month == 1

    # Determine last month and last year for the cycle calculation
    if today.month == 1:
        last_month = 12
        last_year = today.year - 1
    else:
        last_month = today.month - 1
        last_year = today.year

    accrued_el = 0.0
    try:
        from payroll.views import get_attendance_summary
        summary = get_attendance_summary(emp_id, last_month, last_year)
        paid_days = float(summary.get('paid_days', 0.0))
        accrued_el = round(paid_days / 20.0, 2)
    except Exception as e:
        print(f"Error calculating EL accrual for {emp_id}: {e}")

    try:
        # Get existing Earned Leave balance
        current_el = float(employee.get('Balance_PL') or 0.0)
        new_el = current_el + accrued_el

        if is_new_year:
            org_id = employee.get('OrgID')
            emp_type = 'Permanent'
            if employee.get('EmploymentType') == 'Intern':
                emp_type = 'Intern'
            elif employee.get('EmploymentStatus') == 'Probation':
                emp_type = 'Probation'

            # Fallback default limits
            sl_limit = 12.0
            cl_limit = 12.0
            if emp_type == 'Intern':
                sl_limit = 0.0
                cl_limit = 0.0

            if org_id:
                try:
                    from core.dynamodb_service import OrganizationsTable
                    org = OrganizationsTable.get_item({'OrgID': org_id})
                    if org and 'LeavePolicies' in org and emp_type in org['LeavePolicies']:
                        policy = org['LeavePolicies'][emp_type]
                        sl_limit = float(policy.get('SL_Limit', sl_limit))
                        cl_limit = float(policy.get('CL_Limit', cl_limit))
                except Exception as e:
                    print(f"Error fetching org policy in refresh_monthly_leaves: {e}")

            # Reset CL and SL to configured limits on Jan 1st, and update EL
            EmployeesTable.update_item(
                Key={'EmployeeID': emp_id},
                UpdateExpression="SET Balance_SL = :sl, Balance_CL = :cl, Balance_PL = :pl, LastLeaveRefresh = :lr",
                ExpressionAttributeValues={
                    ':sl': str(sl_limit),
                    ':cl': str(cl_limit),
                    ':pl': str(new_el),
                    ':lr': current_month
                }
            )
            print(f"Leave balances reset to {sl_limit}/{cl_limit} (SL/CL) and EL accrued (+{accrued_el}) on Jan 1st for {emp_id}")
            return True
        else:
            # On other months, just accrue EL
            EmployeesTable.update_item(
                Key={'EmployeeID': emp_id},
                UpdateExpression="SET Balance_PL = :pl, LastLeaveRefresh = :lr",
                ExpressionAttributeValues={
                    ':pl': str(new_el),
                    ':lr': current_month
                }
            )
            print(f"EL accrued (+{accrued_el}) on {current_month} 1st for {emp_id}")
            return True
    except Exception as e:
        print(f"Failed to refresh leaves for {emp_id}: {e}")
        return False

def save_uploaded_file(uploaded_file, folder='uploads', org_id=None):
    """
    Saves an uploaded file to the MEDIA_ROOT/folder directory.
    Returns the filename of the saved file.
    """
    if not uploaded_file:
        return None

    if not org_id:
        from core.middleware import get_current_request
        request = get_current_request()
        if request and hasattr(request, 'user') and getattr(request.user, 'org_id', None):
            org_id = request.user.org_id

    if org_id:
        folder = os.path.join(org_id, folder)
        
    fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, folder))
    filename = fs.save(uploaded_file.name, uploaded_file)
    # Return the relative path from MEDIA_ROOT
    return os.path.join(folder, filename).replace('\\', '/')


def apply_pending_hikes():
    from core.dynamodb_service import EmployeesTable, EmployeeLettersTable
    import datetime
    try:
        today = get_local_date().isoformat()
        # Scan for Hike Letters
        letters = EmployeeLettersTable.scan(
            FilterExpression="LetterType = :lt",
            ExpressionAttributeValues={":lt": "Hike Letter"}
        )
        for letter in letters:
            is_applied = letter.get('HikeApplied', False)
            eff_date = letter.get('EffectiveDate')
            hike_pct_str = letter.get('HikePercentage')
            
            if not is_applied and eff_date and hike_pct_str:
                if eff_date <= today:
                    emp_id = letter.get('EmployeeID')
                    emp = EmployeesTable.get_item({'EmployeeID': emp_id})
                    if emp:
                        try:
                            current_salary = safe_float(emp.get('SalaryPA'))
                            hike_pct = float(hike_pct_str or 0)
                            if hike_pct > 0:
                                new_salary = current_salary * (1 + hike_pct / 100)
                                emp['SalaryPA'] = str(round(new_salary, 2))
                                EmployeesTable.put_item(emp)
                            
                            letter['HikeApplied'] = True
                            EmployeeLettersTable.put_item(letter)
                            print(f"Automatically applied pending hike of {hike_pct}% to employee {emp_id} effective from {eff_date}")
                        except Exception as e:
                            print(f"Error applying pending hike to {emp_id}: {e}")
                            
        # Scan for Promotion Letters
        promo_letters = EmployeeLettersTable.scan(
            FilterExpression="LetterType = :lt",
            ExpressionAttributeValues={":lt": "Promotion Letter"}
        )
        for letter in promo_letters:
            is_applied = letter.get('PromotionApplied', False)
            eff_date = letter.get('EffectiveDate')
            new_designation = letter.get('NewDesignation')
            new_salary = letter.get('NewSalary')
            
            if not is_applied and eff_date and new_designation:
                if eff_date <= today:
                    emp_id = letter.get('EmployeeID')
                    emp = EmployeesTable.get_item({'EmployeeID': emp_id})
                    if emp:
                        try:
                            emp['Designation'] = new_designation
                            if new_salary:
                                emp['SalaryPA'] = new_salary
                            EmployeesTable.put_item(emp)
                            
                            letter['PromotionApplied'] = True
                            EmployeeLettersTable.put_item(letter)
                            print(f"Automatically applied pending promotion to {new_designation} for employee {emp_id} effective from {eff_date}")
                        except Exception as e:
                            print(f"Error applying pending promotion to {emp_id}: {e}")
    except Exception as ex:
        print(f"Error checking pending hikes/promotions: {ex}")


def safe_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    try:
        clean_str = str(val).replace(',', '').replace('₹', '').replace(' ', '').strip()
        if not clean_str:
            return default
        return float(clean_str)
    except (ValueError, TypeError):
        return default


def get_lurnexa_logo_base64():
    """
    Returns the base64 encoded data URI of the Lurnexa logo.
    """
    import base64
    from django.conf import settings

    path = os.path.join(settings.BASE_DIR, 'static', 'img', 'namelesslogolurnexa.png')
    if os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
            return f"data:image/png;base64,{encoded}"
        except Exception as e:
            print(f"Error base64 encoding logo: {e}")
    return ""

def get_authorized_stamp_base64():
    import base64
    from django.conf import settings
    path = os.path.join(settings.BASE_DIR, 'static', 'img', 'authorized_stamp.png')
    if os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
            return f"data:image/png;base64,{encoded}"
        except Exception as e:
            print(f"Error base64 encoding stamp: {e}")
    return ""

def get_authorized_signature_base64():
    import base64
    from django.conf import settings
    path = os.path.join(settings.BASE_DIR, 'static', 'img', 'authorized_signature.png')
    if os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
            return f"data:image/png;base64,{encoded}"
        except Exception as e:
            print(f"Error base64 encoding signature: {e}")
    return ""

def get_authorized_signature_stamp_base64():
    import base64
    from django.conf import settings
    path = os.path.join(settings.BASE_DIR, 'static', 'img', 'authorized_signature_stamp.png')
    if os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
            return f"data:image/png;base64,{encoded}"
        except Exception as e:
            print(f"Error base64 encoding signature stamp: {e}")
    return ""


def get_local_now():
    """
    Returns the current datetime in the configured TIME_ZONE (Asia/Kolkata).
    """
    from django.utils import timezone
    return timezone.localtime(timezone.now())


def get_local_date():
    """
    Returns the current date in the configured TIME_ZONE (Asia/Kolkata).
    """
    return get_local_now().date()


def is_mobile_app(request):
    """
    Detects if the incoming request is originating from the Capacitor mobile app wrapper.
    Checks the User-Agent (for webviews on Android/iOS) and X-Requested-With header.
    """
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    requested_with = request.META.get('HTTP_X_REQUESTED_WITH', '')
    
    # 1. Check custom Android header/package name
    if 'com.lurnexa' in requested_with:
        return True
        
    # 2. Check Android webview User-Agent characteristics
    if 'Android' in user_agent and ('wv' in user_agent or 'Version/4.0' in user_agent):
        return True
        
    # 3. Check iOS webview User-Agent characteristics (iOS Capacitor / WKWebView)
    if ('iPhone' in user_agent or 'iPad' in user_agent) and 'Mobile/' in user_agent and 'Safari' not in user_agent:
        return True
        
    return False


def can_add_employee(org_id):
    """Check if org can add more employees based on plan limits."""
    if not org_id:
        return True, ""
    from core.dynamodb_service import OrganizationsTable, EmployeesTable
    from core.features import PLAN_LIMITS
    try:
        org = OrganizationsTable.get_item({'OrgID': org_id})
    except Exception:
        org = None

    if not org:
        # Fallback to true if organization details are not yet fully provisioned
        return True, ""

    plan = org.get('Plan', 'basic')
    max_emp = org.get('MaxEmployees') or PLAN_LIMITS.get(plan, {}).get('max_employees', 25)

    try:
        current_count = len(EmployeesTable.scan(
            FilterExpression="OrgID = :oid AND IsActive = :active",
            ExpressionAttributeValues={":oid": org_id, ":active": True}
        ))
    except Exception:
        current_count = 0

    if current_count >= max_emp:
        return False, f"Employee limit ({max_emp}) reached for your {plan.title()} plan."
    return True, ""


def resolve_workflow_step(employee_id, org_id, current_status=None, action='submit', request_type='leave_request'):
    """
    Determines next status, next approver ID, and whether it's final approved
    based on the organization's custom WorkflowRules.
    WorkflowRules is a dictionary stored in the organization config.
    """
    from core.dynamodb_service import OrganizationsTable, ReportingHierarchyTable, UsersTable, EmployeesTable
    
    # 1. Load organization config and get WorkflowRules
    workflow_rules = None
    if org_id:
        try:
            org = OrganizationsTable.get_item({'OrgID': org_id})
            if org:
                workflow_rules = org.get('WorkflowRules')
        except Exception:
            pass

    # 2. Get submitter role
    submitter_role = 'Employee'
    try:
        emp = EmployeesTable.get_item({'EmployeeID': employee_id})
        if emp:
            submitter_role = emp.get('Role', 'Employee')
    except Exception:
        pass

    # Standardize submitter_role
    if submitter_role not in ['Employee', 'Manager', 'HR ADMIN', 'Super admin']:
        submitter_role = 'Employee'

    # Default fallback rules if no custom ones are configured
    default_rules = {
        'leave_request': {
            'Employee': ['Manager'],
            'Manager': ['HR ADMIN'],
            'HR ADMIN': ['Super admin'],
            'Super admin': []
        },
        'expense_claim': {
            'Employee': ['Manager'],
            'Manager': ['HR ADMIN'],
            'HR ADMIN': ['Super admin'],
            'Super admin': []
        },
        'wfh_request': {
            'Employee': ['Manager'],
            'Manager': ['HR ADMIN'],
            'HR ADMIN': ['Super admin'],
            'Super admin': []
        },
        'payroll_approval': {
            'Employee': ['Manager', 'HR ADMIN', 'Super admin'],
            'Manager': ['HR ADMIN', 'Super admin'],
            'HR ADMIN': ['Super admin'],
            'Super admin': []
        }
    }

    rules_for_type = {}
    if workflow_rules:
        rules_for_type = workflow_rules.get(request_type, {})
        
    if not rules_for_type:
        chain = default_rules.get(request_type, {}).get(submitter_role, [])
    else:
        chain = rules_for_type.get(submitter_role, [])
    
    # If no steps defined (e.g. Super Admin), approve immediately
    if not chain:
        return 'Approved', None, True

    # 3. Determine actual managers/HRs in the org
    manager_id = None
    try:
        hierarchy = ReportingHierarchyTable.scan(
            FilterExpression="EmployeeID = :eid",
            ExpressionAttributeValues={":eid": employee_id}
        )
        if hierarchy:
            manager_id = hierarchy[0].get('ManagerID')
    except Exception:
        pass

    manager_manager_id = None
    if manager_id:
        try:
            m_hierarchy = ReportingHierarchyTable.scan(
                FilterExpression="EmployeeID = :eid",
                ExpressionAttributeValues={":eid": manager_id}
            )
            if m_hierarchy:
                manager_manager_id = m_hierarchy[0].get('ManagerID')
        except Exception:
            pass

    hr_users = []
    sa_users = []
    try:
        all_users = UsersTable.scan()
        for u in all_users:
            u_org_id = u.get('OrgID')
            if not org_id or u_org_id == org_id:
                if u.get('Role') == 'HR ADMIN' and u.get('EmployeeID'):
                    hr_users.append(u.get('EmployeeID'))
                elif u.get('Role') == 'Super admin' and u.get('EmployeeID'):
                    sa_users.append(u.get('EmployeeID'))
    except Exception:
        pass
    
    fallback_hr_id = hr_users[0] if hr_users else (sa_users[0] if sa_users else None)
    fallback_sa_id = sa_users[0] if sa_users else (hr_users[0] if hr_users else None)

    def get_approver_by_role_name(role_name):
        if role_name == 'Manager':
            return manager_id or fallback_hr_id
        elif role_name == 'Team Lead':
            return manager_id or fallback_hr_id # Fallback to manager
        elif role_name == 'HR ADMIN':
            return fallback_hr_id
        elif role_name == 'Super admin':
            return fallback_sa_id
        return fallback_hr_id

    # 4. Handle rejection
    if action == 'reject':
        return 'Rejected', None, False

    # 5. Handle submission or progression
    # Status format: 'Pending [Role Name] Approval'
    # E.g. 'Pending Manager Approval'
    
    # Map current status to step index in chain
    current_step_index = -1
    if current_status:
        # Find which role name matches current status
        for idx, role_name in enumerate(chain):
            if current_status == f"Pending {role_name} Approval":
                current_step_index = idx
                break

    if action == 'submit' or not current_status:
        next_role = chain[0]
        status = f"Pending {next_role} Approval"
        approver = get_approver_by_role_name(next_role)
        return status, approver, False

    elif action == 'approve':
        next_step_index = current_step_index + 1
        if next_step_index < len(chain):
            next_role = chain[next_step_index]
            status = f"Pending {next_role} Approval"
            approver = get_approver_by_role_name(next_role)
            return status, approver, False
        else:
            return 'Approved', None, True

    return 'Approved', None, True




