import boto3
import os
import time

endpoint = 'http://127.0.0.1:8001'
db = boto3.resource('dynamodb', endpoint_url=endpoint, region_name='us-east-1', aws_access_key_id='dummy', aws_secret_access_key='dummy')

table_name = 'TestTable'
try:
    db.create_table(
        TableName=table_name,
        KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
    )
    print(f"Table {table_name} created.")
    table = db.Table(table_name)
    table.put_item(Item={'id': 'test-1', 'data': 'hello'})
    print("Item put.")
    
    response = table.scan()
    print(f"Full response: {response}")
    print(f"Scan found: {response.get('Items')}")
except Exception as e:
    print(f"Error: {e}")
finally:
    try:
        db.Table(table_name).delete()
        print("Table deleted.")
    except:
        pass
