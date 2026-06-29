import datetime
from decimal import Decimal
from importlib import import_module
from django.conf import settings
from django.test import TestCase, Client
from django.contrib.messages import get_messages
from core.dynamodb_service import (
    UsersTable, EmployeesTable, LeaveRequestsTable, ResignationsTable, HolidaysTable,
    OnboardingTokensTable, ReportingHierarchyTable, ExpensesTable, WFHRequestsTable, AttendanceTable
)

class BusinessLogicTestSuite(TestCase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.messages_list = []
        self.to_cleanup = []
        self.engine = import_module(settings.SESSION_ENGINE)

    def tearDown(self):
        # Restore modified or created objects
        for table, key, orig_item in self.to_cleanup:
            try:
                if orig_item is None:
                    table.delete_item(key=key)
                else:
                    table.put_item(item=orig_item)
            except Exception as e:
                pass
        super().tearDown()

    def track_cleanup(self, table, key):
        try:
            orig = table.get_item(key=key)
        except Exception:
            orig = None
        self.to_cleanup.append((table, key, orig))

    def set_session_data(self, data):
        store = self.engine.SessionStore()
        for k, v in data.items():
            store[k] = v
        store.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = store.session_key
        return store

    def get_msg_texts(self, response):
        return [m.message for m in get_messages(response.wsgi_request)]

    # --- PHASE 2: AUTH & SECURITY ---
    def test_01_deactivated_user_cannot_login(self):
        """Test that a deactivated user cannot log in and gets error message."""
        temp_user_id = 'test-deact-user-id'
        temp_email = 'deact-test@lurnexa.com'
        
        self.track_cleanup(UsersTable, {'UserID': temp_user_id})
        
        import bcrypt
        hashed_pw = bcrypt.hashpw(b'Password@123', bcrypt.gensalt()).decode('utf-8')
        UsersTable.put_item(item={
            'UserID': temp_user_id,
            'Email': temp_email,
            'Role': 'Employee',
            'PasswordHash': hashed_pw,
            'IsActive': False,
            'EmployeeID': 'LT-TEMP-001'
        })
        
        response = self.client.post('/auth/login/', {
            'username': temp_email,
            'password': 'Password@123'
        }, follow=True)
        messages = self.get_msg_texts(response)
        self.assertTrue(any("deactivated" in m.lower() for m in messages), f"Messages: {messages}")

    def test_02_last_working_day_check(self):
        """Test that past last working day user login is auto-deactivated and blocked."""
        temp_user_id = 'test-lwd-user-id'
        temp_email = 'lwd-test@lurnexa.com'
        temp_emp_id = 'LT-LWD-001'
        
        self.track_cleanup(UsersTable, {'UserID': temp_user_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': temp_emp_id})
        
        import bcrypt
        hashed_pw = bcrypt.hashpw(b'Password@123', bcrypt.gensalt()).decode('utf-8')
        
        UsersTable.put_item(item={
            'UserID': temp_user_id,
            'Email': temp_email,
            'Role': 'Employee',
            'PasswordHash': hashed_pw,
            'IsActive': True,
            'EmployeeID': temp_emp_id
        })
        
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        EmployeesTable.put_item(item={
            'EmployeeID': temp_emp_id,
            'UserID': temp_user_id,
            'Email': temp_email,
            'FirstName': 'LWD',
            'LastName': 'Tester',
            'LastWorkingDate': yesterday
        })
        
        response = self.client.post('/auth/login/', {
            'username': temp_email,
            'password': 'Password@123'
        }, follow=True)
        
        messages = self.get_msg_texts(response)
        self.assertTrue(any("expired" in m.lower() or "last working day" in m.lower() for m in messages), f"Messages: {messages}")
        
        user_record = UsersTable.get_item(key={'UserID': temp_user_id})
        emp_record = EmployeesTable.get_item(key={'EmployeeID': temp_emp_id})
        self.assertFalse(user_record.get('IsActive'))
        self.assertFalse(emp_record.get('IsActive'))

    # --- PHASE 3: ROLE-BASED ACCESS CONTROLS (RBAC) ---
    def test_03_employee_role_rbac_restrictions(self):
        """Test Employee role access controls for restricted paths."""
        emp_user = next((u for u in UsersTable.scan() if u.get('Role') == 'Employee' and u.get('IsActive')), None)
        if not emp_user:
            self.skipTest("No active employee user in database to run RBAC tests.")
            
        self.set_session_data({'user_id': emp_user['UserID']})
        
        paths_to_test = [
            ('/core/hr_dashboard/', 302),
            ('/leave/approvals/', 302),
            ('/payroll/manage/', 302),
            ('/workflows/resignation/approvals/', 302)
        ]
        
        for path, expected_status in paths_to_test:
            response = self.client.get(path)
            self.assertEqual(response.status_code, expected_status, f"Path {path} did not redirect (status {response.status_code})")

    def test_04_manager_role_rbac_restrictions(self):
        """Test Manager role access controls for restricted paths."""
        mgr_user = next((u for u in UsersTable.scan() if u.get('Role') == 'Manager' and u.get('IsActive')), None)
        if not mgr_user:
            self.skipTest("No active Manager user in database to run RBAC tests.")
            
        self.set_session_data({'user_id': mgr_user['UserID']})
        
        paths_to_test = [
            ('/payroll/manage/', 302),
            ('/employees/add/', 302),
            ('/core/super_admin_dashboard/', 302)
        ]
        
        for path, expected_status in paths_to_test:
            response = self.client.get(path)
            self.assertEqual(response.status_code, expected_status, f"Path {path} did not redirect (status {response.status_code})")

    # --- PHASE 5: EMPLOYEE MANAGEMENT & RESIGNATION ---
    def test_05_resignation_tenure_check(self):
        """Test that resignation is blocked if employee tenure is < 60 days."""
        temp_user_id = 'res-tenure-user-id'
        temp_email = 'res-tenure-test@lurnexa.com'
        temp_emp_id = 'LT-TEN-001'
        
        self.track_cleanup(UsersTable, {'UserID': temp_user_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': temp_emp_id})
        self.track_cleanup(ResignationsTable, {'EmployeeID': temp_emp_id})
        
        ten_days_ago = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
        
        UsersTable.put_item(item={
            'UserID': temp_user_id,
            'Email': temp_email,
            'Role': 'Employee',
            'IsActive': True,
            'EmployeeID': temp_emp_id
        })
        EmployeesTable.put_item(item={
            'EmployeeID': temp_emp_id,
            'UserID': temp_user_id,
            'Email': temp_email,
            'FirstName': 'Tenure',
            'LastName': 'Tester',
            'JoinedDate': ten_days_ago,
            'OnboardingStatus': 'Approved',
            'IsActive': True
        })
        
        self.set_session_data({'user_id': temp_user_id})
        
        lwd_val = (datetime.date.today() + datetime.timedelta(days=60)).isoformat()
        response = self.client.post('/workflows/resignation/', {
            'reason': 'Better opportunities',
            'lwd': lwd_val,
            'comments': 'Short tenure test'
        }, follow=True)
        
        messages = self.get_msg_texts(response)
        self.assertTrue(any("after 60 days of service only" in m.lower() for m in messages), f"Messages: {messages}")
        
        res_record = ResignationsTable.get_item(key={'EmployeeID': temp_emp_id})
        self.assertIsNone(res_record)

    def test_06_resignation_cooling_off_period(self):
        """Test resignation cooling off period (blocked if rejected < 3 days ago)."""
        temp_user_id = 'res-cool-user-id'
        temp_email = 'res-cool-test@lurnexa.com'
        temp_emp_id = 'LT-COOL-001'
        
        self.track_cleanup(UsersTable, {'UserID': temp_user_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': temp_emp_id})
        self.track_cleanup(ResignationsTable, {'EmployeeID': temp_emp_id})
        
        long_ago = (datetime.date.today() - datetime.timedelta(days=100)).isoformat()
        yesterday_iso = (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat()
        
        UsersTable.put_item(item={
            'UserID': temp_user_id,
            'Email': temp_email,
            'Role': 'Employee',
            'IsActive': True,
            'EmployeeID': temp_emp_id
        })
        EmployeesTable.put_item(item={
            'EmployeeID': temp_emp_id,
            'UserID': temp_user_id,
            'Email': temp_email,
            'FirstName': 'Cool',
            'LastName': 'Tester',
            'JoinedDate': long_ago,
            'OnboardingStatus': 'Approved',
            'IsActive': True
        })
        
        ResignationsTable.put_item(item={
            'EmployeeID': temp_emp_id,
            'Status': 'Rejected',
            'RejectedOn': yesterday_iso,
            'LastWorkingDay': (datetime.date.today() + datetime.timedelta(days=60)).isoformat()
        })
        
        self.set_session_data({'user_id': temp_user_id})
        
        lwd_val = (datetime.date.today() + datetime.timedelta(days=60)).isoformat()
        response = self.client.post('/workflows/resignation/', {
            'reason': 'Better opportunities 2',
            'lwd': lwd_val,
            'comments': 'Cooling off test'
        }, follow=True)
        
        messages = self.get_msg_texts(response)
        self.assertTrue(any("cooling off" in m.lower() or "apply again in" in m.lower() or "rejected. you can apply" in m.lower() for m in messages), f"Messages: {messages}")

    # --- PHASE 6: LEAVE MANAGEMENT ---
    def test_07_intern_leave_restriction(self):
        """Test that Interns can only apply for Unpaid Leave."""
        temp_user_id = 'leave-intern-user'
        temp_email = 'leave-intern@lurnexa.com'
        temp_emp_id = 'LT-LEAVE-INT'
        
        self.track_cleanup(UsersTable, {'UserID': temp_user_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': temp_emp_id})
        self.track_cleanup(LeaveRequestsTable, {'EmployeeID': temp_emp_id, 'LeaveDate': '2026-06-01'})
        
        UsersTable.put_item(item={
            'UserID': temp_user_id,
            'Email': temp_email,
            'Role': 'Employee',
            'IsActive': True,
            'EmployeeID': temp_emp_id
        })
        EmployeesTable.put_item(item={
            'EmployeeID': temp_emp_id,
            'UserID': temp_user_id,
            'Email': temp_email,
            'FirstName': 'Intern',
            'LastName': 'Tester',
            'EmploymentType': 'Intern',
            'OnboardingStatus': 'Approved',
            'IsActive': True
        })
        
        self.set_session_data({'user_id': temp_user_id})
        
        response = self.client.post('/leave/apply/', {
            'leave_type': 'Earned Leave (PL)',
            'start_date': '2026-06-01',
            'end_date': '2026-06-02',
            'reason': 'Vacation'
        }, follow=True)
        
        messages = self.get_msg_texts(response)
        self.assertTrue(any("only apply for unpaid leave" in m.lower() for m in messages), f"Messages: {messages}")
        
        response2 = self.client.post('/leave/apply/', {
            'leave_type': 'Unpaid Leave',
            'start_date': '2026-06-01',
            'end_date': '2026-06-02',
            'reason': 'Personal'
        }, follow=True)
        self.assertEqual(response2.status_code, 200)
        self.assertIn('history', response2.wsgi_request.path)

    def test_08_leave_weekend_and_holiday_validations(self):
        """Test leave start/end date weekend and holiday validations."""
        temp_user_id = 'leave-wk-user'
        temp_email = 'leave-wk@lurnexa.com'
        temp_emp_id = 'LT-LEAVE-WK'
        
        self.track_cleanup(UsersTable, {'UserID': temp_user_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': temp_emp_id})
        self.track_cleanup(HolidaysTable, {'HolidayID': 'test-h-id'})
        
        UsersTable.put_item(item={
            'UserID': temp_user_id,
            'Email': temp_email,
            'Role': 'Employee',
            'IsActive': True,
            'EmployeeID': temp_emp_id
        })
        EmployeesTable.put_item(item={
            'EmployeeID': temp_emp_id,
            'UserID': temp_user_id,
            'Email': temp_email,
            'FirstName': 'LeaveDate',
            'LastName': 'Tester',
            'EmploymentType': 'Permanent',
            'Balance_SL': '10.0',
            'OnboardingStatus': 'Approved',
            'IsActive': True
        })
        
        self.set_session_data({'user_id': temp_user_id})
        
        # 1. Start date on weekend (2026-05-30 is a Saturday)
        response = self.client.post('/leave/apply/', {
            'leave_type': 'Sick Leave (SL)',
            'start_date': '2026-05-30',
            'end_date': '2026-06-01',
            'reason': 'Sick'
        }, follow=True)
        messages = self.get_msg_texts(response)
        self.assertTrue(any("weekend" in m.lower() for m in messages), f"Messages: {messages}")
        
        # 2. Start date on public holiday
        HolidaysTable.put_item(item={
            'HolidayID': 'test-h-id',
            'HolidayDate': '2026-06-03',
            'Name': 'Test Holiday',
            'Type': 'National'
        })
        
        response2 = self.client.post('/leave/apply/', {
            'leave_type': 'Sick Leave (SL)',
            'start_date': '2026-06-03',
            'end_date': '2026-06-04',
            'reason': 'Sick'
        }, follow=True)
        messages2 = self.get_msg_texts(response2)
        self.assertTrue(any("public holiday" in m.lower() or "holiday" in m.lower() for m in messages2), f"Messages: {messages2}")

    # --- PHASE 9: PAYROLL ---
    def test_09_payroll_generation_date_restriction(self):
        """Test that payroll run can only be processed on the 30th of the month."""
        hr_user = next((u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN' and u.get('IsActive')), None)
        if not hr_user:
            self.skipTest("No active HR Admin user to test payroll submission.")
            
        self.set_session_data({
            'user_id': hr_user['UserID'],
            'payroll_authenticated': True
        })
        
        today = datetime.date.today()
        response = self.client.post('/payroll/manage/', {
            'selected_employees': ['LT-26004']
        }, follow=True)
        
        messages = self.get_msg_texts(response)
        if today.day != 30:
            self.assertTrue(any("failed" in m.lower() or "30th of the month" in m.lower() for m in messages), f"Messages: {messages}")

    # --- PHASE 10: PF & STATUTORY ---
    def test_10_pf_details_validation(self):
        """Test PF details validation rules (PF exactly 22 alphanumeric, UAN exactly 12 digits)."""
        hr_user = next((u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN' and u.get('IsActive')), None)
        if not hr_user:
            self.skipTest("No active HR Admin user to test PF details update.")
            
        self.set_session_data({'user_id': hr_user['UserID']})
        
        emp_id = 'LT-26007'
        
        # 1. Invalid PF Number format (e.g. too short or containing symbols)
        response = self.client.post(f'/payroll/pf/update-details/{emp_id}/', {
            'pf_number': 'SHORT123',
            'uan_number': '123456789012'
        }, follow=True)
        messages = self.get_msg_texts(response)
        self.assertTrue(any("invalid pf number" in m.lower() for m in messages), f"Messages: {messages}")
        
        # 2. Invalid UAN Number format (e.g. non-numeric or too long)
        response2 = self.client.post(f'/payroll/pf/update-details/{emp_id}/', {
            'pf_number': 'MHBAN12345678901234567',
            'uan_number': '12345ABC9012'
        }, follow=True)
        messages2 = self.get_msg_texts(response2)
        self.assertTrue(any("invalid uan number" in m.lower() for m in messages2), f"Messages: {messages2}")

    # --- PHASE 11: APPROVALS & WORKFLOWS (ONBOARDING, LEAVE, EXPENSE, WFH, CERTIFICATE, RESIGNATION) ---
    def test_11_onboarding_approval_workflow(self):
        """Test onboarding token creation, self-onboarding submission, and HR approval."""
        import random
        rand_suffix = str(random.randint(100000, 999999))
        token = f'onb-token-11-{rand_suffix}'
        temp_emp_id = f'LT-ONB-11-{rand_suffix}'
        temp_email = f'onb-new-{rand_suffix}@lurnexa.com'
        temp_user_id = f'onb-user-11-{rand_suffix}'
        aadhar_num = '123412341234'
        phone_num = '9' + str(random.randint(100000000, 999999999))

        self.track_cleanup(OnboardingTokensTable, {'Token': token})
        self.track_cleanup(EmployeesTable, {'EmployeeID': temp_emp_id})
        self.track_cleanup(UsersTable, {'UserID': temp_user_id})

        OnboardingTokensTable.put_item(item={
            'Token': token,
            'CreatedAt': datetime.datetime.now().isoformat(),
            'TargetEmail': temp_email,
            'EmployeeID': temp_emp_id,
            'Role': 'Employee',
            'Used': False
        })

        # Complete Self Onboarding (Simulate POST request)
        response = self.client.post(f'/employees/self-onboarding/{token}/', {
            'email': temp_email,
            'first_name': 'NewOnb',
            'last_name': 'Employee',
            'dob': '1995-05-15',
            'gender': 'Male',
            'aadhar_number': aadhar_num,
            'pan_number': 'ABCDE1234F',
            'password': 'Password@123',
            'confirm_password': 'Password@123',
            'phone': phone_num
        }, follow=True)
        
        # Verify onboarding status is Pending Review
        emp_record = EmployeesTable.get_item(key={'EmployeeID': temp_emp_id})
        if emp_record is None:
            print("TESTING DEBUG - MESSAGES:", self.get_msg_texts(response))
        self.assertIsNotNone(emp_record)
        self.assertEqual(emp_record.get('OnboardingStatus'), 'Pending Review')

        # Now approve onboarding
        hr_user = next((u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN' and u.get('IsActive')), None)
        self.assertIsNotNone(hr_user)
        self.set_session_data({'user_id': hr_user['UserID']})

        # HR approves
        self.client.post(f'/employees/approve-onboarding/{temp_emp_id}/', {
            'action': 'approve',
            'doc_statuses': '{}'
        }, follow=True)

        emp_record_final = EmployeesTable.get_item(key={'EmployeeID': temp_emp_id})
        self.assertEqual(emp_record_final.get('OnboardingStatus'), 'Approved')

    def test_12_onboarding_rejection_workflow(self):
        """Test HR onboarding rejection."""
        import random
        rand_suffix = str(random.randint(100000, 999999))
        token = f'onb-token-12-{rand_suffix}'
        temp_emp_id = f'LT-ONB-12-{rand_suffix}'
        temp_email = f'onb-rej-{rand_suffix}@lurnexa.com'
        temp_user_id = f'onb-user-12-{rand_suffix}'
        aadhar_num = '123412341234'
        phone_num = '9' + str(random.randint(100000000, 999999999))

        self.track_cleanup(OnboardingTokensTable, {'Token': token})
        self.track_cleanup(EmployeesTable, {'EmployeeID': temp_emp_id})
        self.track_cleanup(UsersTable, {'UserID': temp_user_id})

        OnboardingTokensTable.put_item(item={
            'Token': token,
            'CreatedAt': datetime.datetime.now().isoformat(),
            'TargetEmail': temp_email,
            'EmployeeID': temp_emp_id,
            'Role': 'Employee',
            'Used': False
        })

        # Complete Self Onboarding
        self.client.post(f'/employees/self-onboarding/{token}/', {
            'email': temp_email,
            'first_name': 'RejOnb',
            'last_name': 'Employee',
            'dob': '1995-05-15',
            'gender': 'Male',
            'aadhar_number': aadhar_num,
            'pan_number': 'ABCDE1234G',
            'password': 'Password@123',
            'confirm_password': 'Password@123',
            'phone': phone_num
        }, follow=True)

        hr_user = next((u for u in UsersTable.scan() if u.get('Role') == 'HR ADMIN' and u.get('IsActive')), None)
        self.set_session_data({'user_id': hr_user['UserID']})

        # HR rejects
        self.client.post(f'/employees/approve-onboarding/{temp_emp_id}/', {
            'action': 'reject',
            'reason': 'Incorrect PAN Card format',
            'doc_statuses': '{}'
        }, follow=True)

        emp_record = EmployeesTable.get_item(key={'EmployeeID': temp_emp_id})
        self.assertEqual(emp_record.get('OnboardingStatus'), 'Rejected')

    def test_13_leave_approval_manager_isolation(self):
        """Test that leave request is only visible to the specific manager and updates balance upon approval."""
        mgr_m_id = 'MGR-M-001'
        mgr_n_id = 'MGR-N-001'
        emp_a_id = 'EMP-A-001'
        emp_b_id = 'EMP-B-001'
        
        user_m_id = 'u-mgr-m'
        user_n_id = 'u-mgr-n'
        user_a_id = 'u-emp-a'
        
        self.track_cleanup(EmployeesTable, {'EmployeeID': mgr_m_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': mgr_n_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': emp_a_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': emp_b_id})
        self.track_cleanup(UsersTable, {'UserID': user_m_id})
        self.track_cleanup(UsersTable, {'UserID': user_n_id})
        self.track_cleanup(UsersTable, {'UserID': user_a_id})
        self.track_cleanup(ReportingHierarchyTable, {'ManagerID': mgr_m_id, 'EmployeeID': emp_a_id})
        self.track_cleanup(ReportingHierarchyTable, {'ManagerID': mgr_n_id, 'EmployeeID': emp_b_id})
        self.track_cleanup(LeaveRequestsTable, {'EmployeeID': emp_a_id, 'LeaveDate': '2026-08-03'})
        
        # Setup Hierarchy & Employees
        EmployeesTable.put_item(item={'EmployeeID': mgr_m_id, 'FirstName': 'Manager', 'LastName': 'M', 'OnboardingStatus': 'Approved', 'IsActive': True})
        EmployeesTable.put_item(item={'EmployeeID': mgr_n_id, 'FirstName': 'Manager', 'LastName': 'N', 'OnboardingStatus': 'Approved', 'IsActive': True})
        EmployeesTable.put_item(item={'EmployeeID': emp_a_id, 'FirstName': 'Employee', 'LastName': 'A', 'OnboardingStatus': 'Approved', 'IsActive': True, 'Balance_SL': '10.0'})
        EmployeesTable.put_item(item={'EmployeeID': emp_b_id, 'FirstName': 'Employee', 'LastName': 'B', 'OnboardingStatus': 'Approved', 'IsActive': True})
        
        UsersTable.put_item(item={'UserID': user_m_id, 'Email': 'mgr-m@lurnexa.com', 'Role': 'Manager', 'EmployeeID': mgr_m_id, 'IsActive': True})
        UsersTable.put_item(item={'UserID': user_n_id, 'Email': 'mgr-n@lurnexa.com', 'Role': 'Manager', 'EmployeeID': mgr_n_id, 'IsActive': True})
        UsersTable.put_item(item={'UserID': user_a_id, 'Email': 'emp-a@lurnexa.com', 'Role': 'Employee', 'EmployeeID': emp_a_id, 'IsActive': True})
        
        ReportingHierarchyTable.put_item(item={'ManagerID': mgr_m_id, 'EmployeeID': emp_a_id})
        ReportingHierarchyTable.put_item(item={'ManagerID': mgr_n_id, 'EmployeeID': emp_b_id})

        # Employee A applies for leave
        self.set_session_data({'user_id': user_a_id})
        self.client.post('/leave/apply/', {
            'leave_type': 'Sick Leave (SL)',
            'start_date': '2026-08-03',
            'end_date': '2026-08-03',
            'reason': 'Fever'
        }, follow=True)

        # Manager M logs in. Verify leave is in pending list.
        self.set_session_data({'user_id': user_m_id})
        resp_m = self.client.get('/leave/approvals/')
        pending_m = resp_m.context['pending_leaves']
        self.assertTrue(any(l.get('EmployeeID') == emp_a_id for l in pending_m))

        # Manager N logs in. Verify leave is NOT in pending list.
        self.set_session_data({'user_id': user_n_id})
        resp_n = self.client.get('/leave/approvals/')
        pending_n = resp_n.context['pending_leaves']
        self.assertFalse(any(l.get('EmployeeID') == emp_a_id for l in pending_n))

        # Manager M approves the leave
        self.set_session_data({'user_id': user_m_id})
        self.client.get(f'/leave/approve/{emp_a_id}/2026-08-03/', follow=True)

        # Check balance and status
        emp_rec = EmployeesTable.get_item(key={'EmployeeID': emp_a_id})
        self.assertEqual(float(emp_rec.get('Balance_SL')), 9.0)
        leave_rec = LeaveRequestsTable.get_item(key={'EmployeeID': emp_a_id, 'LeaveDate': '2026-08-03'})
        self.assertEqual(leave_rec.get('Status'), 'Approved')

    def test_14_leave_rejection_workflow(self):
        """Test that leave request status updates to Rejected and balance remains unchanged."""
        mgr_m_id = 'MGR-M-001'
        emp_a_id = 'EMP-A-001'
        user_m_id = 'u-mgr-m'
        user_a_id = 'u-emp-a'
        
        self.track_cleanup(EmployeesTable, {'EmployeeID': mgr_m_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': emp_a_id})
        self.track_cleanup(UsersTable, {'UserID': user_m_id})
        self.track_cleanup(UsersTable, {'UserID': user_a_id})
        self.track_cleanup(ReportingHierarchyTable, {'ManagerID': mgr_m_id, 'EmployeeID': emp_a_id})
        self.track_cleanup(LeaveRequestsTable, {'EmployeeID': emp_a_id, 'LeaveDate': '2026-08-04'})

        EmployeesTable.put_item(item={'EmployeeID': mgr_m_id, 'FirstName': 'Manager', 'LastName': 'M', 'OnboardingStatus': 'Approved', 'IsActive': True})
        EmployeesTable.put_item(item={'EmployeeID': emp_a_id, 'FirstName': 'Employee', 'LastName': 'A', 'OnboardingStatus': 'Approved', 'IsActive': True, 'Balance_SL': '10.0'})
        UsersTable.put_item(item={'UserID': user_m_id, 'Email': 'mgr-m@lurnexa.com', 'Role': 'Manager', 'EmployeeID': mgr_m_id, 'IsActive': True})
        UsersTable.put_item(item={'UserID': user_a_id, 'Email': 'emp-a@lurnexa.com', 'Role': 'Employee', 'EmployeeID': emp_a_id, 'IsActive': True})
        ReportingHierarchyTable.put_item(item={'ManagerID': mgr_m_id, 'EmployeeID': emp_a_id})

        # Employee A applies for leave
        self.set_session_data({'user_id': user_a_id})
        self.client.post('/leave/apply/', {
            'leave_type': 'Sick Leave (SL)',
            'start_date': '2026-08-04',
            'end_date': '2026-08-04',
            'reason': 'Fever'
        }, follow=True)

        # Manager M rejects the leave
        self.set_session_data({'user_id': user_m_id})
        self.client.get(f'/leave/reject/{emp_a_id}/2026-08-04/', follow=True)

        # Check balance and status
        emp_rec = EmployeesTable.get_item(key={'EmployeeID': emp_a_id})
        self.assertEqual(float(emp_rec.get('Balance_SL')), 10.0)
        leave_rec = LeaveRequestsTable.get_item(key={'EmployeeID': emp_a_id, 'LeaveDate': '2026-08-04'})
        self.assertEqual(leave_rec.get('Status'), 'Rejected')

    def test_15_expense_approval_and_rejection(self):
        """Test expense submission, manager isolation, rejection, and final HR approval."""
        mgr_m_id = 'MGR-M-001'
        mgr_n_id = 'MGR-N-001'
        emp_a_id = 'EMP-A-001'
        user_m_id = 'u-mgr-m'
        user_n_id = 'u-mgr-n'
        user_a_id = 'u-emp-a'
        hr_user_id = 'u-hr-admin'
        hr_emp_id = 'LT-26002'

        self.track_cleanup(EmployeesTable, {'EmployeeID': mgr_m_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': mgr_n_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': emp_a_id})
        self.track_cleanup(UsersTable, {'UserID': user_m_id})
        self.track_cleanup(UsersTable, {'UserID': user_n_id})
        self.track_cleanup(UsersTable, {'UserID': user_a_id})
        self.track_cleanup(UsersTable, {'UserID': hr_user_id})
        self.track_cleanup(ReportingHierarchyTable, {'ManagerID': mgr_m_id, 'EmployeeID': emp_a_id})
        self.track_cleanup(ReportingHierarchyTable, {'ManagerID': mgr_n_id, 'EmployeeID': 'EMP-B-001'})
        
        EmployeesTable.put_item(item={'EmployeeID': mgr_m_id, 'FirstName': 'Manager', 'LastName': 'M', 'OnboardingStatus': 'Approved', 'IsActive': True})
        EmployeesTable.put_item(item={'EmployeeID': mgr_n_id, 'FirstName': 'Manager', 'LastName': 'N', 'OnboardingStatus': 'Approved', 'IsActive': True})
        EmployeesTable.put_item(item={'EmployeeID': emp_a_id, 'FirstName': 'Employee', 'LastName': 'A', 'OnboardingStatus': 'Approved', 'IsActive': True})
        
        UsersTable.put_item(item={'UserID': user_m_id, 'Email': 'mgr-m@lurnexa.com', 'Role': 'Manager', 'EmployeeID': mgr_m_id, 'IsActive': True})
        UsersTable.put_item(item={'UserID': user_n_id, 'Email': 'mgr-n@lurnexa.com', 'Role': 'Manager', 'EmployeeID': mgr_n_id, 'IsActive': True})
        UsersTable.put_item(item={'UserID': user_a_id, 'Email': 'emp-a@lurnexa.com', 'Role': 'Employee', 'EmployeeID': emp_a_id, 'IsActive': True})
        UsersTable.put_item(item={'UserID': hr_user_id, 'Email': 'hr-adm@lurnexa.com', 'Role': 'HR ADMIN', 'EmployeeID': hr_emp_id, 'IsActive': True})
        
        ReportingHierarchyTable.put_item(item={'ManagerID': mgr_m_id, 'EmployeeID': emp_a_id})

        # Submit expense
        self.set_session_data({'user_id': user_a_id})
        self.client.post('/workflows/expenses/', {
            'amount': '1500',
            'category': 'Travel',
            'description': 'Client meet'
        }, follow=True)

        expenses = ExpensesTable.scan()
        exp_item = next((e for e in expenses if e.get('EmployeeID') == emp_a_id), None)
        self.assertIsNotNone(exp_item)
        req_id = exp_item['RequestID']
        self.track_cleanup(ExpensesTable, {'EmployeeID': emp_a_id, 'RequestID': req_id})

        # Verify Manager M sees it, Manager N does not
        self.set_session_data({'user_id': user_m_id})
        resp_m = self.client.get('/workflows/expenses/approvals/')
        self.assertTrue(any(e.get('RequestID') == req_id for e in resp_m.context['pending_expenses']))

        self.set_session_data({'user_id': user_n_id})
        resp_n = self.client.get('/workflows/expenses/approvals/')
        self.assertFalse(any(e.get('RequestID') == req_id for e in resp_n.context['pending_expenses']))

        # Manager M rejects the expense
        self.set_session_data({'user_id': user_m_id})
        self.client.get(f'/workflows/expenses/reject/{emp_a_id}/{req_id}/', follow=True)
        
        exp_rec = ExpensesTable.get_item(key={'EmployeeID': emp_a_id, 'RequestID': req_id})
        self.assertEqual(exp_rec.get('Status'), 'Rejected')

        # Re-submit and approve
        self.set_session_data({'user_id': user_a_id})
        self.client.post('/workflows/expenses/', {
            'amount': '2500',
            'category': 'Food',
            'description': 'Team lunch'
        }, follow=True)

        expenses_2 = ExpensesTable.scan()
        exp_item_2 = next((e for e in expenses_2 if e.get('EmployeeID') == emp_a_id and e.get('RequestID') != req_id), None)
        self.assertIsNotNone(exp_item_2)
        req_id_2 = exp_item_2['RequestID']
        self.track_cleanup(ExpensesTable, {'EmployeeID': emp_a_id, 'RequestID': req_id_2})

        # Manager M approves -> Manager Approved status
        self.set_session_data({'user_id': user_m_id})
        self.client.get(f'/workflows/expenses/approve/{emp_a_id}/{req_id_2}/', follow=True)
        
        exp_rec_2 = ExpensesTable.get_item(key={'EmployeeID': emp_a_id, 'RequestID': req_id_2})
        self.assertEqual(exp_rec_2.get('Status'), 'Manager Approved')

        # HR Admin approves -> Fully Approved (Status: Approved)
        self.set_session_data({'user_id': hr_user_id})
        self.client.get(f'/workflows/expenses/approve/{emp_a_id}/{req_id_2}/', follow=True)
        
        exp_rec_final = ExpensesTable.get_item(key={'EmployeeID': emp_a_id, 'RequestID': req_id_2})
        self.assertEqual(exp_rec_final.get('Status'), 'Approved')

    def test_16_wfh_approval_and_attendance(self):
        """Test WFH workflow submission, approval, and auto-attendance record creation."""
        mgr_m_id = 'MGR-M-001'
        emp_a_id = 'EMP-A-001'
        user_m_id = 'u-mgr-m'
        user_a_id = 'u-emp-a'
        hr_user_id = 'u-hr-admin'
        hr_emp_id = 'LT-26002'

        self.track_cleanup(EmployeesTable, {'EmployeeID': mgr_m_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': emp_a_id})
        self.track_cleanup(UsersTable, {'UserID': user_m_id})
        self.track_cleanup(UsersTable, {'UserID': user_a_id})
        self.track_cleanup(UsersTable, {'UserID': hr_user_id})
        self.track_cleanup(ReportingHierarchyTable, {'ManagerID': mgr_m_id, 'EmployeeID': emp_a_id})

        EmployeesTable.put_item(item={'EmployeeID': mgr_m_id, 'FirstName': 'Manager', 'LastName': 'M', 'OnboardingStatus': 'Approved', 'IsActive': True})
        EmployeesTable.put_item(item={'EmployeeID': emp_a_id, 'FirstName': 'Employee', 'LastName': 'A', 'OnboardingStatus': 'Approved', 'IsActive': True})
        UsersTable.put_item(item={'UserID': user_m_id, 'Email': 'mgr-m@lurnexa.com', 'Role': 'Manager', 'EmployeeID': mgr_m_id, 'IsActive': True})
        UsersTable.put_item(item={'UserID': user_a_id, 'Email': 'emp-a@lurnexa.com', 'Role': 'Employee', 'EmployeeID': emp_a_id, 'IsActive': True})
        UsersTable.put_item(item={'UserID': hr_user_id, 'Email': 'hr-adm@lurnexa.com', 'Role': 'HR ADMIN', 'EmployeeID': hr_emp_id, 'IsActive': True})
        ReportingHierarchyTable.put_item(item={'ManagerID': mgr_m_id, 'EmployeeID': emp_a_id})

        # Submit WFH
        self.set_session_data({'user_id': user_a_id})
        wfh_date = '2026-08-05'
        req_id = 'wfh-req-123'
        self.track_cleanup(WFHRequestsTable, {'EmployeeID': emp_a_id, 'RequestID': req_id})
        self.track_cleanup(AttendanceTable, {'EmployeeID': emp_a_id, 'RecordDate': wfh_date})

        WFHRequestsTable.put_item(item={
            'EmployeeID': emp_a_id,
            'RequestID': req_id,
            'WFHDate': wfh_date,
            'EndDate': wfh_date,
            'Reason': 'Remote work',
            'Status': 'Pending Manager Approval',
            'ApproverID': mgr_m_id,
            'OriginalRole': 'Employee'
        })

        # Manager M approves -> status is Pending HR ADMIN Approval
        self.set_session_data({'user_id': user_m_id})
        self.client.get(f'/workflows/wfh/approve/{emp_a_id}/{req_id}/', follow=True)
        wfh_rec = WFHRequestsTable.get_item(key={'EmployeeID': emp_a_id, 'RequestID': req_id})
        self.assertEqual(wfh_rec.get('Status'), 'Pending HR ADMIN Approval')

        # HR Admin approves -> Approved and generates Attendance Record
        self.set_session_data({'user_id': hr_user_id})
        self.client.get(f'/workflows/wfh/approve/{emp_a_id}/{req_id}/', follow=True)
        
        wfh_final = WFHRequestsTable.get_item(key={'EmployeeID': emp_a_id, 'RequestID': req_id})
        self.assertEqual(wfh_final.get('Status'), 'Approved')

        att_rec = AttendanceTable.get_item(key={'EmployeeID': emp_a_id, 'RecordDate': wfh_date})
        self.assertIsNotNone(att_rec)
        self.assertEqual(att_rec.get('Status'), 'WFH')

    def test_17_certificate_approval_workflow(self):
        """Test employee certificate upload, pending approvals listing, and HR action."""
        emp_a_id = 'EMP-C-001'
        user_a_id = 'u-emp-c'
        hr_user_id = 'u-hr-admin'
        hr_emp_id = 'LT-26002'

        self.track_cleanup(EmployeesTable, {'EmployeeID': emp_a_id})
        self.track_cleanup(UsersTable, {'UserID': user_a_id})
        self.track_cleanup(UsersTable, {'UserID': hr_user_id})

        EmployeesTable.put_item(item={
            'EmployeeID': emp_a_id, 
            'FirstName': 'Cert', 
            'LastName': 'Tester', 
            'OnboardingStatus': 'Approved', 
            'IsActive': True,
            'Certificates': [
                {
                    'CertificateID': 'cert-101',
                    'Name': 'AWS Certified Cloud Practitioner',
                    'Status': 'Pending',
                    'UploadedAt': '2026-05-28T12:00:00'
                }
            ]
        })
        UsersTable.put_item(item={'UserID': user_a_id, 'Email': 'cert-test@lurnexa.com', 'Role': 'Employee', 'EmployeeID': emp_a_id, 'IsActive': True})
        UsersTable.put_item(item={'UserID': hr_user_id, 'Email': 'hr-adm@lurnexa.com', 'Role': 'HR ADMIN', 'EmployeeID': hr_emp_id, 'IsActive': True})

        # HR Admin views certificate approvals list
        self.set_session_data({'user_id': hr_user_id})
        response = self.client.get('/employees/certificates/approvals/')
        pending_list = response.context['pending_requests']
        self.assertTrue(any(c.get('CertificateID') == 'cert-101' for c in pending_list))

        # HR Rejects the certificate
        self.client.post(f'/employees/certificates/{emp_a_id}/cert-101/action/', {
            'action': 'reject',
            'reason': 'Blurry file upload'
        }, follow=True)

        emp_rec = EmployeesTable.get_item(key={'EmployeeID': emp_a_id})
        certs = emp_rec.get('Certificates', [])
        cert_item = next((c for c in certs if c.get('CertificateID') == 'cert-101'), None)
        self.assertEqual(cert_item.get('Status'), 'Rejected')
        self.assertEqual(cert_item.get('RejectionReason'), 'Blurry file upload')

        # HR Approves it
        self.client.post(f'/employees/certificates/{emp_a_id}/cert-101/action/', {
            'action': 'approve'
        }, follow=True)

        emp_rec_final = EmployeesTable.get_item(key={'EmployeeID': emp_a_id})
        certs_final = emp_rec_final.get('Certificates', [])
        cert_final = next((c for c in certs_final if c.get('CertificateID') == 'cert-101'), None)
        self.assertEqual(cert_final.get('Status'), 'Approved')

    def test_18_resignation_rejection_approval_and_lwd_block(self):
        """Test resignation rejection, approval, and deactivation after Last Working Day (LWD)."""
        temp_user_id = 'res-exit-user-id'
        temp_email = 'res-exit-test@lurnexa.com'
        temp_emp_id = 'LT-EXIT-001'
        hr_user_id = 'u-hr-admin'
        hr_emp_id = 'LT-26002'

        self.track_cleanup(UsersTable, {'UserID': temp_user_id})
        self.track_cleanup(EmployeesTable, {'EmployeeID': temp_emp_id})
        self.track_cleanup(UsersTable, {'UserID': hr_user_id})
        self.track_cleanup(ResignationsTable, {'EmployeeID': temp_emp_id})

        long_ago = (datetime.date.today() - datetime.timedelta(days=100)).isoformat()
        
        UsersTable.put_item(item={
            'UserID': temp_user_id,
            'Email': temp_email,
            'Role': 'Employee',
            'IsActive': True,
            'EmployeeID': temp_emp_id
        })
        EmployeesTable.put_item(item={
            'EmployeeID': temp_emp_id,
            'UserID': temp_user_id,
            'Email': temp_email,
            'FirstName': 'Exit',
            'LastName': 'Tester',
            'JoinedDate': long_ago,
            'OnboardingStatus': 'Approved',
            'IsActive': True
        })
        UsersTable.put_item(item={'UserID': hr_user_id, 'Email': 'hr-adm@lurnexa.com', 'Role': 'HR ADMIN', 'EmployeeID': hr_emp_id, 'IsActive': True})

        # Submit Resignation
        self.set_session_data({'user_id': temp_user_id})
        lwd_val = (datetime.date.today() + datetime.timedelta(days=60)).isoformat()
        self.client.post('/workflows/resignation/', {
            'reason': 'Personal reasons',
            'lwd': lwd_val,
            'comments': 'I want to resign'
        }, follow=True)

        # HR Rejects
        self.set_session_data({'user_id': hr_user_id})
        self.client.get(f'/workflows/resignation/process/{temp_emp_id}/reject/', follow=True)

        res_rec = ResignationsTable.get_item(key={'EmployeeID': temp_emp_id})
        self.assertEqual(res_rec.get('Status'), 'Rejected')

        # Re-submit resignation
        ResignationsTable.delete_item(key={'EmployeeID': temp_emp_id})
        self.set_session_data({'user_id': temp_user_id})
        self.client.post('/workflows/resignation/', {
            'reason': 'Personal reasons 2',
            'lwd': lwd_val,
            'comments': 'Resubmit'
        }, follow=True)

        # HR Approves
        self.set_session_data({'user_id': hr_user_id})
        self.client.get(f'/workflows/resignation/process/{temp_emp_id}/approve/', follow=True)

        res_rec_approved = ResignationsTable.get_item(key={'EmployeeID': temp_emp_id})
        self.assertEqual(res_rec_approved.get('Status'), 'Accepted Resignation')

        # Now simulate LWD has passed (LWD is set to yesterday)
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        ResignationsTable.update_item(
            Key={'EmployeeID': temp_emp_id},
            UpdateExpression="SET LastWorkingDay = :val",
            ExpressionAttributeValues={':val': yesterday}
        )

        # Trigger deactivation logic by fetching approvals
        self.set_session_data({'user_id': hr_user_id})
        self.client.get('/workflows/resignation/approvals/')

        # Verify employee is marked inactive
        emp_final = EmployeesTable.get_item(key={'EmployeeID': temp_emp_id})
        user_final = UsersTable.get_item(key={'UserID': temp_user_id})
        self.assertFalse(emp_final.get('IsActive'))
        self.assertFalse(user_final.get('IsActive'))

