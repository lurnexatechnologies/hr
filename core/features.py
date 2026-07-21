# Subscription Plans & Feature Matrix Config

FEATURE_REGISTRY = {
    # Basic Plan Features
    'onboarding':           ('Employee Self-Onboarding', 'employees'),
    'employee_directory':   ('Employee Directory & Organization Hierarchy', 'employees'),
    'leave_management':     ('Leave Management', 'leave'),
    'attendance':           ('Attendance Management', 'attendance'),
    'holiday_calendar':     ('Holiday Calendar', 'leave'),
    'ess_portal':           ('Employee Self-Service (ESS) Portal', 'core'),

    # Elite Plan Features (Includes Basic + these)
    'okrs_appraisals':      ('Performance Management & OKRs', 'core'),
    'asset_management':     ('Asset Management', 'employees'),
    'wfh_requests':         ('Work From Home (WFH) Management', 'workflows'),
    'expense_management':   ('Expense & Reimbursement Management', 'workflows'),
    'resignation_workflow': ('Resignation & Exit Management', 'workflows'),

    # Professional Plan Features (Includes Elite + these)
    'payroll':              ('Payroll Processing', 'payroll'),
    'payslips':             ('Digital Payslip Generation', 'payroll'),
    'pf_management':        ('Statutory Compliance', 'payroll'),
    'hr_letters':           ('Document Generation', 'core'),
    'alumni_management':    ('Alumni Management', 'employees'),
    'enterprise_security':  ('Enterprise Security', 'auth_custom'),
    'rbac':                 ('Advanced Role-Based Access Control (RBAC)', 'auth_custom'),

}

PLAN_FEATURES = {
    'basic': [
        'onboarding',
        'employee_directory',
        'leave_management',
        'attendance',
        'holiday_calendar',
        'ess_portal',
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
    ],
}

PLAN_LIMITS = {
    'basic':        {'max_employees': 25},
    'elite':        {'max_employees': 100},
    'professional': {'max_employees': 9999},
}
