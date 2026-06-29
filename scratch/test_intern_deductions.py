import datetime

def process_payroll_logic_mock(employee, attendance, gross_salary, basic, current_annual_salary):
    total_days = attendance["total_days"]
    lop_days = attendance["lop_days"]

    per_day_salary = gross_salary / total_days if total_days > 0 else 0
    lop_deduction = per_day_salary * lop_days

    adjusted_gross = gross_salary - lop_deduction

    # PF
    pf_employee = 0
    is_intern = employee.get('EmploymentType') == 'Intern'
    
    if not is_intern and (employee.get('pf_enabled', False)):
        pf_employee = 0.12 * basic

    # ESI
    esi_employee = 0
    if not is_intern:
        if adjusted_gross <= 21000:
            esi_employee = 0.0075 * adjusted_gross
        else:
            esi_employee = 0.0125 * adjusted_gross

    # PT
    pt = 0
    if not is_intern:
        if adjusted_gross > 20000:
            pt = 200
        elif adjusted_gross > 15000:
            pt = 150

    # TDS
    tds = 0
    if not is_intern:
        annual_income = current_annual_salary
        std_deduction = 75000
        taxable_income = max(0, annual_income - std_deduction)
        if taxable_income > 700000:
            tax = (taxable_income - 700000) * 0.1 # Simplified
            tds = tax / 12

    total_deductions = pf_employee + esi_employee + pt + tds
    return {
        "lop": lop_deduction,
        "pf": pf_employee,
        "esi": esi_employee,
        "pt": pt,
        "tds": tds,
        "total_deductions": total_deductions,
        "net_salary": adjusted_gross - total_deductions
    }

# Test cases
intern = {"EmploymentType": "Intern", "pf_enabled": True}
permanent = {"EmploymentType": "Permanent", "pf_enabled": True}

attendance = {"total_days": 30, "lop_days": 2} # 2 days LOP
gross = 50000
basic = 25000
annual = 600000

intern_payroll = process_payroll_logic_mock(intern, attendance, gross, basic, annual)
perm_payroll = process_payroll_logic_mock(permanent, attendance, gross, basic, annual)

print(f"Intern LOP: {intern_payroll['lop']}")
print(f"Intern PF: {intern_payroll['pf']}, ESI: {intern_payroll['esi']}, PT: {intern_payroll['pt']}, TDS: {intern_payroll['tds']}")

print(f"Permanent LOP: {perm_payroll['lop']}")
print(f"Permanent PF: {perm_payroll['pf']}, ESI: {perm_payroll['esi']}, PT: {perm_payroll['pt']}, TDS: {perm_payroll['tds']}")

assert intern_payroll['lop'] > 0
assert intern_payroll['pf'] == 0
assert intern_payroll['esi'] == 0
assert intern_payroll['pt'] == 0
assert intern_payroll['tds'] == 0

assert perm_payroll['pf'] > 0
assert perm_payroll['esi'] > 0
assert perm_payroll['pt'] > 0

print("Test passed successfully!")
