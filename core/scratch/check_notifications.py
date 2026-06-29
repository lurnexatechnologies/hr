import boto3
import os
from dotenv import load_dotenv

load_dotenv()

endpoint_url = os.getenv('DYNAMODB_ENDPOINT_URL', 'http://127.0.0.1:8001')
dynamodb = boto3.resource('dynamodb', endpoint_url=endpoint_url, region_name='us-east-1')
table = dynamodb.Table('Lurnexa_Notifications')

response = table.scan()
print(f"Total items: {len(response['Items'])}")
for item in response['Items']:
    print(item)
