from core.dynamodb_service import EmployeesTable
import sys

emp_id = sys.argv[1] if len(sys.argv) > 1 else 'LT-26001'
employee = EmployeesTable.get_item({'EmployeeID': emp_id})
if employee:
    print(f"Employee: {employee.get('FirstName')} {employee.get('LastName')}")
    print(f"AllowSecondParental: {employee.get('AllowSecondParental')}")
    print(f"AllowSecondMarriage: {employee.get('AllowSecondMarriage')}")
    print(f"Balances: PL={employee.get('Balance_PL')}, SL={employee.get('Balance_SL')}, CL={employee.get('Balance_CL')}")
else:
    print("Employee not found.")
