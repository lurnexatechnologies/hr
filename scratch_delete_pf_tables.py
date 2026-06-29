import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import get_dynamodb_resource

def delete_tables():
    dynamodb = get_dynamodb_resource()
    tables_to_delete = ['Lurnexa_PFSettings', 'Lurnexa_PFTransactions']
    
    for table_name in tables_to_delete:
        table = dynamodb.Table(table_name)
        try:
            table.delete()
            print(f"Successfully deleted table: {table_name}")
            # Wait for it to be deleted
            table.meta.client.get_waiter('table_not_exists').wait(TableName=table_name)
        except Exception as e:
            print(f"Error deleting {table_name}: {e}")

if __name__ == '__main__':
    delete_tables()
