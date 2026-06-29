import datetime
from core.dynamodb_service import HolidaysTable, EmployeesTable, AttendanceTable

def check_and_credit_compoff(employee_id, record_date):
    """
    Checks if record_date is a weekend or public holiday.
    If so, credits 1 day of compensatory off (Comp Off) to the employee's balance
    if they haven't already been credited for this date.
    """
    try:
        # 1. Parse date
        for fmt in ('%Y-%m-%d', '%d-%m-%Y'):
            try:
                date_obj = datetime.datetime.strptime(record_date, fmt).date()
                iso_date = date_obj.isoformat()
                break
            except ValueError:
                continue
        else:
            return False

        # 2. Check if weekend (Saturday=5, Sunday=6)
        is_wk = date_obj.weekday() >= 5

        # 3. Check if holiday
        holidays = HolidaysTable.scan()
        is_hol = any(h.get('HolidayDate') == iso_date for h in holidays)

        if is_wk or is_hol:
            # 4. Check if already credited in attendance record
            attendance_rec = AttendanceTable.get_item({'EmployeeID': employee_id, 'RecordDate': iso_date})
            if attendance_rec and attendance_rec.get('CompOffCredited') == True:
                return False

            # 5. Fetch employee and update Comp Off balance
            employee = EmployeesTable.get_item({'EmployeeID': employee_id})
            if employee:
                # Get current balance (default to 0.0)
                try:
                    current_co = float(employee.get('Balance_CO', 0.0))
                except (TypeError, ValueError):
                    current_co = 0.0
                new_co = current_co + 1.0

                # Update employee record
                EmployeesTable.update_item(
                    Key={'EmployeeID': employee_id},
                    UpdateExpression="SET Balance_CO = :val",
                    ExpressionAttributeValues={':val': str(new_co)}
                )

                # Mark as credited in attendance record
                if attendance_rec:
                    AttendanceTable.update_item(
                        Key={'EmployeeID': employee_id, 'RecordDate': iso_date},
                        UpdateExpression="SET CompOffCredited = :val",
                        ExpressionAttributeValues={':val': True}
                    )
                return True
    except Exception as e:
        print(f"Error crediting compoff: {e}")
    return False

def get_active_compoff_balance(employee, reference_date=None):
    """
    Calculates the active (non-expired) compensatory off balance for an employee.
    Comp-offs expire exactly 30 days after they are accrued.
    Accruals come from:
      1. Attendance records where CompOffCredited = True
      2. Manual HR adjustments recorded in employee.get('COAdjustments', [])
    FIFO (First In, First Out) consumption is applied for spent comp-offs
    (approved leave requests of type Compensatory Off).
    """
    import datetime
    from boto3.dynamodb.conditions import Key
    from core.dynamodb_service import AttendanceTable, LeaveRequestsTable

    if not reference_date:
        reference_date = datetime.date.today()
    elif isinstance(reference_date, str):
        try:
            reference_date = datetime.datetime.strptime(reference_date, '%Y-%m-%d').date()
        except ValueError:
            reference_date = datetime.date.today()

    employee_id = employee.get('EmployeeID')
    if not employee_id:
        return {
            'active_balance': 0.0,
            'effective_balance': 0.0,
            'pending_balance': 0.0,
            'expired_balance': 0.0,
            'spent_balance': 0.0
        }

    # 1. Fetch all attendance records for this employee to find auto-credits
    records = []
    try:
        records = AttendanceTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(employee_id)
        )
    except Exception as e:
        print(f"Error querying attendance table: {e}")

    # Gather all accruals
    accruals = []
    
    # Auto-credited comp-offs from attendance
    for r in records:
        if r.get('CompOffCredited') is True:
            date_str = r.get('RecordDate')
            try:
                acc_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                accruals.append({
                    'date': acc_date,
                    'amount': 1.0,
                    'description': f"Accrued on {date_str}"
                })
            except:
                pass

    # Manual adjustments from Employee profile
    adjustments = employee.get('COAdjustments', [])
    for adj in adjustments:
        date_str = adj.get('Date')
        amount_val = adj.get('Amount', '0.0')
        try:
            acc_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            accruals.append({
                'date': acc_date,
                'amount': float(amount_val),
                'description': f"HR Adjustment on {date_str}"
            })
        except:
            pass

    # Sort accruals chronologically (oldest first)
    accruals.sort(key=lambda x: x['date'])

    # 2. Fetch all leave requests to calculate total spent (Approved) and pending
    leaves = []
    try:
        leaves = LeaveRequestsTable.query(
            KeyConditionExpression=Key('EmployeeID').eq(employee_id)
        )
    except Exception as e:
        print(f"Error querying leave requests table: {e}")

    spent_co = sum(
        float(l.get('DaysCount', 0))
        for l in leaves
        if l.get('Status') == 'Approved' and ('Comp' in l.get('Type', '') or 'Comp' in l.get('LeaveType', ''))
    )
    
    pending_co = sum(
        float(l.get('DaysCount', 0))
        for l in leaves
        if l.get('Status') == 'Pending' and ('Comp' in l.get('Type', '') or 'Comp' in l.get('LeaveType', ''))
    )

    # 3. FIFO Consumption
    remaining_spent = spent_co
    cutoff_date = reference_date - datetime.timedelta(days=30)
    
    active_balance = 0.0
    expired_balance = 0.0

    for acc in accruals:
        acc_date = acc['date']
        acc_amount = acc['amount']
        
        # If the amount is negative (e.g. negative HR adjustment), we can treat it as consuming positive balance
        if acc_amount < 0:
            remaining_spent += abs(acc_amount)
            continue

        if remaining_spent >= acc_amount:
            # Fully consumed by past leaves
            remaining_spent -= acc_amount
            acc_amount = 0.0
        elif remaining_spent > 0:
            # Partially consumed
            acc_amount -= remaining_spent
            remaining_spent = 0.0

        if acc_amount > 0:
            # Check if expired (older than 30 days)
            if acc_date < cutoff_date:
                expired_balance += acc_amount
            else:
                active_balance += acc_amount

    # Subtract remaining spent if there was more spent than accrued (should not happen normally)
    if remaining_spent > 0:
        active_balance = max(0.0, active_balance - remaining_spent)

    effective_balance = max(0.0, active_balance - pending_co)

    return {
        'active_balance': round(active_balance, 2),
        'effective_balance': round(effective_balance, 2),
        'pending_balance': round(pending_co, 2),
        'expired_balance': round(expired_balance, 2),
        'spent_balance': round(spent_co, 2)
    }
