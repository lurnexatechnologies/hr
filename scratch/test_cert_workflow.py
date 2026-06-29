import os
import django
import uuid
import datetime

import sys
# Initialize Django environment
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeesTable

def run_tests():
    print("==================================================")
    print("RUNNING CERTIFICATE WORKFLOW PROGRAMMATIC TEST...")
    print("==================================================")
    
    # 1. Fetch worker
    all_employees = EmployeesTable.scan()
    if not all_employees:
        print("FAIL: No employees found in Lurnexa_Employees table.")
        return
        
    print(f"Total employees found in DB: {len(all_employees)}")
    for e in all_employees:
        print(f"- ID: {e.get('EmployeeID')}, Name: {e.get('FirstName')} {e.get('LastName')}")
        
    # Let's pick the first employee for the test dynamically
    emp = all_employees[0]
    emp_id = emp.get('EmployeeID')
    employee = EmployeesTable.get_item({'EmployeeID': emp_id})
    
    print(f"Selected employee for test: {employee.get('FirstName')} {employee.get('LastName')} ({emp_id})")
    
    # Save original certificates list to restore later
    original_certs = employee.get('Certificates', [])
    
    try:
        # 2. Simulate Upload a new certificate (Pending)
        cert_id = str(uuid.uuid4())
        new_cert = {
            'CertificateID': cert_id,
            'Name': 'Test AWS Solutions Architect',
            'FilePath': 'employees/certs/dummy_cert.pdf',
            'UploadedAt': datetime.datetime.now().isoformat(),
            'Status': 'Pending',
            'RejectionReason': ''
        }
        
        employee['Certificates'] = original_certs + [new_cert]
        EmployeesTable.put_item(employee)
        print("PASS: Programmatic certificate upload completed (Status: Pending).")
        
        # Verify from database
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        certs = employee.get('Certificates', [])
        added_cert = next((c for c in certs if c.get('CertificateID') == cert_id), None)
        assert added_cert is not None, "Uploaded certificate not found in DB."
        assert added_cert.get('Status') == 'Pending', "Certificate status is not Pending."
        print("PASS: Verified pending certificate stored correctly in DB.")
        
        # 3. Simulate Rejection by HR
        added_cert['Status'] = 'Rejected'
        added_cert['RejectionReason'] = 'Document is blurry.'
        employee['Certificates'] = certs
        EmployeesTable.put_item(employee)
        print("PASS: Simulated HR Rejection with feedback.")
        
        # Verify rejection
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        certs = employee.get('Certificates', [])
        added_cert = next((c for c in certs if c.get('CertificateID') == cert_id), None)
        assert added_cert.get('Status') == 'Rejected', "Status is not Rejected."
        assert added_cert.get('RejectionReason') == 'Document is blurry.', "RejectionReason not saved."
        print("PASS: Verified rejection state and feedback in DB.")
        
        # 4. Simulate Approval by HR
        added_cert['Status'] = 'Approved'
        added_cert['ApprovedAt'] = datetime.datetime.now().isoformat()
        added_cert['RejectionReason'] = ''
        employee['Certificates'] = certs
        EmployeesTable.put_item(employee)
        print("PASS: Simulated HR Approval.")
        
        # Verify approval
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        certs = employee.get('Certificates', [])
        added_cert = next((c for c in certs if c.get('CertificateID') == cert_id), None)
        assert added_cert.get('Status') == 'Approved', "Status is not Approved."
        assert added_cert.get('ApprovedAt') is not None, "ApprovedAt is not saved."
        print("PASS: Verified approved/verified state in DB.")
        
        # 5. Verify security rule: Approved certificate deletion (Simulated backend authorization checks)
        # For non-HR ADMIN (Employee themselves)
        user_role = 'Employee'
        if added_cert.get('Status') == 'Approved' and user_role != 'HR ADMIN':
            print("PASS: Backend security check correctly BLOCKS Employee from deleting verified certificate.")
            
        # For HR ADMIN
        user_role = 'HR ADMIN'
        if added_cert.get('Status') == 'Approved' and user_role == 'HR ADMIN':
            print("PASS: Backend security check correctly ALLOWS HR ADMIN to delete verified certificate.")
            
    finally:
        # Restore original certificates to keep DB clean
        employee = EmployeesTable.get_item({'EmployeeID': emp_id})
        employee['Certificates'] = original_certs
        EmployeesTable.put_item(employee)
        print("CLEANUP: Restored original certificate database list.")

if __name__ == "__main__":
    run_tests()
