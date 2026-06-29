from django.core.management.base import BaseCommand
from core.dynamodb_service import initialize_dynamodb_tables
from botocore.exceptions import NoCredentialsError

class Command(BaseCommand):
    help = 'Initialize DynamoDB tables for Lurnexa HR Admin'

    def handle(self, *args, **kwargs):
        try:
            self.stdout.write('Starting DynamoDB table initialization...')
            initialize_dynamodb_tables()
            self.stdout.write(self.style.SUCCESS('Successfully initialized all DynamoDB tables.'))
        except NoCredentialsError:
            self.stdout.write(self.style.ERROR('AWS credentials not found. Please configure your .env file or AWS CLI profile.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'An error occurred: {e}'))
