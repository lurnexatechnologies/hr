import datetime
from core.dynamodb_service import EmployeesTable, NotificationsTable, HolidaysTable
from boto3.dynamodb.conditions import Key

def lurnexa_settings(request):
    from core.utils import is_mobile_app
    # Initialize default data
    data = {
        'LURNEXA_VERSION': '1.0.0',
        'is_birthday_today': False,
        'today_birthdays': [],
        'tomorrow_birthdays': [],
        'global_notifications': [],
        'unread_notifications_count': 0,
        'user_gender': None,
        'IS_MOBILE_APP': is_mobile_app(request)
    }

    # Only fetch birthdays if user is logged in
    if request.user.is_authenticated:
        try:
            today = datetime.date.today()
            today_str = today.strftime('%m-%d')
            tomorrow = today + datetime.timedelta(days=1)
            tomorrow_str = tomorrow.strftime('%m-%d')
            
            user_emp_id = getattr(request.user, 'employee_id', None)
            
            # Check if user has cleared notifications in this session
            notifications_dismissed = request.session.get('notifications_dismissed', False)
            
            # Fetch all employees to check birthdays
            all_employees = EmployeesTable.scan()
            
            for emp in all_employees:
                dob = emp.get('DOB')
                if dob and len(dob) >= 10:
                    dob_md = dob[5:10] # Extracts MM-DD from YYYY-MM-DD
                    
                    if dob_md == today_str:
                        data['today_birthdays'].append(emp)
                        # Check if it's the current user's birthday for the theme
                        if emp.get('EmployeeID') == user_emp_id:
                            data['is_birthday_today'] = True
                            data['user_gender'] = emp.get('Gender')
                            
                    elif dob_md == tomorrow_str:
                        data['tomorrow_birthdays'].append(emp)

            # Add Birthday notifications dynamically for everyone EXCEPT the birthday person (to avoid duplicate alerts for them)
            if not notifications_dismissed:
                for bday in data['today_birthdays']:
                    if bday.get('EmployeeID') != user_emp_id:
                        data['global_notifications'].append({
                            'Title': 'Birthday Celebration!',
                            'Message': f"Today is {bday.get('FirstName')}'s birthday! 🎉",
                            'Timestamp': 'Just Now',
                            'Icon': 'fa-cake-candles',
                            'Color': 'danger'
                        })
        except Exception as e:
            print(f"Error in birthday context processor: {e}")

        # --- Holiday Reminder (One Day Before) ---
        try:
            tomorrow_full_str = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
            # Scan holidays to find if any is for tomorrow
            all_holidays = HolidaysTable.scan()
            tomorrow_holiday = next((h for h in all_holidays if h.get('HolidayDate') == tomorrow_full_str), None)
            
            if tomorrow_holiday:
                h_name = tomorrow_holiday.get('Name')
                # Use session to ensure we only trigger the DB notification once per day/session
                session_key = f"notified_holiday_{tomorrow_full_str}"
                if not request.session.get(session_key):
                    from core.utils import send_notification
                    send_notification(
                        employee_id=user_emp_id,
                        title="Holiday Tomorrow! 🏖️",
                        message=f"Reminder: Tomorrow ({tomorrow_full_str}) is a holiday for {h_name}.",
                        n_type='Holiday',
                        icon='fa-calendar-day',
                        color='info'
                    )
                    request.session[session_key] = True
        except Exception as e:
            print(f"Error in holiday reminder check: {e}")

        # --- Real Notifications ---
        try:
            if user_emp_id:
                notifications = NotificationsTable.query(
                    KeyConditionExpression=Key('EmployeeID').eq(user_emp_id),
                    ScanIndexForward=False, # Newest first
                    Limit=5
                )
                # Merge DB notifications with dynamic ones
                data['global_notifications'].extend(notifications)
                # Sort by timestamp (optional, but keep dynamic ones at top for now or just take latest 5)
                data['global_notifications'] = data['global_notifications'][:10]
                
                # Unread count (requires a full scan or separate counter in production, 
                # but for this dev app we'll scan the recent ones or just use a small limit)
                # Actually, let's just query all unread for the count
                # Since we don't have a GSI on IsRead, we scan with FilterExpression
                all_unread = NotificationsTable.query(
                    KeyConditionExpression=Key('EmployeeID').eq(user_emp_id),
                    FilterExpression="#r = :val",
                    ExpressionAttributeNames={'#r': 'IsRead'},
                    ExpressionAttributeValues={':val': False}
                )
                data['unread_notifications_count'] = len(all_unread)
                
                # --- Pending Approvals Counts ---
                try:
                    from core.dynamodb_service import LeaveRequestsTable, ExpensesTable, WFHRequestsTable, ResignationsTable, PayrollApprovalsTable, ReportingHierarchyTable
                    user_role = getattr(request.user, 'role', None)
                    
                    # Pending Certificates (HR ADMIN only)
                    if user_role == 'HR ADMIN':
                        pending_certs_count = 0
                        pending_onboarding_count = 0
                        for emp in all_employees:
                            certs = emp.get('Certificates', [])
                            if isinstance(certs, list):
                                pending_certs_count += sum(1 for c in certs if isinstance(c, dict) and c.get('Status') == 'Pending')
                            
                            if emp.get('OnboardingStatus') == 'Pending Review':
                                pending_onboarding_count += 1
                                
                        data['pending_certificates_count'] = pending_certs_count
                        data['pending_onboarding_count'] = pending_onboarding_count

                    # Get reportees for Manager
                    my_reportees = []
                    if user_role == 'Manager':
                        hierarchy = ReportingHierarchyTable.scan(
                            FilterExpression="ManagerID = :mid",
                            ExpressionAttributeValues={":mid": user_emp_id}
                        )
                        my_reportees = [h.get('EmployeeID') for h in hierarchy]

                    # Pending Leaves (Uses 'Pending' status)
                    if user_role in ['Manager', 'HR ADMIN', 'Super admin']:
                        all_leaves = LeaveRequestsTable.scan()
                        count_l = 0
                        for l in all_leaves:
                            if l.get('Status') == 'Pending':
                                if user_role in ['HR ADMIN', 'Super admin'] and (not l.get('ApproverID') or l.get('ApproverID') == user_emp_id):
                                    count_l += 1
                                elif user_role == 'Manager' and l.get('EmployeeID') in my_reportees:
                                    count_l += 1
                        data['pending_leaves_count'] = count_l
                        
                    # Pending Expenses
                    if user_role in ['Manager', 'HR ADMIN', 'Super admin']:
                        all_expenses = ExpensesTable.scan()
                        count_e = 0
                        for exp in all_expenses:
                            status = exp.get('Status')
                            if user_role == 'Super admin':
                                if exp.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                                    count_e += 1
                            elif user_role == 'HR ADMIN':
                                if status in ['Manager Approved', 'Pending HR ADMIN Approval']:
                                    count_e += 1
                                elif exp.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                                    count_e += 1
                            elif user_role == 'Manager':
                                if exp.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                                    count_e += 1
                        data['pending_expenses_count'] = count_e
                        
                    # Pending WFH
                    if user_role in ['Manager', 'HR ADMIN', 'Super admin']:
                        all_wfh = WFHRequestsTable.scan()
                        count_w = 0
                        for w in all_wfh:
                            status = w.get('Status')
                            if user_role == 'Super admin':
                                if w.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                                    count_w += 1
                            elif user_role == 'HR ADMIN':
                                if status == 'Pending HR ADMIN Approval':
                                    count_w += 1
                                elif w.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                                    count_w += 1
                            elif user_role == 'Manager':
                                if w.get('ApproverID') == user_emp_id and status == 'Pending Manager Approval':
                                    count_w += 1
                        data['pending_wfh_count'] = count_w
                        
                    # Pending Resignations (Uses 'Pending HR ADMIN Review')
                    if user_role in ['HR ADMIN', 'Super admin']:
                        from core.dynamodb_service import UsersTable
                        all_res = ResignationsTable.scan()
                        all_users = UsersTable.scan()
                        user_role_map = {u.get('EmployeeID'): u.get('Role') for u in all_users if u.get('EmployeeID')}
                        
                        count_r = 0
                        for r in all_res:
                            if r.get('Status') == 'Pending HR ADMIN Review':
                                r_role = user_role_map.get(r.get('EmployeeID'))
                                if user_role == 'Super admin' and r_role == 'HR ADMIN':
                                    count_r += 1
                                elif user_role == 'HR ADMIN' and r_role not in ['HR ADMIN', 'Super admin']:
                                    count_r += 1
                        data['pending_resignations_count'] = count_r
                        
                    # Pending Payroll Approvals
                    if user_role == 'Super admin':
                        all_pay = PayrollApprovalsTable.scan()
                        count_p = sum(1 for p in all_pay if p.get('Status') == 'Pending')
                        data['pending_payroll_count'] = count_p

                except Exception as e:
                    print(f"Error fetching pending approval counts: {e}")

        except Exception as e:
            print(f"Error fetching real notifications: {e}")

    return data
