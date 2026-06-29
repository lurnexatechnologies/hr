import boto3
import bcrypt
import uuid
import datetime

dynamodb = boto3.resource(
    'dynamodb', 
    endpoint_url='http://localhost:8001', 
    region_name='us-east-1',
    aws_access_key_id='dummy',
    aws_secret_access_key='dummy'
)

users_table = dynamodb.Table('Lurnexa_Users')
employees_table = dynamodb.Table('Lurnexa_Employees')

def create_super_admin():
    email = "superadmin@lurnexa.com"
    raw_password = "Password@123"
    emp_id = "LXP-SUPER-001"
    user_id = str(uuid.uuid4())
    
    # Hash password
    hashed_pw = bcrypt.hashpw(raw_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    # Create User
    user_item = {
        'UserID': user_id,
        'Email': email,
        'PasswordHash': hashed_pw,
        'Role': 'Super admin',
        'EmployeeID': emp_id,
        'IsActive': True,
        'CreatedAt': datetime.datetime.now().isoformat()
    }
    users_table.put_item(Item=user_item)
    print(f"User created: {email}")
    
    # Create Employee
    employee_item = {
        'EmployeeID': emp_id,
        'UserID': user_id,
        'FirstName': 'Super',
        'LastName': 'Admin',
        'Email': email,
        'Phone': '0000000000',
        'Role': 'Super admin',
        'Department': 'Management',
        'Designation': 'System Administrator',
        'OnboardingStatus': 'Approved',
        'JoinedDate': '2026-01-01',
        'EmploymentType': 'Permanent',
        'Shift': 'Day Shift',
        'IsActive': True,
        'DateOfBirth': '1990-01-01',
        'Gender': 'Male',
        'BloodGroup': 'O+',
        'Address': 'System Main Office',
        'AadharNumber': '000000000000',
        'PanNumber': 'SUPER0000A',
        'AccountNumber': '0000000000',
        'BankName': 'System Bank',
        'IFSCCode': 'SYS00001',
        'EmergencyContactName': 'Admin Support',
        'EmergencyContactPhone': '0000000000'
    }
    employees_table.put_item(Item=employee_item)
    print(f"Employee created: {emp_id}")

if __name__ == "__main__":
    create_super_admin()
