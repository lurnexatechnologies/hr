import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

import bcrypt
import uuid
from core.dynamodb_service import UsersTable, EmployeesTable, initialize_dynamodb_tables
from boto3.dynamodb.conditions import Key

def main():
    print("Checking DynamoDB tables...")
    try:
        initialize_dynamodb_tables()
    except Exception as e:
        print(f"Table Init: {e}")

    email = 'lurnexasolution@gmail.com'
    password = 'Password@123'
    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    print(f"Scanning for Platform Admin account ({email})...")
    users = UsersTable.scan()
    platform_admin_user = None
    for u in users:
        role = (u.get('Role') or '').strip()
        u_email = (u.get('Email') or '').strip().lower()
        if role.upper() in ['PLATFORM ADMIN', 'PLATFORM_ADMIN', 'PLATFORM SUPER ADMIN'] or u_email == email:
            platform_admin_user = u
            print(f"Found Platform Admin User item: UserID={u.get('UserID')}, Email={u.get('Email')}, Role={u.get('Role')}")

    if platform_admin_user:
        # Reset password to Password@123 and ensure Active
        user_id = platform_admin_user['UserID']
        UsersTable.update_item(
            Key={'UserID': user_id},
            UpdateExpression="SET PasswordHash = :ph, IsActive = :act, #r = :role, Email = :em",
            ExpressionAttributeNames={'#r': 'Role'},
            ExpressionAttributeValues={
                ':ph': hashed_pw,
                ':act': True,
                ':role': 'Platform Admin',
                ':em': email
            }
        )
        print(f"Successfully updated Platform Admin ({email}) with active status & password 'Password@123'!")
    else:
        # Create fresh Platform Admin User
        user_id = str(uuid.uuid4())
        emp_id = 'LXP-PLAT-001'

        user_item = {
            'UserID': user_id,
            'Email': email,
            'Role': 'Platform Admin',
            'PasswordHash': hashed_pw,
            'EmployeeID': emp_id,
            'IsActive': True
        }
        UsersTable.put_item(user_item)

        employee_item = {
            'EmployeeID': emp_id,
            'UserID': user_id,
            'Email': email,
            'FirstName': 'Lurnexa',
            'LastName': 'Technologies',
            'Department': 'Administration',
            'Designation': 'Platform Admin'
        }
        EmployeesTable.put_item(employee_item)
        print(f"Successfully created new Platform Admin account ({email}) with password 'Password@123'!")

if __name__ == "__main__":
    main()
