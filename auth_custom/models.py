class DynamoUser:
    def __init__(self, data):
        self.id = data.get('UserID')
        self.user_id = data.get('UserID')
        self.email = data.get('Email')
        role_raw = data.get('Role', 'Employee').strip()
        role_upper = role_raw.upper()
        if role_upper in ['PLATFORM ADMIN', 'PLATFORM SUPER ADMIN']:
            self.role = 'Platform Admin'
        elif role_upper in ['SUPER ADMIN', 'SUPERADMIN']:
            self.role = 'Super admin'
        elif role_upper in ['HR ADMIN', 'HRADMIN', 'HR']:
            self.role = 'HR ADMIN'
        elif role_upper == 'MANAGER':
            self.role = 'Manager'
        else:
            self.role = 'Employee'
        self.is_active = data.get('IsActive', True)
        self.is_authenticated = True
        self.is_anonymous = False
        
        # Additional fields
        self.employee_id = data.get('EmployeeID') or data.get('UserID')
        self.first_name = data.get('FirstName', '')
        self.last_name = data.get('LastName', '')
        self.passport_photo = data.get('PassportPhoto')
        self.onboarding_status = data.get('OnboardingStatus', 'Approved') # Default to Approved for existing employees
        self.rejection_reason = data.get('RejectionReason', '')

        # Multi-tenant fields
        self.org_id = data.get('OrgID')
        self.plan = None        # Set by middleware
        self.features = []      # Set by middleware
        self.org = {}           # Set by middleware
        self.permissions = []   # Set by middleware

    def has_perm(self, perm):
        if self.role in ['Platform Admin', 'Super admin']:
            return True
        return perm in getattr(self, 'permissions', [])

    @property
    def employee(self):
        """Lazy lookup for full employee record if needed in templates."""
        if not hasattr(self, '_employee_cache'):
            if not self.employee_id:
                self._employee_cache = None
            else:
                from core.dynamodb_service import EmployeesTable
                self._employee_cache = EmployeesTable.get_item({'EmployeeID': self.employee_id})
        return self._employee_cache

    def has_role(self, role):
        return self.role == role

class DynamoAnonymousUser:
    is_authenticated = False
    is_anonymous = True
    role = None

    def has_role(self, role):
        return False
