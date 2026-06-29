import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.dynamodb_service import EmployeeLettersTable
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

def run_migration():
    print("Fetching letters from DynamoDB...")
    letters = EmployeeLettersTable.scan()
    print(f"Found {len(letters)} letters total.")
    
    migrated_count = 0
    skipped_count = 0
    
    for letter in letters:
        letter_id = letter.get('LetterID')
        employee_id = letter.get('EmployeeID')
        content = letter.get('Content')
        file_path = letter.get('FilePath')
        
        # We only migrate if Content is populated and FilePath is empty/missing
        if content and not file_path:
            print(f"Migrating letter {letter_id} for Employee {employee_id}...")
            
            # Save file to default_storage
            dest_path = f"letters/{letter_id}.html"
            default_storage.save(dest_path, ContentFile(content.encode('utf-8')))
            
            # Update DynamoDB record
            letter['FilePath'] = dest_path
            # Remove Content field from DynamoDB to save space
            if 'Content' in letter:
                del letter['Content']
                
            # Put item back in DynamoDB
            EmployeeLettersTable.put_item(letter)
            migrated_count += 1
        else:
            skipped_count += 1
            
    print(f"Migration completed! Migrated: {migrated_count}, Skipped: {skipped_count}.")

if __name__ == '__main__':
    run_migration()
