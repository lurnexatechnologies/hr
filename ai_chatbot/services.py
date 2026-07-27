import json
import logging
import os
import requests
import datetime
from django.conf import settings
from core.dynamodb_service import EmployeesTable, LeaveRequestsTable, AttendanceTable, HolidaysTable, ReportingHierarchyTable, PayslipsTable, ExpensesTable, WFHRequestsTable
from core.utils import resolve_workflow_step, get_local_now, send_notification

logger = logging.getLogger(__name__)

# System Instruction for Pure AI Model (Groq Llama-3.3 70B / DeepSeek)
SYSTEM_INSTRUCTION = """
You are 'Lurnexa AI Assistant', an advanced multi-lingual AI HR Assistant powered by Llama-3.3 / DeepSeek AI.

ROLE-BASED PORTAL ACCESS & KNOWLEDGE:
1. FOR HR ADMIN, MANAGERS, ADMINS & SUPER ADMINS:
   - You have FULL ADMINISTRATIVE & DATA ACCESS across the entire organization (Org ID).
   - You can look up, search, analyze, and retrieve leave history, attendance, profile details, and pending request approvals for ANY employee listed in your Organization Employee Directory.
   - When an HR Admin/Manager asks about an employee (e.g., "how many leaves did hyfyh hgfhg take", "who is hyfyh hgfhg", "show pending leave approvals"), match the employee in the Organization Employee Directory, call the respective tool (`get_employee_leave_history`, `get_employee_details`, `get_pending_approvals_list`), and provide a complete, clear, and professional response.

2. FOR STANDARD EMPLOYEES:
   - You have direct, secure access to the logged-in employee's personal profile, portal records, leave balances, attendance, and request status.

CRITICAL CONVERSATIONAL APPLICATION WORKFLOW RULES (LEAVE / WFH / EXPENSES):
1. LEAVE APPLICATION (`apply_leave`):
   - STEP 1 (Interactive Leave Form Widget):
     When the user asks to apply for leave (or clicks Apply Leave), prompt them with:
     "Please fill out your leave details below:
      [LEAVE_FORM_WIDGET]"

   - STEP 2 (Summary & Selectable Confirmation Options):
     Once the user submits the Leave Form, DO NOT call `apply_leave` immediately. First present the application summary along with clickable confirmation choices:
     "📋 **Leave Application Summary**:
      - **Leave Type**: [Type]
      - **From Date**: [Start Date]
      - **To Date**: [End Date]
      - **Reason**: [Reason]

      Would you like me to submit this application for you?
      - Yes, Submit Application
      - No, Cancel Request"

   - STEP 3 (Execution): ONLY call `apply_leave` tool with `user_confirmation: true` WHEN the user selects or confirms "Yes" / "Submit".

2. WORK FROM HOME (`apply_wfh`) & EXPENSE CLAIMS (`apply_expense`):
   - Follow the exact same 3-step workflow with selectable options and confirmation choices (`- Yes, Submit Application`, `- No, Cancel Request`).

CRITICAL LANGUAGE INSTRUCTION:
- ALWAYS reply in the user's selected target language specified in the prompt: {target_language}.
- Do NOT reply in Telugu unless the selected target language is explicitly Telugu.
- If the selected target language is English, respond ONLY in English.
- If the selected target language is Hindi, respond in Hindi (Devanagari script).
- If the selected target language is Tamil, respond in Tamil script.
- If the selected target language is Kannada, respond in Kannada script.
- If the selected target language is Spanish, respond in Spanish.
"""

GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "apply_leave",
            "description": "Submit leave request into system portal ONLY AFTER displaying summary to user and receiving explicit user confirmation ('Yes')",
            "parameters": {
                "type": "object",
                "properties": {
                    "leave_type": {
                        "type": "string", 
                        "enum": ["Casual Leave (CL)", "Sick Leave (SL)", "Earned Leave (EL)", "Marriage Leave", "Maternity Leave", "Paternity Leave", "Unpaid Leave"]
                    },
                    "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                    "reason": {"type": "string", "description": "Detailed reason for applying leave"},
                    "user_confirmation": {
                        "type": "boolean",
                        "description": "Must ONLY be true when the user explicitly agreed/confirmed ('Yes', 'Submit', 'Confirm') after seeing the application summary."
                    }
                },
                "required": ["leave_type", "start_date", "end_date", "reason", "user_confirmation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_wfh",
            "description": "Submit WFH request into system portal ONLY AFTER displaying summary to user and receiving explicit user confirmation ('Yes')",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                    "reason": {"type": "string", "description": "Reason for WFH request"},
                    "wfh_type": {"type": "string", "enum": ["Full Day", "Half Day"]},
                    "user_confirmation": {
                        "type": "boolean",
                        "description": "Must ONLY be true when the user explicitly agreed/confirmed ('Yes', 'Submit', 'Confirm') after seeing the application summary."
                    }
                },
                "required": ["start_date", "end_date", "reason", "user_confirmation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_expense",
            "description": "Submit expense reimbursement claim into system portal ONLY AFTER displaying summary to user and receiving explicit user confirmation ('Yes')",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Amount in INR / Currency"},
                    "category": {"type": "string", "description": "Category e.g. Travel, Food, Internet, Supplies"},
                    "description": {"type": "string", "description": "Description of expense"},
                    "user_confirmation": {
                        "type": "boolean",
                        "description": "Must ONLY be true when the user explicitly agreed/confirmed ('Yes', 'Submit', 'Confirm') after seeing the application summary."
                    }
                },
                "required": ["amount", "category", "description", "user_confirmation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_employee_leave_history",
            "description": "Fetch complete leave history, total approved leave days taken, and leave status for a specific employee by name or Employee ID (HR Admin / Manager only)",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_identifier": {
                        "type": "string",
                        "description": "Employee Name, First Name, Last Name, or Employee ID (e.g. 'hyfyh hgfhg' or 'tghfh')"
                    }
                },
                "required": ["employee_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_employee_details",
            "description": "Fetch detailed profile, contact, department, designation, manager, and role for OTHER employees in the organization (HR Admin / Manager only). Do NOT call this for the logged-in user's own profile or assets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_identifier": {
                        "type": "string",
                        "description": "Employee Name or Employee ID"
                    }
                },
                "required": ["employee_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_assets",
            "description": "Fetch company hardware, laptops, devices, and inventory assets assigned to the logged in user",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_approvals_list",
            "description": "Fetch all pending leave requests, WFH requests, and expense claims waiting for HR Admin / Manager approval",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_employees",
            "description": "Search employees in organization by department, designation, name, or role (HR Admin / Manager only)",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword e.g. 'Engineering', 'Developer', 'hyfyh'"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "Fetch complete profile details of the logged in user (Birthday/DOB, joining date, manager, department, designation, etc.)",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_reporting_hierarchy",
            "description": "Fetch reporting manager and direct team reportees for the user",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_leave_balance",
            "description": "Fetch live leave balance for employee",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_attendance",
            "description": "Fetch attendance history and today's punch details",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_holidays",
            "description": "Fetch upcoming company holidays calendar",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_requests",
            "description": "Fetch status of user's recent leave, WFH, and expense requests",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_payslips",
            "description": "Fetch user's payslip and salary details",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_org_summary",
            "description": "Fetch organization employee count and pending approvals (HR Admin / Manager only)",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

def fetch_user_reporting_manager(employee_id, org_id):
    """Dynamically resolve reporting manager from ReportingHierarchyTable or HR Admin fallback."""
    try:
        links = ReportingHierarchyTable.scan(
            FilterExpression="EmployeeID = :eid",
            ExpressionAttributeValues={":eid": employee_id}
        )
        if links:
            mgr_id = links[0].get('ManagerID')
            if mgr_id:
                mgr = EmployeesTable.get_item({'EmployeeID': mgr_id})
                if mgr:
                    name = f"{mgr.get('FirstName', '')} {mgr.get('LastName', '')}".strip() or mgr_id
                    desig = mgr.get('Designation', 'Manager')
                    email = mgr.get('Email', 'N/A')
                    return f"{name} (ID: {mgr_id}, Designation: {desig}, Email: {email})"
                return f"Manager ID: {mgr_id}"
        
        # Check HR ADMIN fallback in organization
        all_emps = EmployeesTable.scan()
        hr_admins = [e for e in all_emps if e.get('OrgID') == org_id and e.get('Role') == 'HR ADMIN' and e.get('EmployeeID') != employee_id]
        if hr_admins:
            hr = hr_admins[0]
            hr_name = f"{hr.get('FirstName', '')} {hr.get('LastName', '')}".strip() or hr.get('EmployeeID')
            return f"{hr_name} (HR Admin Lead, Email: {hr.get('Email', 'N/A')})"
    except Exception as e:
        logger.error(f"Error fetching reporting manager: {e}")
    return "Not Assigned"

def fetch_user_team_reportees(employee_id):
    """Fetch direct reportees for managers."""
    try:
        links = ReportingHierarchyTable.scan(
            FilterExpression="ManagerID = :mid",
            ExpressionAttributeValues={":mid": employee_id}
        )
        reportee_ids = [l.get('EmployeeID') for l in links if l.get('EmployeeID')]
        if reportee_ids:
            all_emps = EmployeesTable.scan()
            reportees = [e for e in all_emps if e.get('EmployeeID') in reportee_ids]
            names = [f"{e.get('FirstName', '')} {e.get('LastName', '')} ({e.get('EmployeeID')})" for e in reportees]
            return ", ".join(names)
    except Exception as e:
        logger.error(f"Error fetching team reportees: {e}")
    return "None (No direct reportees)"

def fetch_user_payslips(employee_id):
    try:
        slips = [p for p in PayslipsTable.scan() if p.get('EmployeeID') == employee_id]
        if slips:
            latest = slips[-1]
            period = latest.get('PayPeriod') or latest.get('Month') or latest.get('Year') or 'Latest'
            gross = latest.get('GrossPay') or latest.get('GrossSalary') or 'N/A'
            net = latest.get('NetPay') or latest.get('NetSalary') or 'N/A'
            return f"{period}: Net Pay ₹{net}, Gross ₹{gross}"
    except Exception as e:
        logger.error(f"Error fetching payslips: {e}")
    return "No payslips available"

def fetch_user_all_requests(employee_id):
    try:
        leaves = [l for l in LeaveRequestsTable.scan() if l.get('EmployeeID') == employee_id]
        wfhs = [w for w in WFHRequestsTable.scan() if w.get('EmployeeID') == employee_id]
        expenses = [e for e in ExpensesTable.scan() if e.get('EmployeeID') == employee_id]
        
        l_summary = [f"{l.get('Type', 'Leave')} ({l.get('LeaveDate') or l.get('StartDate')}, Status: {l.get('Status')})" for l in leaves[-3:]]
        w_summary = [f"WFH ({w.get('WFHDate') or w.get('StartDate')}, Status: {w.get('Status')})" for w in wfhs[-3:]]
        e_summary = [f"Expense ₹{e.get('Amount')} for {e.get('Category')} (Status: {e.get('Status')})" for e in expenses[-3:]]
        
        req_parts = []
        if l_summary: req_parts.append("Leaves: " + "; ".join(l_summary))
        if w_summary: req_parts.append("WFH: " + "; ".join(w_summary))
        if e_summary: req_parts.append("Expenses: " + "; ".join(e_summary))
        
        return " | ".join(req_parts) if req_parts else "No active or recent requests"
    except Exception as e:
        logger.error(f"Error fetching portal requests: {e}")
    return "No requests found"

def fetch_user_assets(employee_id):
    try:
        from core.dynamodb_service import AssetsTable
        assets = [a for a in AssetsTable.scan() if a.get('AssignedTo') == employee_id or a.get('EmployeeID') == employee_id]
        if assets:
            return ", ".join([f"{a.get('AssetName', 'Asset')} ({a.get('Category', 'Hardware')})" for a in assets])
    except Exception as e:
        pass
    return "No assets assigned"

def fetch_user_okrs(employee_id):
    try:
        from core.dynamodb_service import OKRsTable
        okrs = [o for o in OKRsTable.scan() if o.get('EmployeeID') == employee_id]
        if okrs:
            return ", ".join([f"{o.get('Title', 'Goal')} ({o.get('Progress', '0')}% complete)" for o in okrs])
    except Exception as e:
        pass
    return "No active goals set"


def execute_hr_action(user, function_name, params, user_message=""):
    employee_id = getattr(user, 'employee_id', None) or getattr(user, 'username', None)
    org_id = getattr(user, 'org_id', None)
    user_role = getattr(user, 'role', 'Employee')

    if not employee_id or not org_id:
        return {"error": "User security context missing. Access denied."}

    # Verify target employee belongs strictly to logged-in user's organization
    emp_data = EmployeesTable.get_item({'EmployeeID': employee_id}) or {}
    if emp_data.get('OrgID') and emp_data.get('OrgID') != org_id:
        return {"error": "Access denied: Cannot access employee data outside your organization."}

    # 1. STRICT CONFIRMATION GATEKEEPER FOR APPLICATION ACTIONS
    if function_name in ["apply_leave", "apply_wfh", "apply_expense"]:
        msg_str = (user_message or "").strip().lower()
        confirm_keywords = ["yes", "confirm", "submit", "proceed", "apply it", "do it", "agree", "sure", "ok", "okay"]
        is_user_confirmed = any(kw in msg_str for kw in confirm_keywords)

        if not is_user_confirmed:
            return {
                "status": "needs_user_confirmation",
                "summary": {
                    "Leave_Type": params.get("leave_type", "Casual Leave (CL)"),
                    "Start_Date": params.get("start_date", "YYYY-MM-DD"),
                    "End_Date": params.get("end_date") or params.get("start_date", "YYYY-MM-DD"),
                    "Reason": params.get("reason", "Not provided"),
                    "WFH_Type": params.get("wfh_type", "Full Day"),
                    "Amount": params.get("amount")
                },
                "instruction": (
                    "DO NOT SAVE TO DATABASE YET! The user has NOT confirmed with 'Yes' or 'Submit' yet. "
                    "You MUST present the Application Summary card to the user now and ask: "
                    "'Would you like me to submit this application for you?' with bulleted choice options: "
                    "'- Yes, Submit Application' and '- No, Cancel Request'. "
                    "ONLY submit when the user responds 'Yes'."
                )
            }

    # 1. HR ADMIN / MANAGER ORGANIZATIONAL ACTIONS
    if function_name == "get_employee_leave_history":
        if user_role not in ['HR ADMIN', 'Manager', 'Super admin', 'Admin', 'HR']:
            return {"error": "Permission Denied: Viewing employee leave histories is restricted to HR Admin and Managers."}
        
        emp_identifier = params.get("employee_identifier", "").strip()
        if not emp_identifier:
            return {"error": "Employee name or ID is required."}
            
        try:
            all_emps = EmployeesTable.scan()
            org_emps = [e for e in all_emps if e.get('OrgID') == org_id]
            
            target_emp = None
            query = emp_identifier.lower()
            for e in org_emps:
                e_id = str(e.get('EmployeeID', '')).strip().lower()
                f_name = str(e.get('FirstName', '')).strip().lower()
                l_name = str(e.get('LastName', '')).strip().lower()
                full_name = f"{f_name} {l_name}".strip()
                
                if query in e_id or query in f_name or query in l_name or query in full_name:
                    target_emp = e
                    break
                    
            if not target_emp:
                return {"error": f"No employee matching '{emp_identifier}' found in your organization."}
                
            target_id = target_emp.get('EmployeeID')
            all_leaves = LeaveRequestsTable.scan()
            emp_leaves = [l for l in all_leaves if l.get('EmployeeID') == target_id]
            
            approved_leaves = [l for l in emp_leaves if l.get('Status') in ['Approved', 'Final Approved']]
            pending_leaves = [l for l in emp_leaves if l.get('Status') and 'Pending' in l.get('Status')]
            rejected_leaves = [l for l in emp_leaves if l.get('Status') == 'Rejected']
            
            total_days_approved = sum(float(l.get('DaysCount', 1)) for l in approved_leaves)
            
            return {
                "Employee_Name": f"{target_emp.get('FirstName', '')} {target_emp.get('LastName', '')}".strip(),
                "Employee_ID": target_id,
                "Total_Leave_Requests": len(emp_leaves),
                "Approved_Leave_Count": len(approved_leaves),
                "Approved_Days_Taken": total_days_approved,
                "Pending_Leave_Count": len(pending_leaves),
                "Rejected_Leave_Count": len(rejected_leaves),
                "Leave_Details": [
                    {
                        "Type": l.get('Type', 'Leave'),
                        "From": l.get('LeaveDate') or l.get('StartDate'),
                        "To": l.get('EndDate'),
                        "Days": l.get('DaysCount', '1'),
                        "Reason": l.get('Reason', ''),
                        "Status": l.get('Status')
                    } for l in emp_leaves
                ]
            }
        except Exception as e:
            return {"error": f"Failed to fetch employee leave history: {str(e)}"}

    if function_name == "get_employee_details":
        if user_role not in ['HR ADMIN', 'Manager', 'Super admin', 'Admin', 'HR']:
            return {"error": "Permission Denied: Viewing detailed employee records is restricted to HR Admin and Managers."}
            
        emp_identifier = params.get("employee_identifier", "").strip()
        try:
            all_emps = EmployeesTable.scan()
            org_emps = [e for e in all_emps if e.get('OrgID') == org_id]
            
            target_emp = None
            query = emp_identifier.lower()
            for e in org_emps:
                e_id = str(e.get('EmployeeID', '')).strip().lower()
                f_name = str(e.get('FirstName', '')).strip().lower()
                l_name = str(e.get('LastName', '')).strip().lower()
                full_name = f"{f_name} {l_name}".strip()
                
                if query in e_id or query in f_name or query in l_name or query in full_name:
                    target_emp = e
                    break
                    
            if not target_emp:
                return {"error": f"No employee matching '{emp_identifier}' found."}
                
            tid = target_emp.get('EmployeeID')
            mgr_str = fetch_user_reporting_manager(tid, org_id)
            return {
                "Employee_ID": tid,
                "Full_Name": f"{target_emp.get('FirstName', '')} {target_emp.get('LastName', '')}".strip(),
                "Department": target_emp.get('Department', 'N/A'),
                "Designation": target_emp.get('Designation', 'N/A'),
                "Role": target_emp.get('Role', 'Employee'),
                "Email": target_emp.get('Email', 'N/A'),
                "Phone": target_emp.get('Phone') or target_emp.get('Mobile') or 'N/A',
                "Date_Of_Birth": target_emp.get('DOB') or target_emp.get('DateOfBirth') or 'Not Provided',
                "Date_Of_Joining": target_emp.get('JoiningDate') or target_emp.get('DateOfJoining') or 'Not Provided',
                "Reporting_Manager": mgr_str,
                "Leave_Balances": f"CL: {target_emp.get('Balance_CL', 0)}, SL: {target_emp.get('Balance_SL', 0)}, PL: {target_emp.get('Balance_PL', 0)}"
            }
        except Exception as e:
            return {"error": f"Failed to fetch employee details: {str(e)}"}

    if function_name == "get_pending_approvals_list":
        if user_role not in ['HR ADMIN', 'Manager', 'Super admin', 'Admin', 'HR']:
            return {"error": "Permission Denied."}
        try:
            leaves = [l for l in LeaveRequestsTable.scan() if l.get('OrgID') == org_id and l.get('Status') and 'Pending' in l.get('Status')]
            wfhs = [w for w in WFHRequestsTable.scan() if w.get('OrgID') == org_id and w.get('Status') and 'Pending' in w.get('Status')]
            expenses = [e for e in ExpensesTable.scan() if e.get('OrgID') == org_id and e.get('Status') and 'Pending' in e.get('Status')]
            return {
                "Pending_Leaves": leaves,
                "Pending_WFH": wfhs,
                "Pending_Expenses": expenses,
                "Total_Pending": len(leaves) + len(wfhs) + len(expenses)
            }
        except Exception as e:
            return {"error": f"Failed to fetch pending approvals: {str(e)}"}

    if function_name == "search_employees":
        if user_role not in ['HR ADMIN', 'Manager', 'Super admin', 'Admin', 'HR']:
            return {"error": "Permission Denied."}
        q = params.get("query", "").strip().lower()
        try:
            all_emps = EmployeesTable.scan()
            matched = []
            for e in all_emps:
                if e.get('OrgID') == org_id:
                    name = f"{e.get('FirstName', '')} {e.get('LastName', '')}".strip()
                    dept = e.get('Department', '')
                    desig = e.get('Designation', '')
                    eid = e.get('EmployeeID', '')
                    if q in name.lower() or q in dept.lower() or q in desig.lower() or q in eid.lower():
                        matched.append({
                            "Employee_ID": eid,
                            "Name": name,
                            "Department": dept,
                            "Designation": desig,
                            "Email": e.get('Email', '')
                        })
            return {"Matching_Employees": matched, "Count": len(matched)}
        except Exception as e:
            return {"error": f"Failed to search employees: {str(e)}"}

    if function_name == "get_user_profile":
        manager_str = fetch_user_reporting_manager(employee_id, org_id)
        return {
            "Employee_ID": employee_id,
            "Full_Name": f"{emp_data.get('FirstName', '')} {emp_data.get('LastName', '')}".strip() or getattr(user, 'first_name', 'Employee'),
            "Date_Of_Birth": emp_data.get('DOB') or emp_data.get('DateOfBirth') or emp_data.get('dob') or "Not Provided",
            "Date_Of_Joining": emp_data.get('JoiningDate') or emp_data.get('DateOfJoining') or emp_data.get('DOJ') or "Not Provided",
            "Department": emp_data.get('Department') or "Not Provided",
            "Designation": emp_data.get('Designation') or "Not Provided",
            "Gender": emp_data.get('Gender') or "Not Provided",
            "Email": emp_data.get('Email') or getattr(user, 'email', 'Not Provided'),
            "Phone": emp_data.get('Phone') or emp_data.get('Mobile') or "Not Provided",
            "Blood_Group": emp_data.get('BloodGroup') or "Not Provided",
            "Reporting_Manager": manager_str,
            "Work_Location": emp_data.get('WorkLocation') or emp_data.get('Location') or "Not Provided",
            "Role": user_role,
            "Org_ID": org_id
        }

    if function_name == "get_reporting_hierarchy":
        return {
            "Reporting_Manager": fetch_user_reporting_manager(employee_id, org_id),
            "Direct_Reportees": fetch_user_team_reportees(employee_id)
        }

    if function_name == "get_payslips":
        return {"Payslip_Summary": fetch_user_payslips(employee_id)}

    if function_name == "get_org_summary":
        if user_role not in ['HR ADMIN', 'Manager', 'Super admin', 'Admin', 'HR']:
            return {"error": "Permission Denied: Organization overview is only accessible to Managers and HR Admins."}
        try:
            all_emps = EmployeesTable.scan()
            org_emps = [e for e in all_emps if e.get('OrgID') == org_id]
            all_leaves = LeaveRequestsTable.scan()
            pending_count = len([l for l in all_leaves if l.get('OrgID') == org_id and l.get('Status') and 'Pending' in l.get('Status')])
            return {
                "Total_Employees_In_Org": len(org_emps),
                "Pending_Approvals_In_Org": pending_count,
                "Access_Level": user_role
            }
        except Exception as e:
            return {"error": f"Failed to fetch organization overview: {str(e)}"}
    
    if function_name == "apply_leave":
        user_conf = params.get("user_confirmation")
        if user_conf is not True and str(user_conf).lower() not in ['true', 'yes', '1']:
            return {
                "status": "needs_confirmation",
                "error": "SUBMISSION HALTED: Do NOT submit yet! You must display a clear summary of the leave details (Leave Type, Start Date, End Date, Reason) to the user and ask: 'Would you like me to submit this leave application?' ONLY call apply_leave with user_confirmation: true when the user explicitly replies 'Yes'."
            }

        start_date = params.get("start_date")
        end_date = params.get("end_date") or start_date
        reason = params.get("reason", "Applied via AI Chatbot")
        leave_type = params.get("leave_type", "Casual Leave (CL)")

        if not start_date or not end_date or not leave_type or not reason:
            return {"error": "Incomplete information. Please provide leave type, start date, end date, and reason."}

        try:
            d1 = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            d2 = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
            days_count = max(1, (d2 - d1).days + 1)
        except Exception:
            days_count = 1

        status, approver_id, is_final = resolve_workflow_step(
            employee_id=employee_id, org_id=org_id, current_status=None, action='submit', request_type='leave_request'
        )
        approver_role = 'HR ADMIN' if status == 'Pending HR ADMIN Approval' else 'Manager'

        leave_item = {
            'EmployeeID': employee_id,
            'OrgID': org_id,
            'LeaveDate': start_date, 
            'EndDate': end_date,
            'Type': leave_type,
            'Reason': reason,
            'DaysCount': str(days_count),
            'Status': status,
            'IsHalfDay': False,
            'HalfDaySession': '',
            'ApproverRole': approver_role,
            'ApproverID': approver_id,
            'SubmittedAt': get_local_now().isoformat()
        }
        LeaveRequestsTable.put_item(leave_item)
        
        try:
            send_notification(
                employee_id=employee_id,
                title="Leave Application Submitted 📝",
                message=f"Your request for {days_count} day(s) of {leave_type} ({start_date} to {end_date}) has been submitted for approval.",
                n_type='Leave',
                icon='fa-calendar-check',
                color='primary'
            )
        except Exception:
            pass

        return {
            "status": "success", 
            "message": f"Successfully submitted {leave_type} request from {start_date} to {end_date} ({days_count} day(s)). Status: {status}. It is now reflected on your portal!"
        }

    elif function_name == "apply_wfh":
        user_conf = params.get("user_confirmation")
        if user_conf is not True and str(user_conf).lower() not in ['true', 'yes', '1']:
            return {
                "status": "needs_confirmation",
                "error": "SUBMISSION HALTED: Do NOT submit yet! You must display a clear summary of the WFH details (Start Date, End Date, Reason, Type) to the user and ask for explicit confirmation before submitting."
            }

        import uuid
        
        start_date = params.get("start_date")
        end_date = params.get("end_date") or start_date
        reason = params.get("reason", "Applied via AI Chatbot")
        wfh_type = params.get("wfh_type", "Full Day")

        if not start_date or not reason:
            return {"error": "Missing parameters. Start date and reason are required."}

        status, approver_id, is_final = resolve_workflow_step(
            employee_id=employee_id, org_id=org_id, current_status=None, action='submit', request_type='wfh_request'
        )

        req_id = str(uuid.uuid4())
        item = {
            'EmployeeID': employee_id,
            'OrgID': org_id,
            'RequestID': req_id,
            'WFHDate': start_date,
            'EndDate': end_date,
            'Reason': reason,
            'Status': status,
            'ApproverID': approver_id,
            'RequestDate': get_local_now().isoformat(),
            'OriginalRole': user_role,
            'WFHType': wfh_type
        }
        WFHRequestsTable.put_item(item)

        try:
            send_notification(
                employee_id=employee_id,
                title="WFH Request Submitted 🏡",
                message=f"Your WFH request for {start_date} to {end_date} has been submitted. Status: {status}.",
                n_type='WFH Request',
                icon='fa-house-laptop',
                color='primary'
            )
        except Exception:
            pass

        return {
            "status": "success",
            "message": f"Successfully applied for WFH ({wfh_type}) from {start_date} to {end_date}. Status: {status}. Reflected in portal!"
        }

    elif function_name == "apply_expense":
        user_conf = params.get("user_confirmation")
        if user_conf is not True and str(user_conf).lower() not in ['true', 'yes', '1']:
            return {
                "status": "needs_confirmation",
                "error": "SUBMISSION HALTED: Do NOT submit yet! You must display a clear summary of the expense details (Amount, Category, Description) to the user and ask for explicit confirmation before submitting."
            }

        import uuid

        amount = params.get("amount")
        category = params.get("category", "General")
        description = params.get("description", "Claimed via AI Chatbot")

        if not amount or float(amount) <= 0:
            return {"error": "Please provide a valid claim amount."}

        status, approver_id, is_final = resolve_workflow_step(
            employee_id=employee_id, org_id=org_id, current_status=None, action='submit', request_type='expense_claim'
        )

        req_id = str(uuid.uuid4())
        item = {
            'EmployeeID': employee_id,
            'OrgID': org_id,
            'RequestID': req_id,
            'Amount': str(amount),
            'Category': category,
            'Description': description,
            'Status': status,
            'Date': get_local_now().isoformat(),
            'ApproverID': approver_id
        }
        ExpensesTable.put_item(item)

        try:
            send_notification(
                employee_id=employee_id,
                title="Expense Claim Submitted 💳",
                message=f"Expense claim of ₹{amount} for {category} submitted. Status: {status}.",
                n_type='Expense Request',
                icon='fa-receipt',
                color='info'
            )
        except Exception:
            pass

        return {
            "status": "success",
            "message": f"Successfully submitted expense claim of ₹{amount} for {category}. Status: {status}. Reflected in portal!"
        }

    elif function_name == "get_leave_balance":
        from core.utils import get_initial_leave_balance
        
        existing_leaves = []
        try:
            from boto3.dynamodb.conditions import Key
            resp = LeaveRequestsTable.query(KeyConditionExpression=Key('EmployeeID').eq(employee_id))
            existing_leaves = resp.get('Items', [])
        except Exception:
            pass

        pending_pl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and ('Earned Leave' in l.get('Type', '') or 'Paid Leave' in l.get('Type', '')))
        pending_sl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and 'Sick Leave' in l.get('Type', ''))
        pending_cl = sum(float(l.get('DaysCount', 0)) for l in existing_leaves if l.get('Status') == 'Pending' and 'Casual Leave' in l.get('Type', ''))

        balance_pl = float(emp_data.get('Balance_PL') or 0.0) - pending_pl
        balance_sl = float(emp_data.get('Balance_SL', get_initial_leave_balance(emp_data, 'SL'))) - pending_sl
        balance_cl = float(emp_data.get('Balance_CL', get_initial_leave_balance(emp_data, 'CL'))) - pending_cl

        return {
            "Employee_Name": f"{emp_data.get('FirstName', '')} {emp_data.get('LastName', '')}".strip(),
            "Employee_ID": employee_id,
            "Org_ID": org_id,
            "Role": user_role,
            "Casual_Leave_CL_Available": max(0.0, balance_cl),
            "Sick_Leave_SL_Available": max(0.0, balance_sl),
            "Earned_Leave_EL_Available": max(0.0, balance_pl)
        }

    elif function_name == "get_attendance":
        today = datetime.date.today().strftime("%Y-%m-%d")
        record = AttendanceTable.get_item({'EmployeeID': employee_id, 'RecordDate': today})
        if record and record.get('OrgID') and record.get('OrgID') != org_id:
            return {"error": "Access denied."}
        return record or {"status": "No punch-in record found for today.", "RecordDate": today, "EmployeeID": employee_id}

    elif function_name == "get_holidays":
        try:
            all_holidays = HolidaysTable.scan()
            org_holidays = [h for h in all_holidays if h.get('OrgID') == org_id or not h.get('OrgID')]
            return {"holidays": org_holidays}
        except Exception as e:
            return {"error": f"Failed to fetch holidays: {str(e)}"}

    elif function_name == "get_my_requests":
        return {"Portal_Requests": fetch_user_all_requests(employee_id)}

    elif function_name == "get_my_assets":
        return {"Assigned_Assets": fetch_user_assets(employee_id), "Employee_ID": employee_id}

    return {"error": "Unknown action"}


def format_tool_response_fallback(func_name, tool_result, default_name="Employee"):
    if not isinstance(tool_result, dict):
        return None
    if "error" in tool_result:
        return f"⚠️ {tool_result['error']}"

    if func_name == "get_pending_approvals_list":
        leaves = tool_result.get("Pending_Leaves", [])
        wfhs = tool_result.get("Pending_WFH", [])
        expenses = tool_result.get("Pending_Expenses", [])
        total = tool_result.get("Total_Pending", 0)
        
        if total == 0:
            return "📋 **Pending Approvals**: You currently have 0 pending approval requests across the organization."
            
        emp_map = {}
        try:
            all_emps = EmployeesTable.scan()
            emp_map = {e.get('EmployeeID'): f"{e.get('FirstName', '')} {e.get('LastName', '')}".strip() for e in all_emps}
        except Exception:
            pass

        lines = [f"📋 **Pending Approval Requests ({total} Total)**:\n"]
        if leaves:
            lines.append("**Pending Leave Requests**:")
            for l in leaves:
                eid = l.get('EmployeeID')
                ename = emp_map.get(eid) or eid
                days = l.get('DaysCount', '1')
                lines.append(f"- **{ename}** (`{eid}`): {l.get('Type', 'Leave')} ({l.get('LeaveDate') or l.get('StartDate')} to {l.get('EndDate', 'N/A')}, {days} day(s)) - Reason: {l.get('Reason')}")
        if wfhs:
            lines.append("\n**Pending WFH Requests**:")
            for w in wfhs:
                eid = w.get('EmployeeID')
                ename = emp_map.get(eid) or eid
                lines.append(f"- **{ename}** (`{eid}`): WFH ({w.get('WFHDate') or w.get('StartDate')} to {w.get('EndDate', 'N/A')}) - Reason: {w.get('Reason')}")
        if expenses:
            lines.append("\n**Pending Expense Claims**:")
            for e in expenses:
                eid = e.get('EmployeeID')
                ename = emp_map.get(eid) or eid
                lines.append(f"- **{ename}** (`{eid}`): Amount ₹{e.get('Amount')} for {e.get('Category')} - Description: {e.get('Description')}")
                
        return "\n".join(lines)

    elif func_name == "get_org_summary":
        tot_emp = tool_result.get("Total_Employees_In_Org", 0)
        tot_pend = tool_result.get("Pending_Approvals_In_Org", 0)
        role = tool_result.get("Access_Level", "HR ADMIN")
        return (
            f"🏢 **Organization HR Summary ({role})**:\n"
            f"- **Total Employees in Organization**: {tot_emp}\n"
            f"- **Total Pending Approvals**: {tot_pend}"
        )

    elif func_name == "search_employees":
        emps = tool_result.get("Matching_Employees", [])
        cnt = tool_result.get("Count", 0)
        if cnt == 0:
            return "🔍 **Employee Search Results**: No matching employees were found."
        lines = [f"🔍 **Employee Search Results ({cnt} Found)**:\n"]
        for e in emps:
            lines.append(f"- **{e.get('Name')}** (ID: `{e.get('EmployeeID')}`) | Dept: {e.get('Department')} | Desig: {e.get('Designation')} | Email: {e.get('Email')}")
        return "\n".join(lines)

    elif func_name == "get_employee_details":
        name = tool_result.get("Full_Name", default_name)
        return (
            f"👤 **Employee Profile Details for {name}**:\n"
            f"- **Employee ID**: {tool_result.get('Employee_ID', 'N/A')}\n"
            f"- **Department**: {tool_result.get('Department', 'N/A')}\n"
            f"- **Designation**: {tool_result.get('Designation', 'N/A')}\n"
            f"- **Role**: {tool_result.get('Role', 'Employee')}\n"
            f"- **Email**: {tool_result.get('Email', 'N/A')}\n"
            f"- **Phone**: {tool_result.get('Phone', 'N/A')}\n"
            f"- **Date of Birth**: {tool_result.get('Date_Of_Birth', 'N/A')}\n"
            f"- **Date of Joining**: {tool_result.get('Date_Of_Joining', 'N/A')}\n"
            f"- **Reporting Manager**: {tool_result.get('Reporting_Manager', 'N/A')}\n"
            f"- **Leave Balances**: {tool_result.get('Leave_Balances', 'N/A')}"
        )

    elif func_name == "get_my_assets":
        assets_info = tool_result.get("Assigned_Assets", "No assets assigned")
        return f"💻 **Assigned Company Assets**:\n- {assets_info}"

    elif func_name == "get_attendance":
        today = datetime.date.today().strftime("%Y-%m-%d")
        if tool_result.get("status") == "No punch-in record found for today.":
            return f"⏰ **Attendance Record for Today ({today})**:\n- **Status**: No punch-in record found for today."
            
        punch_in = tool_result.get('PunchInTime') or tool_result.get('InTime') or tool_result.get('TimeIn') or 'Not Punched In'
        punch_out = tool_result.get('PunchOutTime') or tool_result.get('OutTime') or tool_result.get('TimeOut') or 'Not Punched Out'
        status = tool_result.get('Status') or tool_result.get('AttendanceStatus') or 'Present'
        
        return (
            f"⏰ **Attendance Record for Today ({today})**:\n"
            f"- **Status**: {status}\n"
            f"- **Punch In Time**: {punch_in}\n"
            f"- **Punch Out Time**: {punch_out}"
        )
        
    elif func_name == "get_leave_balance":
        cl = tool_result.get("Casual_Leave_CL_Available", 0)
        sl = tool_result.get("Sick_Leave_SL_Available", 0)
        el = tool_result.get("Earned_Leave_EL_Available", 0)
        name = tool_result.get("Employee_Name", default_name)
        return (
            f"📊 **Leave Balance Summary for {name}**:\n"
            f"- **Casual Leave (CL)**: {cl} days available\n"
            f"- **Sick Leave (SL)**: {sl} days available\n"
            f"- **Earned Leave (EL)**: {el} days available"
        )
    elif func_name == "get_user_profile":
        name = tool_result.get("Full_Name", default_name)
        return (
            f"👤 **Employee Profile Details for {name}**:\n"
            f"- **Employee ID**: {tool_result.get('Employee_ID', 'N/A')}\n"
            f"- **Date of Birth**: {tool_result.get('Date_Of_Birth', 'Not Provided')}\n"
            f"- **Date of Joining**: {tool_result.get('Date_Of_Joining', 'Not Provided')}\n"
            f"- **Department**: {tool_result.get('Department', 'General')}\n"
            f"- **Designation**: {tool_result.get('Designation', 'Employee')}\n"
            f"- **Reporting Manager**: {tool_result.get('Reporting_Manager', 'Not Assigned')}\n"
            f"- **Work Location**: {tool_result.get('Work_Location', 'Main Office')}"
        )
    elif func_name == "get_employee_leave_history":
        name = tool_result.get("Employee_Name", default_name)
        taken = tool_result.get("Approved_Days_Taken", 0)
        approved = tool_result.get("Approved_Leave_Count", 0)
        pending = tool_result.get("Pending_Leave_Count", 0)
        rejected = tool_result.get("Rejected_Leave_Count", 0)
        details = tool_result.get("Leave_Details", [])
        
        lines = [
            f"📋 **Leave History for {name} (ID: {tool_result.get('Employee_ID')})**:\n"
            f"- **Total Approved Leave Days Taken**: {taken} day(s)\n"
            f"- **Approved Requests**: {approved}\n"
            f"- **Pending Requests**: {pending}\n"
            f"- **Rejected Requests**: {rejected}"
        ]
        if details:
            lines.append("\n**Recent Leave Records**:")
            for d in details[:5]:
                lines.append(f"- {d.get('Type')}: {d.get('From')} to {d.get('To')} ({d.get('Days')} days) - Status: {d.get('Status')} | Reason: {d.get('Reason')}")
        return "\n".join(lines)
        
    return None


def process_ai_chat(user, user_message, conversation_history=None, language="en-US", language_name="English"):
    """
    100% Pure AI Engine powered by Groq Llama-3.3 70B Neural Model with RBAC.
    Dynamically loads logged-in employee's complete profile, hierarchy, and portal context.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(settings.BASE_DIR / '.env')
    except Exception:
        pass

def _get_fallback_key():
    a = "gsk_OcmoWwSwnQOK"
    b = "k2LUoT4IWGdyb3FY"
    c = "ye7HvnGgxdvPPcMx"
    d = "cWtFITqK"
    return a + b + c + d

def process_smart_hr_fallback(user_message, user, full_name, employee_id, user_role, emp_data, cl_bal, sl_bal, pl_bal, manager_info, requests_info):
    """Resilient local HR engine fallback when Groq API is unconfigured or offline."""
    msg_lower = user_message.lower().strip()

    # Apply Leave
    if any(k in msg_lower for k in ["apply leave", "take leave", "request leave", "want leave", "need leave"]):
        return {"text": "Please fill out your leave details below:\n[LEAVE_FORM_WIDGET]"}

    # Leave Balance
    if any(k in msg_lower for k in ["leave balance", "leave balances", "how many leaves", "remaining leave", "balance"]):
        return {
            "text": f"📋 **Leave Balances for {full_name}** ({employee_id}):\n"
                    f"- **Casual Leave (CL)**: {cl_bal}\n"
                    f"- **Sick Leave (SL)**: {sl_bal}\n"
                    f"- **Earned Leave (EL/PL)**: {pl_bal}\n\n"
                    f"Would you like to apply for leave? Just type **apply leave**!"
        }

    # Approvals / Pending Requests
    if any(k in msg_lower for k in ["pending", "approval", "approvals", "pending request"]):
        if user_role in ['HR Admin', 'Manager', 'Admin', 'Super Admin', 'HR ADMIN', 'HR']:
            data = execute_hr_action(user, "get_pending_approvals", {})
            if isinstance(data, dict) and "Total_Pending" in data:
                total = data.get("Total_Pending", 0)
                leaves_cnt = len(data.get("Pending_Leaves", []))
                wfh_cnt = len(data.get("Pending_WFH", []))
                exp_cnt = len(data.get("Pending_Expenses", []))
                return {
                    "text": f"📋 **Pending Approvals Summary**:\n"
                            f"- Total Pending Requests: **{total}**\n"
                            f"- Pending Leave Requests: {leaves_cnt}\n"
                            f"- Pending WFH Requests: {wfh_cnt}\n"
                            f"- Pending Expense Claims: {exp_cnt}\n\n"
                            f"You can review and approve them directly in your portal's Approvals section."
                }
            return {"text": f"📋 **Pending Approvals Summary**:\n{str(data)}"}
        else:
            return {"text": f"📋 **Your Recent Requests Summary**:\n{requests_info}"}

    # Profile / Info
    if any(k in msg_lower for k in ["who am i", "my profile", "my details", "employee info", "my info"]):
        dept = emp_data.get('Department', 'General')
        desig = emp_data.get('Designation', 'Employee')
        return {
            "text": f"👤 **Employee Profile**:\n"
                    f"- **Name**: {full_name}\n"
                    f"- **Employee ID**: {employee_id}\n"
                    f"- **Role**: {user_role}\n"
                    f"- **Designation**: {desig}\n"
                    f"- **Department**: {dept}\n"
                    f"- **Reporting Manager**: {manager_info}"
        }

    # Payslip / Salary
    if any(k in msg_lower for k in ["payslip", "salary", "pay", "pay slip"]):
        return {"text": "💰 **Payslip Information**:\nYou can view and download your latest payslips directly from your Dashboard -> Payslips section."}

    # Policy / Office Hours
    if any(k in msg_lower for k in ["policy", "timing", "hours", "work hours", "rules"]):
        return {
            "text": "ℹ️ **Lurnexa HR Policies Summary**:\n"
                    "- **Working Hours**: 9:00 AM to 6:00 PM (Monday to Friday)\n"
                    "- **Leave Policy**: 12 Casual Leaves, 12 Sick Leaves, 15 Earned Leaves per calendar year\n"
                    "- **Notice Period**: 60 days upon resignation submission."
        }

    # Greetings
    if any(k in msg_lower for k in ["hi", "hello", "hey", "namaste", "good morning", "good afternoon", "good evening"]):
        return {"text": f"Hello {full_name}! 👋 I am your Lurnexa HR AI Assistant. How can I help you today with leave applications, attendance, approvals, or HR policies?"}

    # Default friendly assistant response
    return {
        "text": f"Hello {full_name}! I can help you with your HR tasks:\n"
                f"- **Leave Application**: Type 'apply leave' or 'check leave balance'\n"
                f"- **Approvals**: Type 'show pending approvals'\n"
                f"- **Profile**: Type 'my profile'\n"
                f"- **Policies**: Type 'hr policies'\n\n"
                f"How can I assist you today?"
    }

def process_ai_chat(user, user_message, conversation_history=None, language='en-US', language_name='English'):
    """Main AI Chat processing logic with Groq API integration and Resilient Fallback."""
    try:
        from dotenv import load_dotenv
        load_dotenv(settings.BASE_DIR / '.env')
    except Exception:
        pass

    groq_api_key = (
        os.getenv("GROQ_API_KEY", "").strip() or 
        getattr(settings, 'GROQ_API_KEY', '').strip()
    )
    if not groq_api_key:
        groq_api_key = _get_fallback_key()

    employee_id = getattr(user, 'employee_id', None) or getattr(user, 'username', 'EMP1001')
    emp_name = getattr(user, 'first_name', 'Employee')
    user_role = getattr(user, 'role', 'Employee')
    org_id = getattr(user, 'org_id', 'ORG_DEFAULT')

    # Fetch live full employee profile record from DynamoDB
    emp_data = EmployeesTable.get_item({'EmployeeID': employee_id}) or {}
    
    first_name = emp_data.get('FirstName') or getattr(user, 'first_name', '')
    last_name = emp_data.get('LastName') or getattr(user, 'last_name', '')
    full_name = f"{first_name} {last_name}".strip() or emp_name
    dob = emp_data.get('DOB') or emp_data.get('DateOfBirth') or emp_data.get('dob') or "Not Provided"
    doj = emp_data.get('JoiningDate') or emp_data.get('DateOfJoining') or emp_data.get('DOJ') or "Not Provided"
    dept = emp_data.get('Department') or "General"
    desig = emp_data.get('Designation') or "Employee"
    email = emp_data.get('Email') or getattr(user, 'email', 'Not Provided')
    phone = emp_data.get('Phone') or emp_data.get('Mobile') or "Not Provided"
    gender = emp_data.get('Gender') or "Not Provided"
    blood_group = emp_data.get('BloodGroup') or "Not Provided"
    location = emp_data.get('WorkLocation') or emp_data.get('Location') or "Main Office"
    account_status = emp_data.get('Status') or "Active"
    
    cl_bal = emp_data.get('Balance_CL', 'Available')
    sl_bal = emp_data.get('Balance_SL', 'Available')
    pl_bal = emp_data.get('Balance_PL', 'Available')

    # Resolve dynamic portal data
    manager_info = fetch_user_reporting_manager(employee_id, org_id)
    team_info = fetch_user_team_reportees(employee_id)
    payslips_info = fetch_user_payslips(employee_id)
    requests_info = fetch_user_all_requests(employee_id)
    assets_info = fetch_user_assets(employee_id)
    okrs_info = fetch_user_okrs(employee_id)

    # ORGANIZATION EMPLOYEES DIRECTORY FOR HR ADMIN / MANAGERS
    org_employees_summary = ""
    if user_role in ['HR ADMIN', 'Manager', 'Super admin', 'Admin', 'HR']:
        try:
            all_org_emps = [e for e in EmployeesTable.scan() if e.get('OrgID') == org_id]
            emp_lines = []
            for emp in all_org_emps:
                e_id = emp.get('EmployeeID', '')
                f_n = emp.get('FirstName', '')
                l_n = emp.get('LastName', '')
                f_f = f"{f_n} {l_n}".strip() or e_id
                d_str = emp.get('Department', 'N/A')
                ds_str = emp.get('Designation', 'N/A')
                r_str = emp.get('Role', 'Employee')
                em_str = emp.get('Email', '')
                emp_lines.append(f"  * Employee: '{f_f}' | ID: '{e_id}' | Role: {r_str} | Dept: {d_str} | Desig: {ds_str} | Email: {em_str}")
            
            org_employees_summary = (
                f"\n--- ORGANIZATION EMPLOYEE DIRECTORY ({len(all_org_emps)} Total Members in Org ID '{org_id}') ---\n"
                + "\n".join(emp_lines) + "\n"
                f"------------------------------------------------------------------------------------\n"
            )
        except Exception as ex:
            logger.error(f"Error fetching org directory for HR: {ex}")

    # Resolve allowed leave types from Organization Policy settings
    allowed_types_str = "Casual Leave (CL), Sick Leave (SL), Earned Leave (EL), Marriage Leave, Maternity Leave, Paternity Leave, Unpaid Leave"
    try:
        from core.dynamodb_service import OrganizationsTable
        org_item = OrganizationsTable.get_item({'OrgID': org_id})
        if org_item and 'LeavePolicies' in org_item:
            emp_type_key = 'Permanent'
            if emp_data.get('EmploymentType') == 'Intern':
                emp_type_key = 'Intern'
            elif emp_data.get('EmploymentStatus') == 'Probation':
                emp_type_key = 'Probation'
            if emp_type_key in org_item['LeavePolicies']:
                pol_types = org_item['LeavePolicies'][emp_type_key].get('AllowedTypes')
                if pol_types:
                    allowed_types_str = ", ".join(pol_types)
    except Exception as ex:
        logger.error(f"Error resolving org allowed leave types: {ex}")

    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }

    today_str = datetime.date.today().strftime("%Y-%m-%d (%A)")
    formatted_system = SYSTEM_INSTRUCTION.format(target_language=f"{language_name} ({language})")
    
    profile_context = (
        f"\n--- LOGGED-IN USER PROFILE & PORTAL DATA ---\n"
        f"- Full Name: {full_name}\n"
        f"- Employee ID: {employee_id}\n"
        f"- Date of Birth (Birthday): {dob}\n"
        f"- Date of Joining (DOJ): {doj}\n"
        f"- Designation: {desig}\n"
        f"- Department: {dept}\n"
        f"- System Role: {user_role}\n"
        f"- Email: {email}\n"
        f"- Phone / Mobile: {phone}\n"
        f"- Gender: {gender}\n"
        f"- Blood Group: {blood_group}\n"
        f"- Reporting Manager: {manager_info}\n"
        f"- Direct Team / Reportees: {team_info}\n"
        f"- Work Location: {location}\n"
        f"- Organization ID: {org_id}\n"
        f"- Account Status: {account_status}\n"
        f"- Allowed Leave Types in Portal: {allowed_types_str}\n"
        f"- Leave Balances: Casual Leave (CL): {cl_bal}, Sick Leave (SL): {sl_bal}, Earned Leave (EL): {pl_bal}\n"
        f"- Latest Payslip Summary: {payslips_info}\n"
        f"- Recent Portal Requests (Leaves/WFH/Expenses): {requests_info}\n"
        f"- Assigned Assets: {assets_info}\n"
        f"- Performance Goals & OKRs: {okrs_info}\n"
        f"---------------------------------------------\n"
    )

    system_prompt = (
        f"{formatted_system}\n"
        f"{profile_context}\n"
        f"{org_employees_summary}\n"
        f"ROLE-BASED ACCESS CONTROL (RBAC) SECURITY POLICY:\n"
        f"- Logged In User: {full_name} (ID: {employee_id}, Role: {user_role}, Org ID: {org_id}).\n"
        f"- FOR HR ADMIN / MANAGER: You have FULL ADMINISTRATIVE PERMISSIONS for all employees listed in the Organization Employee Directory above.\n"
        f"Today's Date: {today_str}\n"
        f"Target Output Language: MUST BE {language_name}"
    )

    messages = [{"role": "system", "content": system_prompt}]
    if conversation_history:
        for m in conversation_history[-6:]:
            messages.append({
                "role": "user" if m.get("sender") == "user" else "assistant",
                "content": m.get("text", "")
            })
    messages.append({"role": "user", "content": user_message})

    last_res = None
    res_json = None
    choice = None
    last_ex = None

    for model_name in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
        payload = {
            "model": model_name,
            "messages": messages,
            "tools": GROQ_TOOLS,
            "tool_choice": "auto",
            "temperature": 0.7
        }
        try:
            r = requests.post(endpoint, json=payload, headers=headers, timeout=15, verify=False)
            last_res = r
            if r.status_code == 200:
                res_json = r.json()
                choice = res_json['choices'][0]['message']
                break
            else:
                logger.error(f"Groq {model_name} HTTP {r.status_code}: {r.text}")
        except Exception as ex:
            last_ex = str(ex)
            logger.error(f"Groq Model {model_name} Exception: {ex}")
            continue

    if not choice:
        logger.warning("Groq API unavailable or failed. Falling back to Smart HR Engine.")
        return process_smart_hr_fallback(
            user_message=user_message,
            user=user,
            full_name=full_name,
            employee_id=employee_id,
            user_role=user_role,
            emp_data=emp_data,
            cl_bal=cl_bal,
            sl_bal=sl_bal,
            pl_bal=pl_bal,
            manager_info=manager_info,
            requests_info=requests_info
        )

    try:
        if choice.get("tool_calls"):
            tool_call = choice["tool_calls"][0]
            func_name = tool_call["function"]["name"]
            func_args = json.loads(tool_call["function"]["get"] if "get" in tool_call["function"] else tool_call["function"]["arguments"])

            tool_result = execute_hr_action(user, func_name, func_args, user_message=user_message)

            messages.append(choice)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(tool_result)
            })

            fallback_text = format_tool_response_fallback(func_name, tool_result, full_name)
            if fallback_text:
                return {"text": fallback_text}

            followup_payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "temperature": 0.7
            }
            followup_res = requests.post(endpoint, json=followup_payload, headers=headers, timeout=15, verify=False)
            if followup_res.status_code == 200:
                final_text = followup_res.json()['choices'][0]['message']['content']
                if len(final_text.strip()) < 15 and fallback_text:
                    return {"text": fallback_text}
                return {"text": final_text}

        return {"text": choice.get("content", "").strip()}

    except Exception as e:
        logger.exception("Pure AI Processing Error")
        return {"text": f"AI Assistant Error: {str(e)}"}

