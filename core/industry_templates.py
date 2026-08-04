"""
Industry Template Configuration Presets for Multi-Tenant Multi-Industry HRMS Engine.
"""

INDUSTRY_PROFILES = {
    'RETAIL_SUPERMARKET': {
        'id': 'RETAIL_SUPERMARKET',
        'name': 'Supermarket & Hypermarket (e.g. DMart, Reliance Smart)',
        'icon': 'bi-cart-check',
        'description': 'Store floor shift management, cashier till tracking, section performance incentives, and POS punch integration.',
        'default_shifts': [
            {'name': 'Store Opening Shift', 'start_time': '07:00', 'end_time': '15:30'},
            {'name': 'Mid-Day Billing Rush Shift', 'start_time': '11:00', 'end_time': '19:30'},
            {'name': 'Store Closing Shift', 'start_time': '14:00', 'end_time': '22:30'},
            {'name': 'Night Stocking & Inventory Shift', 'start_time': '22:00', 'end_time': '06:30'}
        ],
        'payroll_models': ['MONTHLY_CTC', 'HOURLY_WAGE', 'SECTION_TARGET_INCENTIVE'],
        'compliance_docs': ['Food Safety Handler Certificate', 'Cashier Liability Bond', 'National ID', 'Police Verification Certificate'],
        'custom_fields': [
            {'key': 'cashier_till_id', 'label': 'Cashier Till / POS Terminal ID', 'type': 'text', 'required': False},
            {'key': 'assigned_section', 'label': 'Store Section / Dept (Billing, Grocery, Fresh, Apparel)', 'type': 'select', 
             'options': ['Billing & Cash Counter', 'Grocery & Staples', 'Fresh Produce & Dairy', 'Apparel & Home', 'Warehouse Storage'], 'required': True},
            {'key': 'till_variance_allowance', 'label': 'Monthly Till Variance Limit (₹)', 'type': 'number', 'required': False, 'default': 500}
        ],
        'onboarding_config': {
            'steps': [
                'Identity & Police Background Verification',
                'Food Handler & Hygiene Screening',
                'Cash Till Variance Liability Agreement Sign-off',
                'Store Floor Section & POS Terminal Assignment',
                'Uniform, Barcode ID & Locker Allocation'
            ],
            'required_documents': [
                'Aadhaar / National ID Card',
                'PAN Card & Bank Passbook',
                'Police Verification Certificate',
                'Food Safety Handler Certificate'
            ],
            'legal_bonds': [
                'Cashier Till Shortage & Audit Liability Bond',
                'Store Security & Anti-Theft Policy Agreement'
            ],
            'equipment_allocations': [
                'POS Terminal Login Credentials & Scanner',
                'Store Branded Uniform (T-Shirt & Apron) & Name Badge',
                'Locker Key & Barcode Attendance Card'
            ]
        },
        'default_roles': {
            'Billing Cashier': {
                'Description': 'Front counter cashier handling POS billing terminals and cash till reconciliation.',
                'Features': ['attendance', 'supermarket_pos', 'shift_roster', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read'],
                'wfh_allowed': False,
                'max_wfh_per_month': 0,
                'leave_quota_annual': 12,
                'blackout_weekends': True
            },
            'Store Floor Executive': {
                'Description': 'Floor staff managing stock replenishment and customer assistance.',
                'Features': ['attendance', 'shift_roster', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read'],
                'wfh_allowed': False,
                'max_wfh_per_month': 0,
                'leave_quota_annual': 14,
                'blackout_weekends': False
            },
            'Store Manager': {
                'Description': 'Supermarket floor manager managing shift rosters, cashier audits and store performance.',
                'Features': ['attendance', 'supermarket_pos', 'shift_roster', 'helpdesk_tickets', 'expense_management', 'payroll'],
                'Policies': [],
                'Permissions': ['employee_read', 'employee_write', 'leave_approve', 'expense_approve'],
                'wfh_allowed': True,
                'max_wfh_per_month': 2,
                'leave_quota_annual': 18,
                'blackout_weekends': False
            }
        },
        'chatbot_context': 'Supermarket retail environment. Focus on floor shifts, cashier balancing, section target sales, and stock replenishment rules.'
    },
    'HEALTHCARE': {
        'id': 'HEALTHCARE',
        'name': 'Hospital & Healthcare Facility',
        'icon': 'bi-hospital',
        'description': '24/7 Rotational shift roster, doctor emergency callout, nursing ratio, and medical council certification alerts.',
        'default_shifts': [
            {'name': 'Morning Clinical Shift', 'start_time': '07:00', 'end_time': '15:00'},
            {'name': 'Evening Shift', 'start_time': '15:00', 'end_time': '23:00'},
            {'name': 'Night Emergency / ICU Shift', 'start_time': '23:00', 'end_time': '07:00'},
            {'name': 'On-Call Standing', 'start_time': '00:00', 'end_time': '23:59'}
        ],
        'payroll_models': ['MONTHLY_CTC', 'SHIFT_DIFFERENTIAL', 'ON_CALL_ALLOWANCE'],
        'compliance_docs': ['Medical Council Registration', 'NMC / Nursing License', 'Infection Control & Vaccination Card', 'CME Credits Record'],
        'custom_fields': [
            {'key': 'medical_registration_no', 'label': 'Medical Council Registration No', 'type': 'text', 'required': True},
            {'key': 'clinical_specialty', 'label': 'Specialty (ICU, Surgery, Pediatrics, OPD, ER)', 'type': 'text', 'required': True},
            {'key': 'cme_points_year', 'label': 'CME Credit Points Achieved', 'type': 'number', 'required': False, 'default': 0}
        ],
        'onboarding_config': {
            'steps': [
                'Medical Council / Nursing Council License Verification',
                'Immunization Record & Medical Board Fitness Clearance',
                'Patient Privacy (HIPAA) & Confidentiality Sign-off',
                'Clinical Specialty & Rotational ICU Roster Setup',
                'HMIS System Credentials & Restricted OT/ICU Access Badge'
            ],
            'required_documents': [
                'Medical Council / Nursing State License Certificate',
                'Degree / Diploma Certificates Verification',
                'Vaccination & Immunization Card (Hep B, TB Clearance)',
                'Medical Fitness Certificate'
            ],
            'legal_bonds': [
                'Patient Privacy & Medical Data Confidentiality (HIPAA)',
                'Infection Control & Needlestick Injury Protocol Agreement'
            ],
            'equipment_allocations': [
                'Hospital Scrubs / Clinical Lab Coat',
                'Biometric Restricted Area Access Badge (OT/ICU/Pharmacy Vault)',
                'HMIS Doctor/Nurse EMR Login Access'
            ]
        },
        'default_roles': {
            'ICU / Ward Nurse': {
                'Description': 'Clinical nursing staff managing patient care and rotational 24/7 hospital shifts.',
                'Features': ['attendance', 'shift_roster', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'Surgeon / Resident Doctor': {
                'Description': 'Medical doctor providing clinical treatments, surgeries, and emergency callouts.',
                'Features': ['attendance', 'shift_roster', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'Hospital Admin / HR': {
                'Description': 'Healthcare facility administrator managing clinical rosters, compliance and biomedical support.',
                'Features': ['attendance', 'shift_roster', 'helpdesk_tickets', 'asset_management', 'payroll'],
                'Policies': [],
                'Permissions': ['employee_read', 'employee_write', 'leave_approve', 'expense_approve', 'payroll_access']
            }
        },
        'chatbot_context': 'Hospital and clinical care context. Prioritize emergency coverage, minimum rest hours, shift swaps, and medical compliance.'
    },
    'AUTO_RETAIL': {
        'id': 'AUTO_RETAIL',
        'name': 'Automobile Showroom & Dealership',
        'icon': 'bi-car-front',
        'description': 'Vehicle sales commission tiers, lead-to-sale performance tracker, and test-drive log management.',
        'default_shifts': [
            {'name': 'Showroom Standard Shift', 'start_time': '09:30', 'end_time': '19:00'},
            {'name': 'Weekend Rush Floor Shift', 'start_time': '09:00', 'end_time': '20:00'}
        ],
        'payroll_models': ['BASE_PLUS_COMMISSION', 'MONTHLY_CTC', 'LEAD_CONVERSION_BONUS'],
        'compliance_docs': ['Driving License', 'Dealership Certification', 'ID Proof'],
        'custom_fields': [
            {'key': 'driving_license_no', 'label': 'Driving License Number', 'type': 'text', 'required': True},
            {'key': 'dl_expiry_date', 'label': 'Driving License Expiry Date', 'type': 'date', 'required': True},
            {'key': 'monthly_sales_target_units', 'label': 'Monthly Vehicle Sales Target (Units)', 'type': 'number', 'required': False, 'default': 5}
        ],
        'onboarding_config': {
            'steps': [
                'Driving License Authenticity Verification',
                'Test-Drive Vehicle Damage Liability Agreement Sign-off',
                'Sales Commission & Lead Protection Terms Acknowledgment',
                'OEM & Dealership Product Induction Training',
                'Showroom Tablet & Dealership CRM Setup'
            ],
            'required_documents': [
                'Commercial / Private Driving License (Valid)',
                'Educational & Previous Sales Experience Certificates',
                'Government ID & Address Proof'
            ],
            'legal_bonds': [
                'Test-Drive Vehicle Damage & Driving Liability Bond',
                'Client Lead Data Non-Disclosure & Non-Solicitation Agreement'
            ],
            'equipment_allocations': [
                'Dealership Sales Blazer / Uniform & Name Badge',
                'Showroom CRM Portal Login Credentials',
                'Test-Drive Key Cabinet RFID Access Card'
            ]
        },
        'default_roles': {
            'Sales Consultant': {
                'Description': 'Showroom sales consultant driving vehicle sales, test-drives and customer leads.',
                'Features': ['attendance', 'field_sales_tracking', 'expense_management', 'helpdesk_tickets', 'okrs_appraisals', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'Test-Drive Executive': {
                'Description': 'Showroom executive managing test-drive vehicles, license checks and customer drives.',
                'Features': ['attendance', 'field_sales_tracking', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'Dealership General Manager': {
                'Description': 'General manager overseeing sales teams, commission payouts and showroom operations.',
                'Features': ['attendance', 'field_sales_tracking', 'expense_management', 'payroll', 'helpdesk_tickets'],
                'Policies': [],
                'Permissions': ['employee_read', 'employee_write', 'leave_approve', 'expense_approve', 'payroll_access']
            }
        },
        'chatbot_context': 'Automobile retail dealership. Emphasize sales targets, test-drive protocols, commission calculation, and client meeting check-ins.'
    },
    'TILES_MFG': {
        'id': 'TILES_MFG',
        'name': 'Tiles & Heavy Manufacturing Factory',
        'icon': 'bi-building-gear',
        'description': 'Piece-rate compensation (pay per sq ft / batch), gate biometric kiosk, contract labor pass, and safety hazard pay.',
        'default_shifts': [
            {'name': 'Factory Day Shift', 'start_time': '08:00', 'end_time': '16:30'},
            {'name': 'Factory Night Production Shift', 'start_time': '20:00', 'end_time': '04:30'}
        ],
        'payroll_models': ['PIECE_RATE', 'DAILY_WAGE', 'MONTHLY_CTC', 'HAZARD_PAY'],
        'compliance_docs': ['Factory Act Medical Fitness Certificate', 'Safety Training Card', 'Government ID'],
        'custom_fields': [
            {'key': 'piece_rate_unit', 'label': 'Piece-Rate Basis (Sq Ft / Metric Ton / Boxes)', 'type': 'text', 'required': False, 'default': 'Sq Ft'},
            {'key': 'rate_per_unit', 'label': 'Default Piece-Rate Amount (₹ per unit)', 'type': 'number', 'required': False, 'default': 2.50},
            {'key': 'gate_pass_id', 'label': 'Factory Gate Pass Badge ID', 'type': 'text', 'required': False}
        ],
        'onboarding_config': {
            'steps': [
                'Factory Act Age & Labor Law Compliance Verification',
                'Pre-Employment Industrial Health & Vision Examination',
                'Hazardous Machinery & Kiln Safety Induction',
                'PPE Kit Sizing & Safety Gear Issue',
                'Factory Gate Pass Generation & Biometric Fingerprint Registration'
            ],
            'required_documents': [
                'Government ID & Age Proof',
                'Factory Medical Fitness Certificate (Audiometry & Lung Test)',
                'ESIC / EPFO Nomination Forms'
            ],
            'legal_bonds': [
                'Factory Industrial Safety & Emergency Protocol NDA',
                'Piece-Rate Wage Ratecard & Output Measurement Agreement'
            ],
            'equipment_allocations': [
                'Steel-Toe Safety Boots & Helmet',
                'Dust Respirator Mask & Protective Work Gloves',
                'Factory Gate Pass RFID Badge'
            ]
        },
        'default_roles': {
            'Kiln / Press Operator': {
                'Description': 'Factory operator managing kiln temperatures, press machinery and production line safety.',
                'Features': ['attendance', 'shift_roster', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'Piece-Rate Production Packer': {
                'Description': 'Factory worker packing tile boxes paid on piece-rate output basis.',
                'Features': ['attendance', 'shift_roster', 'flexible_industry_payroll', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'Factory Plant Manager': {
                'Description': 'Factory manager managing plant shifts, piece-rate batch approvals and industrial safety.',
                'Features': ['attendance', 'shift_roster', 'flexible_industry_payroll', 'asset_management', 'payroll'],
                'Policies': [],
                'Permissions': ['employee_read', 'employee_write', 'leave_approve', 'expense_approve', 'payroll_access']
            }
        },
        'chatbot_context': 'Tiles manufacturing & factory environment. Focus on shift output, piece-rate wages, gate punch rules, and safety PPE compliance.'
    },
    'POULTRY_PROCESSING': {
        'id': 'POULTRY_PROCESSING',
        'name': 'Poultry & Chicken Processing Plant',
        'icon': 'bi-egg-fried',
        'description': 'Processing line batch output, cold storage risk allowances, and FSSAI health & hygiene clearances.',
        'default_shifts': [
            {'name': 'Early Processing Line Shift', 'start_time': '05:00', 'end_time': '13:30'},
            {'name': 'Packaging & Cold Storage Shift', 'start_time': '13:00', 'end_time': '21:30'}
        ],
        'payroll_models': ['PIECE_RATE', 'HOURLY_WAGE', 'COLD_STORAGE_ALLOWANCE', 'MONTHLY_CTC'],
        'compliance_docs': ['FSSAI Food Hygiene Clearance', 'Medical Fitness Certificate', 'Sanitation Check Card'],
        'custom_fields': [
            {'key': 'hygiene_clearance_id', 'label': 'Food Hygiene Clearance ID', 'type': 'text', 'required': True},
            {'key': 'assigned_line', 'label': 'Processing Line / Department', 'type': 'select', 
             'options': ['Receiving & Inspection', 'Processing Line', 'Packaging & Quality', 'Cold Storage Locker'], 'required': True}
        ],
        'onboarding_config': {
            'steps': [
                'FSSAI Food Handler Hygiene Screening',
                'HACCP Sanitation Protocol & Handwash Training',
                'Cold-Room Thermal Gear & Processing Line Fitting',
                'Processing Line Target & Batch Rate Agreement',
                'Hygiene Station RFID Gate Access Pass'
            ],
            'required_documents': [
                'FSSAI Approved Food Handler Health Certificate',
                'Skin & Infectious Disease Test Clearance',
                'Government ID & Bank Details'
            ],
            'legal_bonds': [
                'Food Hygiene & Cross-Contamination Prevention Protocol',
                'Cold Storage Rest Period & Risk Allowance Terms'
            ],
            'equipment_allocations': [
                'Insulated Cold-Room Suit & Thermal Rubber Boots',
                'Cut-Resistant Gloves, Hairnet & Face Shield',
                'Hygiene Disinfection Gate Access Badge'
            ]
        },
        'default_roles': {
            'Processing Line Worker': {
                'Description': 'Plant worker operating chicken processing and packaging lines.',
                'Features': ['attendance', 'shift_roster', 'flexible_industry_payroll', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'Cold Storage Locker Handler': {
                'Description': 'Plant worker managing sub-zero cold storage lockers and dispatch.',
                'Features': ['attendance', 'shift_roster', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            }
        },
        'chatbot_context': 'Poultry processing facility. Highlight hygiene compliance, cold storage rest periods, line batch incentives, and food safety standards.'
    },
    'AGRI_SEEDS': {
        'id': 'AGRI_SEEDS',
        'name': 'Seeds & Agricultural Processing Plant',
        'icon': 'bi-tree',
        'description': 'Seasonal surge worker hiring, crop yield performance bonuses, and farm field geofenced mobile check-ins.',
        'default_shifts': [
            {'name': 'Processing Plant Shift', 'start_time': '08:30', 'end_time': '17:00'},
            {'name': 'Field Sampling & Collection Shift', 'start_time': '06:00', 'end_time': '14:30'}
        ],
        'payroll_models': ['SEASONAL_DAILY_RATE', 'MONTHLY_CTC', 'CROP_YIELD_BONUS'],
        'compliance_docs': ['Agri Lab Certification', 'Seasonal Labor Agreement', 'Govt ID Proof'],
        'custom_fields': [
            {'key': 'seed_lab_licence', 'label': 'Seed Analyst / Lab Specialist Licence', 'type': 'text', 'required': False},
            {'key': 'worker_category', 'label': 'Employment Type', 'type': 'select', 
             'options': ['Permanent Staff', 'Seasonal Harvest Contract', 'Field Collector', 'R&D Lab Specialist'], 'required': True}
        ],
        'onboarding_config': {
            'steps': [
                'Seasonal / Permanent Agricultural Category Verification',
                'Chemical Seed Coating Safety Induction',
                'Seed Quality Lab Specialist Licence Verification',
                'Farm Geofence App Mobile Clock-In Training',
                'Plant Gate Pass & Lab Gear Allocation'
            ],
            'required_documents': [
                'Government ID & Bank Passbook',
                'Seed Analyst License (For R&D Lab Staff)',
                'Seasonal Labor Contract Agreement'
            ],
            'legal_bonds': [
                'Agri Chemical Handling Safety Protocol',
                'Proprietary Seed Hybrid Genetics Non-Disclosure Agreement'
            ],
            'equipment_allocations': [
                'Lab Overalls & Chemical Resistant Gloves',
                'Field Geofence Mobile App Access Credentials',
                'Plant Gate Attendance Pass'
            ]
        },
        'default_roles': {
            'R&D Seed Analyst': {
                'Description': 'Lab specialist carrying out seed quality testing and chemical seed treatment.',
                'Features': ['attendance', 'asset_management', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'Field Sample Collector': {
                'Description': 'Field staff collecting crop samples using mobile GPS geofenced check-ins.',
                'Features': ['attendance', 'field_sales_tracking', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            }
        },
        'chatbot_context': 'Agricultural seeds processing plant. Focus on seasonal surge labor, field geofence punches, crop yield bonuses, and seed quality lab compliance.'
    },
    'SOFTWARE_IT': {
        'id': 'SOFTWARE_IT',
        'name': 'Software & IT Tech Company',
        'icon': 'bi-laptop',
        'description': 'Flexible working hours, hybrid/remote IP check-in, sprint timesheets, tech stack skill tracking, and ESOP vesting.',
        'default_shifts': [
            {'name': 'General Flexible Shift', 'start_time': '09:00', 'end_time': '18:00'},
            {'name': 'US Overlap Shift', 'start_time': '14:00', 'end_time': '23:00'}
        ],
        'payroll_models': ['MONTHLY_CTC', 'PROJECT_BILLABLE_BONUS', 'ESOP_VESTING'],
        'compliance_docs': ['Non-Disclosure Agreement (NDA)', 'IP Assignment Agreement', 'Degree Certificate'],
        'custom_fields': [
            {'key': 'primary_tech_stack', 'label': 'Primary Tech Stack / Skills', 'type': 'text', 'required': False},
            {'key': 'github_username', 'label': 'GitHub / GitLab Profile Username', 'type': 'text', 'required': False},
            {'key': 'billable_hourly_rate', 'label': 'Client Billable Hourly Rate (₹ - For Client Invoicing)', 'type': 'number', 'required': False, 'default': 0}
        ],
        'onboarding_config': {
            'steps': [
                'Background Verification (BGV - Degree & Previous Experience)',
                'IP Assignment & Non-Disclosure Agreement (NDA) E-Signing',
                'IT Hardware & Laptop Asset Provisioning',
                'Corporate Email, GitHub, Slack & Cloud Access Provisioning',
                'Sprint Manager & Team Buddy Assignment'
            ],
            'required_documents': [
                'Educational Degree & Marksheets',
                'Previous Employment Relieving & Experience Letters',
                'Last 3 Months Payslips & Form 16',
                'Government ID & PAN'
            ],
            'legal_bonds': [
                'Proprietary Code & Intellectual Property Assignment Agreement',
                'Non-Compete & Client Non-Solicitation NDA'
            ],
            'equipment_allocations': [
                'Development Laptop (MacBook / Enterprise Laptop)',
                'Monitors, Accessories & Security Key',
                'Corporate Workspace (Google Workspace, Slack, Jira, GitHub)'
            ]
        },
        'default_roles': {
            'Software Engineer': {
                'Description': 'Developer building software applications, sprint tasks and Timesheet logging.',
                'Features': ['attendance', 'wfh_requests', 'asset_management', 'okrs_appraisals', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'DevOps / SysAdmin': {
                'Description': 'System administrator managing IT assets, cloud infrastructure and security licenses.',
                'Features': ['attendance', 'wfh_requests', 'asset_management', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            }
        },
        'chatbot_context': 'Software engineering environment. Focus on remote work policies, sprint timesheets, IP NDAs, and project billable hours.'
    },
    'EDUCATION_SCHOOL_COLLEGE': {
        'id': 'EDUCATION_SCHOOL_COLLEGE',
        'name': 'School, College & Educational Institution',
        'icon': 'bi-mortarboard',
        'description': 'Academic term schedules, teacher lecture workloads, UGC/CBSE/ICSE compliance, exam/vacation leave rosters, and academic grade/subject assignments.',
        'default_shifts': [
            {'name': 'Morning School Shift', 'start_time': '07:30', 'end_time': '14:30'},
            {'name': 'Standard College Shift', 'start_time': '08:30', 'end_time': '16:30'},
            {'name': 'Evening / Lecture Shift', 'start_time': '12:00', 'end_time': '19:30'},
            {'name': 'Administrative & Support Staff Shift', 'start_time': '09:00', 'end_time': '17:30'}
        ],
        'payroll_models': ['MONTHLY_CTC', 'LECTURE_BASE_PAY', 'EXAM_DUTY_ALLOWANCE', 'RESEARCH_GRANT_INCENTIVE'],
        'compliance_docs': ['Teacher Eligibility Test (TET/NET/SET) Certificate', 'B.Ed / Ph.D. Degree Certificate', 'Police Verification Certificate', 'National ID Proof'],
        'custom_fields': [
            {'key': 'faculty_registration_no', 'label': 'Faculty / Teacher Registration No', 'type': 'text', 'required': True},
            {'key': 'assigned_department_subject', 'label': 'Academic Department / Subject', 'type': 'select',
             'options': ['Mathematics & Science', 'Computer Science & IT', 'Languages & Humanities', 'Commerce & Management', 'Administrative & Support'], 'required': True},
            {'key': 'academic_designation', 'label': 'Academic Cadre / Designation', 'type': 'select',
             'options': ['Professor / HOD', 'Associate Professor', 'Assistant Professor', 'School Teacher (PGT/TGT/PRT)', 'Lab Technician / Assistant', 'Administrative Staff'], 'required': True},
            {'key': 'highest_qualification', 'label': 'Highest Academic Qualification (Ph.D., M.Ed, B.Ed, M.Tech)', 'type': 'text', 'required': False},
            {'key': 'weekly_lecture_load', 'label': 'Weekly Lecture Load (Hours/Week)', 'type': 'number', 'required': False, 'default': 18}
        ],
        'onboarding_config': {
            'steps': [
                'B.Ed / Ph.D. & Academic Credentials Verification',
                'Teacher Eligibility Test (TET/NET/SET) Registration Check',
                'Police Background & Child Safety (POCSO) Screening',
                'Academic Department, Subject & Class Section Allocation',
                'Faculty ID Card, Library Access & LMS Portal Credentials Setup'
            ],
            'required_documents': [
                '10th, 12th, Graduation & Post-Graduation Marksheets',
                'B.Ed / M.Ed / Ph.D. Degree Certificate Verification',
                'TET / NET / SET Qualification Certificate',
                'Police Background Verification Certificate'
            ],
            'legal_bonds': [
                'Academic Term / Semester Non-Resignation Commitment Bond',
                'Student Protection (POSH/POCSO) & Educational Code of Conduct Agreement'
            ],
            'equipment_allocations': [
                'Faculty Laptop / Workstation & Classroom Smartboard Pass',
                'LMS & Student Grading System Credentials',
                'Staff RFID Access Badge & Library Card'
            ]
        },
        'default_roles': {
            'Professor / Senior Lecturer': {
                'Description': 'Senior academic faculty managing lectures, research publications, exams, and curriculum development.',
                'Features': ['attendance', 'wfh_requests', 'leave_management', 'okrs_appraisals', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'School Teacher (PGT/TGT)': {
                'Description': 'Teaching staff handling classroom lectures, lesson planning, student attendance and exam duty.',
                'Features': ['attendance', 'leave_management', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'Lab Technician / Assistant': {
                'Description': 'Technical staff managing computer/science labs, equipment maintenance and practical exam support.',
                'Features': ['attendance', 'asset_management', 'helpdesk_tickets', 'ess_portal'],
                'Policies': [],
                'Permissions': ['employee_read']
            },
            'School / College Principal / Dean': {
                'Description': 'Academic head overseeing department operations, faculty lecture loads, exam schedules and leave approvals.',
                'Features': ['attendance', 'leave_management', 'helpdesk_tickets', 'asset_management', 'payroll', 'expense_management'],
                'Policies': [],
                'Permissions': ['employee_read', 'employee_write', 'leave_approve', 'expense_approve', 'payroll_access']
            }
        },
        'chatbot_context': 'School, College and Higher Education institution context. Focus on academic semester calendars, lecture workload rules, exam duty allocations, vacation/duty leaves, and TET/UGC compliance.'
    },
    'CUSTOM': {
        'id': 'CUSTOM',
        'name': 'Custom Enterprise / Other Industry',
        'icon': 'bi-gear-wide-connected',
        'description': 'Blank slate profile allowing customized shifts, fields, and payroll strategies for unique business verticals.',
        'default_shifts': [
            {'name': 'Standard Shift', 'start_time': '09:00', 'end_time': '18:00'}
        ],
        'payroll_models': ['MONTHLY_CTC', 'HOURLY_WAGE'],
        'compliance_docs': ['Government ID Proof'],
        'custom_fields': [],
        'onboarding_config': {
            'steps': [
                'Identity & Educational Document Verification',
                'Company Policy & Code of Conduct Sign-off',
                'Statutory Benefits Nomination (PF / Gratuity)',
                'Workstation & Access Card Allocation'
            ],
            'required_documents': [
                'Government ID & Address Proof',
                'Educational Certificates'
            ],
            'legal_bonds': [
                'Company Code of Conduct & Anti-Harassment (POSH) Policy'
            ],
            'equipment_allocations': [
                'Workstation & Office Access Card'
            ]
        },
        'default_roles': {
            'General Employee': {
                'Description': 'Standard employee with essential self-service features.',
                'Features': ['onboarding', 'employee_directory', 'leave_management', 'attendance', 'ess_portal', 'helpdesk_tickets'],
                'Policies': [],
                'Permissions': ['employee_read']
            }
        },
        'chatbot_context': 'General enterprise environment.'
    }
}

def get_industry_profile(industry_id):
    """Fetch an industry profile preset dictionary by key, fallback to CUSTOM."""
    return INDUSTRY_PROFILES.get(industry_id, INDUSTRY_PROFILES['CUSTOM'])
