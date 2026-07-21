import os
import django
import logging

# Configure logging to a file in the project directory
logging.basicConfig(
    filename='fix_prod_log.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logging.info("Starting fix_prod_db.py script...")

try:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
    django.setup()
    
    from core.dynamodb_service import EmployeesTable, UsersTable, PayrollApprovalsTable, initialize_dynamodb_tables
    from boto3.dynamodb.conditions import Key
    import bcrypt
    import uuid

    logging.info("Initializing DynamoDB tables on live environment...")
    initialize_dynamodb_tables()
    logging.info("DynamoDB tables check completed.")

    # Seed Platform Admin if not exists
    logging.info("Checking if Platform Admin user exists...")
    platform_email = 'lurnexasolution@gmail.com'
    existing_users = UsersTable.query(
        IndexName='EmailIndex',
        KeyConditionExpression=Key('Email').eq(platform_email)
    )
    if not existing_users:
        logging.info("Platform Admin not found. Seeding Platform Admin details...")
        user_id = str(uuid.uuid4())
        employee_id = 'LXP-PLAT-001'
        password = 'Password@123'
        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        user_item = {
            'UserID': user_id,
            'Email': platform_email,
            'Role': 'Platform Admin',
            'PasswordHash': hashed_pw,
            'EmployeeID': employee_id,
            'IsActive': True
        }
        UsersTable.put_item(user_item)
        
        employee_item = {
            'EmployeeID': employee_id,
            'UserID': user_id,
            'Email': platform_email,
            'FirstName': 'Lurnexa',
            'LastName': 'Technologies',
            'Department': 'Administration',
            'Designation': 'Platform Admin'
        }
        EmployeesTable.put_item(employee_item)
        logging.info("Successfully seeded Platform Admin user.")
    else:
        logging.info("Platform Admin user already exists.")
    
    from decimal import Decimal
    
    # 1. Find and update the employee
    target_emp = None
    all_emps = EmployeesTable.scan()
    logging.info(f"Found {len(all_emps)} employees in Lurnexa_Employees.")
    
    for emp in all_emps:
        emp_id = emp.get('EmployeeID', '')
        first_name = emp.get('FirstName', '')
        last_name = emp.get('LastName', '')
        full_name = f"{first_name} {last_name}".upper()
        
        logging.info(f"Employee ID: {emp_id}, Name: {full_name}, is_pf_applicable: {emp.get('is_pf_applicable')}")
        
        if "INTURI" in full_name or "YASHVANTH" in full_name or "LT2026002" in emp_id or "LT-26002" in emp_id:
            target_emp = emp
            logging.info(f"Matched target employee: {emp_id} - {full_name}")
            
    if target_emp:
        emp_id = target_emp['EmployeeID']
        # Update in database
        target_emp['is_pf_applicable'] = True
        # If PF_Balance is None or not present, set it to '0.0'
        if target_emp.get('PF_Balance') is None:
            target_emp['PF_Balance'] = '0.0'
        EmployeesTable.put_item(target_emp)
        logging.info(f"Successfully updated is_pf_applicable to True for {emp_id}.")
        
        # 2. Update pending payroll approval requests
        all_approvals = PayrollApprovalsTable.scan()
        logging.info(f"Found {len(all_approvals)} payroll approval requests.")
        
        for approval in all_approvals:
            req_id = approval.get('RequestID')
            batch_data = approval.get('BatchData', [])
            updated_batch = False
            
            for entry in batch_data:
                if entry.get('EmployeeID') == emp_id:
                    # Let's calculate the correct PF, deductions, and NetPay
                    # Let's read basic salary
                    payslip = entry.get('PayslipData', {})
                    basic = float(payslip.get('Basic', 0))
                    gross = float(payslip.get('GrossSalary', 0))
                    esi = float(payslip.get('ESI', 0))
                    pt = float(payslip.get('PT', 0))
                    tds = float(payslip.get('TDS', 0))
                    bonus = float(payslip.get('Bonus', 0))
                    
                    # Correct PF = 12% of basic
                    pf = round(0.12 * basic, 2)
                    total_deductions = round(pf + esi + pt + tds, 2)
                    net_pay = round((gross - total_deductions) + bonus, 2)
                    
                    logging.info(f"Before fix: PF={payslip.get('PF')}, Ded={payslip.get('TotalDeductions')}, Net={payslip.get('NetPay')}")
                    
                    payslip['PF'] = str(pf)
                    payslip['TotalDeductions'] = str(total_deductions)
                    payslip['NetPay'] = str(net_pay)
                    
                    logging.info(f"After fix: PF={pf}, Ded={total_deductions}, Net={net_pay}")
                    updated_batch = True
                    
            if updated_batch:
                # Recalculate TotalNetPay
                total_net = sum(float(b.get('PayslipData', {}).get('NetPay', 0)) for b in batch_data)
                approval['TotalNetPay'] = str(round(total_net, 2))
                approval['BatchData'] = batch_data
                PayrollApprovalsTable.put_item(approval)
                logging.info(f"Updated payroll approval request {req_id} with TotalNetPay {approval['TotalNetPay']}.")
    else:
        logging.warning("Target employee not found in database scan.")
        
except Exception as e:
    logging.exception(f"Error executing fix_prod_db.py: {e}")
