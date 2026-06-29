import boto3
import os

endpoint = 'http://127.0.0.1:8000'
client = boto3.client('dynamodb', endpoint_url=endpoint, region_name='us-east-1', aws_access_key_id='dummy', aws_secret_access_key='dummy')

# Put item manually
try:
    client.put_item(
        TableName='Lurnexa_Users',
        Item={
            'UserID': {'S': 'test-manual'},
            'Email': {'S': 'test@test.com'},
            'Role': {'S': 'HR'},
            'PasswordHash': {'S': 'abc'},
            'IsActive': {'BOOL': True}
        }
    )
    print("Manual put success.")
    
    # Get item
    res = client.get_item(TableName='Lurnexa_Users', Key={'UserID': {'S': 'test-manual'}})
    print(f"Manual get res: {res.get('Item')}")
    
    # Scan
    res_scan = client.scan(TableName='Lurnexa_Users')
    print(f"Manual scan count: {len(res_scan.get('Items', []))}")
except Exception as e:
    print(f"Error: {e}")
