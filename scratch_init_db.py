import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import initialize_dynamodb_tables

if __name__ == "__main__":
    print("Starting DynamoDB table initialization...")
    initialize_dynamodb_tables()
    print("Initialization complete.")
