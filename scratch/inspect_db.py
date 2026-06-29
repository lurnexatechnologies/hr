import boto3
from pprint import pprint

dynamodb = boto3.resource(
    'dynamodb', 
    endpoint_url='http://localhost:8001', 
    region_name='us-east-1',
    aws_access_key_id='dummy',
    aws_secret_access_key='dummy'
)

def get_samples():
    print("USER SAMPLE:")
    user_table = dynamodb.Table('Lurnexa_Users')
    pprint(user_table.scan(Limit=1).get('Items', []))
    
    print("\nEMPLOYEE SAMPLE:")
    emp_table = dynamodb.Table('Lurnexa_Employees')
    pprint(emp_table.scan(Limit=1).get('Items', []))

if __name__ == "__main__":
    get_samples()
