import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import get_dynamodb_resource

def list_tables():
    dynamodb = get_dynamodb_resource()
    tables = list(dynamodb.tables.all())
    print("CURRENT TABLES IN DYNAMODB:")
    for table in tables:
        print(f"- {table.name}")

if __name__ == '__main__':
    list_tables()
