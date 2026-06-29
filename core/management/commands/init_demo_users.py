import bcrypt
import uuid
from django.core.management.base import BaseCommand
from core.dynamodb_service import UsersTable, EmployeesTable

class Command(BaseCommand):
    help = 'Initialize Demo Users for Lurnexa HR Admin'

    def handle(self, *args, **kwargs):
        self.stdout.write('Generating demo users...')
        
        users_to_create = [
            {
                'Email': 'hr@lurnexa.com',
                'Role': 'HR ADMIN',
                'FirstName': 'Alice',
                'LastName': 'Admin',
                'Password': 'Password@123',
                'EmployeeID': 'LT-26001'
            },
            {
                'Email': 'hr_assistant@lurnexa.com',
                'Role': 'HR',
                'FirstName': 'Sarah',
                'LastName': 'Assistant',
                'Password': 'Password@123',
                'EmployeeID': 'LT-26004'
            },
            {
                'Email': 'manager@lurnexa.com',
                'Role': 'Manager',
                'FirstName': 'Bob',
                'LastName': 'Manager',
                'Password': 'Password@123',
                'EmployeeID': 'LT-26002'
            },
            {
                'Email': 'employee@lurnexa.com',
                'Role': 'Employee',
                'FirstName': 'Charlie',
                'LastName': 'Worker',
                'Password': 'Password@123',
                'EmployeeID': 'LT-26003'
            }
        ]

        for user in users_to_create:
            # Check if user already exists
            from boto3.dynamodb.conditions import Key
            existing = UsersTable.query(
                IndexName='EmailIndex',
                KeyConditionExpression=Key('Email').eq(user['Email'])
            )
            if existing:
                self.stdout.write(self.style.WARNING(f"User {user['Email']} already exists. Skipping."))
                continue

            user_id = str(uuid.uuid4())
            employee_id = user['EmployeeID']
            hashed_pw = bcrypt.hashpw(user['Password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # create user in Users table
            user_item = {
                'UserID': user_id,
                'Email': user['Email'],
                'Role': user['Role'],
                'PasswordHash': hashed_pw,
                'EmployeeID': employee_id,
                'IsActive': True
            }
            UsersTable.put_item(user_item)
            
            # create employee record
            employee_item = {
                'EmployeeID': employee_id,
                'UserID': user_id,
                'Email': user['Email'],
                'FirstName': user['FirstName'],
                'LastName': user['LastName'],
                'Department': 'Administration' if user['Role'] in ['HR', 'HR ADMIN'] else 'Engineering',
                'Designation': user['Role']
            }
            EmployeesTable.put_item(employee_item)
            
            self.stdout.write(self.style.SUCCESS(f"Created {user['Email']} with Role {user['Role']}"))

        self.stdout.write(self.style.SUCCESS('Done generating demo users.'))
