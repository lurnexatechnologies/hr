# Subscription Plans & Feature Matrix Config

FEATURE_REGISTRY = {
    # Basic Plan Features
    'onboarding':           ('Employee Self-Onboarding', 'employees', 'All Industries'),
    'employee_directory':   ('Employee Directory & Organization Hierarchy', 'employees', 'All Industries'),
    'leave_management':     ('Leave Management', 'leave', 'All Industries'),
    'attendance':           ('Attendance Management', 'attendance', 'All Industries'),
    'holiday_calendar':     ('Holiday Calendar', 'leave', 'All Industries'),
    'ess_portal':           ('Employee Self-Service (ESS) Portal', 'core', 'All Industries'),

    # Elite Plan Features (Includes Basic + these)
    'okrs_appraisals':      ('Performance Management & OKRs', 'core', 'Software IT, Corporate & Showrooms'),
    'asset_management':     ('Asset Management', 'employees', 'Software IT, Hospitals & Factories'),
    'wfh_requests':         ('Work From Home (WFH) Management', 'workflows', 'Software IT & Corporate'),
    'expense_management':   ('Expense & Reimbursement Management', 'workflows', 'Car Showrooms, Sales & All Industries'),
    'resignation_workflow': ('Resignation & Exit Management', 'workflows', 'All Industries'),

    # Professional Plan Features (Includes Elite + these)
    'payroll':              ('Payroll Processing', 'payroll', 'All Industries'),
    'payslips':             ('Digital Payslip Generation', 'payroll', 'All Industries'),
    'pf_management':        ('Statutory Compliance', 'payroll', 'All Industries'),
    'hr_letters':           ('Document Generation', 'core', 'All Industries'),
    'alumni_management':    ('Alumni Management', 'employees', 'Software IT & Corporate'),
    'enterprise_security':  ('Enterprise Security', 'auth_custom', 'All Industries'),
    'rbac':                 ('Advanced Role-Based Access Control (RBAC)', 'auth_custom', 'All Industries'),

    # Multi-Industry Specialized Modules
    'helpdesk_tickets':     ('Universal Multi-Industry Helpdesk & Ticketing', 'tickets', 'All Industries (POS, Biomedical, Machinery, IT)'),
    'shift_roster':         ('Rotational Shift Roster & Duty Swapping', 'attendance', 'Hospitals, Supermarkets & Factories'),
    'supermarket_pos':      ('Supermarket POS Clock-In & Till Reconciliation', 'attendance', 'Supermarkets & Hypermarkets (e.g. DMart)'),
    'flexible_industry_payroll': ('Flexible Industry Payroll (Piece-Rate & Commissions)', 'payroll', 'Factories, Showrooms, Poultry & Hospitals'),
    'field_sales_tracking': ('Live GPS Location & Field Sales Executive Tracking', 'sales', 'Car Showrooms, Seed Distributors & Field Delivery'),
}

PLAN_FEATURES = {
    'basic': [
        'onboarding',
        'employee_directory',
        'leave_management',
        'attendance',
        'holiday_calendar',
        'ess_portal',
        'helpdesk_tickets',
        'shift_roster',
    ],
    'elite': [
        'onboarding',
        'employee_directory',
        'leave_management',
        'attendance',
        'holiday_calendar',
        'ess_portal',
        'okrs_appraisals',
        'asset_management',
        'wfh_requests',
        'expense_management',
        'resignation_workflow',
        'helpdesk_tickets',
        'shift_roster',
        'supermarket_pos',
        'field_sales_tracking',
    ],
    'professional': [
        'onboarding',
        'employee_directory',
        'leave_management',
        'attendance',
        'holiday_calendar',
        'ess_portal',
        'okrs_appraisals',
        'asset_management',
        'wfh_requests',
        'expense_management',
        'resignation_workflow',
        'payroll',
        'payslips',
        'pf_management',
        'hr_letters',
        'alumni_management',
        'enterprise_security',
        'rbac',
        'helpdesk_tickets',
        'shift_roster',
        'supermarket_pos',
        'flexible_industry_payroll',
        'field_sales_tracking',
    ],
    'custom': [],
}

PLAN_LIMITS = {
    'basic':        {'max_employees': 9999},
    'elite':        {'max_employees': 9999},
    'professional': {'max_employees': 9999},
    'custom':       {'max_employees': 9999},
}
