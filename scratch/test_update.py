from core.dynamodb_service import EmployeesTable
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lurnexa_hrms.settings')
django.setup()

emp_id = 'LT20265006' # Yesh Raj
updates = {'AllowSecondParental': True, 'AllowSecondMarriage': True}

expr_parts = []
attr_names = {}
attr_vals = {}

for i, (key, value) in enumerate(updates.items()):
    expr_parts.append(f"#k{i} = :v{i}")
    attr_names[f"#k{i}"] = key
    attr_vals[f":v{i}"] = value

UpdateExpression = "SET " + ", ".join(expr_parts)

print(f"Updating {emp_id}...")
print(f"Expr: {UpdateExpression}")
print(f"Names: {attr_names}")
print(f"Values: {attr_vals}")

EmployeesTable.update_item(
    Key={'EmployeeID': emp_id},
    UpdateExpression=UpdateExpression,
    ExpressionAttributeNames=attr_names,
    ExpressionAttributeValues=attr_vals
)

emp = EmployeesTable.get_item({'EmployeeID': emp_id})
print(f"After Update: AllowSecondParental={emp.get('AllowSecondParental')}")
