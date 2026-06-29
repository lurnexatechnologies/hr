import os
import sys
import django
import datetime
from unittest.mock import MagicMock, patch

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

from core.kotak_service import KotakBankService

def test_kotak_integration():
    kotak = KotakBankService()
    
    # Mock employee data
    employee = {
        "EmployeeID": "LT-26007",
        "FirstName": "Test",
        "LastName": "User",
        "AccountNumber": "1234567890",
        "IFSCCode": "KKBK0000001",
        "BankName": "Kotak Bank"
    }
    
    amount = 50000.00
    reference_id = "LT-26007_may_2026"
    
    print(f"Testing fund transfer for {employee['EmployeeID']}...")
    result = kotak.transfer_funds(employee, amount, reference_id, payment_mode='NEFT')
    
    print("\n--- Transfer Result ---")
    print(f"Status: {result.get('status')}")
    print(f"Transaction ID: {result.get('transaction_id')}")
    print(f"Message: {result.get('message')}")
    
    assert result['status'] == "SUCCESS"
    assert "transaction_id" in result
    
    print("\nIntegration check successful!")

if __name__ == "__main__":
    test_kotak_integration()
