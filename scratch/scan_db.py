import boto3
from pprint import pprint

dynamodb = boto3.resource(
    'dynamodb', 
    endpoint_url='http://localhost:8001', 
    region_name='us-east-1',
    aws_access_key_id='dummy',
    aws_secret_access_key='dummy'
)

def scan_user():
    user_table = dynamodb.Table('Lurnexa_Users')
    # Filter for User with EmployeeID 'LP2025001'
    users = user_table.scan().get('Items', [])
    for u in users:
        if u.get('EmployeeID') == 'LP2025001':
            pprint(u)

scan_user()
