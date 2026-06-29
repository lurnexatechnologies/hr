import boto3
import os
from dotenv import load_dotenv

load_dotenv()

endpoint = os.getenv('DYNAMODB_ENDPOINT_URL', 'http://127.0.0.1:8000')
region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')

dynamodb = boto3.resource(
    'dynamodb',
    endpoint_url=endpoint,
    region_name=region,
    aws_access_key_id='dummy',
    aws_secret_access_key='dummy'
)

table = dynamodb.Table('Lurnexa_Users')
try:
    response = table.scan()
    items = response.get('Items', [])
    print(f"Total users found: {len(items)}")
    for item in items:
        print(f"User: {item.get('Email')}, Role: {item.get('Role')}, Active: {item.get('IsActive')}")
except Exception as e:
    print(f"Error: {e}")
