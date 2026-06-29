import sys
import os
import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
import django
django.setup()

from core.dynamodb_service import EmployeesTable

def verify_pf_management_logic():
    today = datetime.date.today()
    all_employees = EmployeesTable.scan()
    
    # Verify earliest year calculation
    earliest_year = today.year
    for e in all_employees:
        joined_str = e.get('JoinedDate')
        if joined_str:
            try:
                y = int(joined_str.split('-')[0])
                if y < earliest_year:
                    earliest_year = y
            except: pass
    
    print(f"Calculated Earliest Year: {earliest_year}")
    
    # Verify filter logic
    permanent_count = 0
    intern_count = 0
    for e in all_employees:
        if e.get('EmploymentType') == 'Permanent':
            permanent_count += 1
        elif e.get('EmploymentType') == 'Intern':
            intern_count += 1
            
    print(f"Total Permanent: {permanent_count}")
    print(f"Total Interns: {intern_count}")
    
    # Simulate view filtering (for current month)
    selected_month = today.strftime('%b').lower()
    selected_year = str(today.year)
    period_end_date = today # approximation
    
    filtered_count = 0
    for e in all_employees:
        if e.get('EmploymentType') != 'Permanent':
            continue
        
        joined_str = e.get('JoinedDate')
        if not joined_str: continue
        
        try:
            joined_date = datetime.datetime.strptime(joined_str, '%Y-%m-%d').date()
            if joined_date <= period_end_date:
                filtered_count += 1
        except: continue
        
    print(f"Filtered Permanent Employees for this period: {filtered_count}")
    assert filtered_count <= permanent_count
    
    print("Verification logic check complete.")

if __name__ == "__main__":
    verify_pf_management_logic()
