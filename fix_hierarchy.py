import boto3
import os
from dotenv import load_dotenv

load_dotenv()

endpoint = os.getenv('DYNAMODB_ENDPOINT_URL', 'http://127.0.0.1:8001')
region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')

dynamodb = boto3.resource(
    'dynamodb',
    endpoint_url=endpoint,
    region_name=region,
    aws_access_key_id='dummy',
    aws_secret_access_key='dummy'
)

users_table = dynamodb.Table('Lurnexa_Users')
hierarchy_table = dynamodb.Table('Lurnexa_ReportingHierarchy')

users = users_table.scan().get('Items', [])
print("Users:")
for u in users:
    print(f"- {u.get('Email')} ID: {u.get('EmployeeID')}")

hierarchy = hierarchy_table.scan().get('Items', [])
print("\nHierarchy:")
for h in hierarchy:
    print(f"- Manager: {h.get('ManagerID')} Reports: {h.get('EmployeeID')}")

# Add relationship if missing
bob = next((u for u in users if u.get('Email') == 'manager@lurnexa.com'), None)
charlie = next((u for u in users if u.get('Email') == 'employee@lurnexa.com'), None)

if bob and charlie:
    print(f"\nLinking Charlie ({charlie.get('EmployeeID')}) to Bob ({bob.get('EmployeeID')})")
    hierarchy_table.put_item(Item={
        'ManagerID': bob.get('EmployeeID'),
        'EmployeeID': charlie.get('EmployeeID')
    })
    print("Done.")
else:
    print("\nCould not find Bob or Charlie.")
