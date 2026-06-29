import os
import datetime
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.mail import EmailMessage
import threading
from core.dynamodb_service import EmployeesTable, NotificationsTable

def send_notification(employee_id, title, message, n_type='System', icon='fa-bell', color='primary', email_subject=None, email_body=None, attachments=None):
    """
    Sends a notification to an employee. 
    Saves to DynamoDB and optionally sends an email in a background thread.
    """
    
    timestamp = datetime.datetime.now().isoformat()
    
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
    try:
        NotificationsTable.put_item(notification_item)
    except Exception as e:
        print(f"Error saving notification: {e}")

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
    Prorated from joining month to December of the joining year for new employees.
    If joined in a previous year, gets the full 12.0 days.
    Interns get 0.0.
    """
    if employee.get('EmploymentType') == 'Intern':
        return 0.0

    if leave_type not in ['SL', 'CL']:
        return 0.0

    joined_date_str = employee.get('JoinedDate')
    if not joined_date_str:
        return 12.0

    try:
        joined_date = datetime.datetime.strptime(joined_date_str, '%Y-%m-%d').date()
        today = datetime.date.today()
        
        if joined_date.year < today.year:
            # Joined in a previous year, gets full 12.0 days
            return 12.0
        else:
            # Joined in the current year (or future), prorate from joining month to December
            months_count = 12 - joined_date.month + 1
            return float(max(1, min(12, months_count)))
    except Exception as e:
        print(f"Error calculating initial leave: {e}")
        return 12.0

def refresh_monthly_leaves(employee):
    """
    Refreshes leave balances (SL, CL) on the 1st day of the month.
    - On Jan 1st, resets SL and CL to 12.0 (previous year's balance disappears).
    - On every month's 1st day, accrues Earned Leave (EL) based on last month's working days / 20.
    """
    today = datetime.date.today()
    if today.day != 1:
        return False # Only on the 1st

    # Interns do not accrue paid/earned leaves
    if employee.get('EmploymentType') == 'Intern':
        return False

    # Inactive or resigned (ex-employees) should not have their leaves updated
    if not employee.get('IsActive', True):
        return False

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
            # Reset CL and SL to 12.0 on Jan 1st, and update EL
            EmployeesTable.update_item(
                Key={'EmployeeID': emp_id},
                UpdateExpression="SET Balance_SL = :sl, Balance_CL = :cl, Balance_PL = :pl, LastLeaveRefresh = :lr",
                ExpressionAttributeValues={
                    ':sl': '12.0',
                    ':cl': '12.0',
                    ':pl': str(new_el),
                    ':lr': current_month
                }
            )
            print(f"Leave balances reset to 12.0 (SL/CL) and EL accrued (+{accrued_el}) on Jan 1st for {emp_id}")
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

def save_uploaded_file(uploaded_file, folder='uploads'):
    """
    Saves an uploaded file to the MEDIA_ROOT/folder directory.
    Returns the filename of the saved file.
    """
    if not uploaded_file:
        return None
        
    fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, folder))
    filename = fs.save(uploaded_file.name, uploaded_file)
    # Return the relative path from MEDIA_ROOT
    return os.path.join(folder, filename).replace('\\', '/')


def apply_pending_hikes():
    from core.dynamodb_service import EmployeesTable, EmployeeLettersTable
    import datetime
    try:
        today = datetime.date.today().isoformat()
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
    Returns the base64 encoded data URI of the namelesslogolurnexa.png file.
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


