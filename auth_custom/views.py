import bcrypt
import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views import View
from core.dynamodb_service import UsersTable, EmployeesTable, LoginHistoryTable, PasswordResetTokensTable
from core.utils import get_local_date, get_local_now
from boto3.dynamodb.conditions import Key
import uuid
from django.core.mail import send_mail
from django.conf import settings

class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            # If an authenticated user tries to access the login page (e.g. via back button),
            # redirect them back to their dashboard instead of logging them out.
            return self._redirect_dashboard(request.user.role)
        return render(request, 'auth_custom/login.html')

    def post(self, request):
        email_or_id = request.POST.get('username')
        password = request.POST.get('password')
        
        user_data = None
        user = UsersTable.get_item({'UserID': email_or_id})
        if user:
            user_data = user
        else:
            # Try by EmailIndex
            users = UsersTable.query(
                IndexName='EmailIndex',
                KeyConditionExpression=Key('Email').eq(email_or_id)
            )
            if users:
                user_data = users[0]
            else:
                # Try by EmployeeID
                employee = EmployeesTable.get_item({'EmployeeID': email_or_id})
                if employee and 'UserID' in employee:
                    user = UsersTable.get_item({'UserID': employee['UserID']})
                    if user:
                        user_data = user
                
        from django.contrib.auth.hashers import check_password
        
        if user_data:
            hashed = user_data.get('PasswordHash', '')
            if not hashed:
                hashed = user_data.get('Password', '') # fallback for test users
                
            is_valid = False
            
            # 1. Try Django's robust check_password first
            if check_password(password, hashed):
                is_valid = True
            else:
                # 2. Fallback to raw bcrypt for legacy users
                try:
                    if bcrypt.checkpw(password.encode('utf-8')[:72], hashed.encode('utf-8')):
                        is_valid = True
                except Exception:
                    pass
                    
            if is_valid:
                # --- LAST WORKING DAY (LWD) CHECK ---
                emp_id = user_data.get('EmployeeID')
                if emp_id:
                    emp = EmployeesTable.get_item({'EmployeeID': emp_id})
                    if emp:
                        lwd_str = emp.get('LastWorkingDate')
                        if lwd_str:
                            try:
                                lwd = datetime.datetime.strptime(lwd_str, '%Y-%m-%d').date()
                                today = get_local_date()
                                if today > lwd:
                                    # Auto-deactivate if not already
                                    if user_data.get('IsActive', True):
                                        UsersTable.update_item(Key={'UserID': user_data['UserID']}, UpdateExpression="SET IsActive = :val", ExpressionAttributeValues={":val": False})
                                        EmployeesTable.update_item(Key={'EmployeeID': emp_id}, UpdateExpression="SET IsActive = :val", ExpressionAttributeValues={":val": False})
                                    
                                    messages.error(request, f"Your access has expired as per your Last Working Day ({lwd_str}). Please contact HR.")
                                    return render(request, 'auth_custom/login.html')
                            except Exception as e:
                                print(f"Error parsing LWD: {e}")

                if not user_data.get('IsActive', True):
                    messages.error(request, "This profile is deactivated. Please contact HR to reactivate.")
                    return render(request, 'auth_custom/login.html')
                # Single Device Login Check
                import time
                now = time.time()
                active_token = user_data.get('ActiveSessionToken')
                last_act = user_data.get('LastActivityTime')
                db_device_id = user_data.get('DeviceID')
                
                # Get device_id from cookie
                cookie_device_id = request.COOKIES.get('device_id')
                
                if active_token and last_act:
                    try:
                        elapsed = now - float(last_act)
                        # Block only if active session is less than 1 hour old AND the device_id does not match
                        if elapsed < 3600 and cookie_device_id != db_device_id:
                            messages.error(request, "You are already logged in on another device. Please log out from that device first or wait for it to expire.")
                            return render(request, 'auth_custom/login.html')
                    except (ValueError, TypeError):
                        pass

                # Ensure we have a cookie_device_id
                if not cookie_device_id:
                    cookie_device_id = str(uuid.uuid4())

                # Generate a new unique session token
                session_token = str(uuid.uuid4())
                request.session['session_token'] = session_token
                
                # Update ActiveSessionToken, LastActivityTime, and DeviceID in DynamoDB
                try:
                    UsersTable.update_item(
                        Key={'UserID': user_data['UserID']},
                        UpdateExpression="SET ActiveSessionToken = :token, LastActivityTime = :act_time, DeviceID = :dev_id",
                        ExpressionAttributeValues={
                            ":token": session_token,
                            ":act_time": int(now),
                            ":dev_id": cookie_device_id
                        }
                    )
                except Exception as e:
                    print(f"ERROR: Failed to update active session token in DB: {e}")

                from core.utils import is_mobile_app
                
                request.session['user_id'] = user_data['UserID']
                if is_mobile_app(request):
                    # For mobile app, keep logged in forever (e.g., 100 years) until explicit logout
                    request.session.set_expiry(3153600000)
                else:
                    # Setting to 0 means the session cookie expires when the browser/tab is closed
                    request.session.set_expiry(0)
                
                # Record Login History
                try:
                    user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')
                    
                    device = "Desktop"
                    if "Mobile" in user_agent: device = "Mobile"
                    elif "Tablet" in user_agent: device = "Tablet"
                    
                    browser = "Unknown Browser"
                    if "Chrome" in user_agent: browser = "Chrome"
                    elif "Firefox" in user_agent: browser = "Firefox"
                    elif "Safari" in user_agent: browser = "Safari"
                    elif "Edge" in user_agent: browser = "Edge"
                    
                    os_name = "Unknown OS"
                    if "Windows" in user_agent: os_name = "Windows"
                    elif "Macintosh" in user_agent: os_name = "macOS"
                    elif "iPhone" in user_agent: os_name = "iOS"
                    elif "Android" in user_agent: os_name = "Android"
                    elif "Linux" in user_agent: os_name = "Linux"

                    # Extract IP Address
                    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                    if x_forwarded_for:
                        ip_address = x_forwarded_for.split(',')[0].strip()
                    else:
                        ip_address = request.META.get('REMOTE_ADDR', '0.0.0.0')

                    LoginHistoryTable.put_item({
                        'UserID': user_data['UserID'],
                        'LoginTime': get_local_now().isoformat(),
                        'Browser': browser,
                        'OS': os_name,
                        'Device': device,
                        'IPAddress': ip_address,
                        'UserAgent': user_agent[:200]
                    })
                except Exception as e:
                    print(f"Failed to record login history: {e}")

                # Explicitly clear any redirect parameters to force dashboard landing as requested
                response = self._redirect_dashboard(user_data.get('Role', 'Employee'))
                response.set_cookie('device_id', cookie_device_id, max_age=31536000, httponly=True, samesite='Lax')
                return response
            else:
                messages.error(request, "Invalid credentials.")
        else:
            messages.error(request, "Invalid credentials.")
            
        return render(request, 'auth_custom/login.html')

    def _redirect_dashboard(self, role):
        if role == 'Super admin':
            return redirect('super_admin_dashboard')
        elif role == 'HR ADMIN':
            return redirect('hr_dashboard')
        elif role == 'Manager':
            return redirect('manager_dashboard')
        else:
            return redirect('employee_dashboard')

class LogoutView(View):
    def get(self, request):
        user_emp_id = None
        uid = request.session.get('user_id')
        if uid:
            user = UsersTable.get_item({'UserID': uid})
            if user:
                user_emp_id = user.get('EmployeeID')
                
        device_token = request.GET.get('device_token')
        if device_token and user_emp_id:
            try:
                from core.dynamodb_service import DeviceTokensTable
                DeviceTokensTable.delete_item({
                    'EmployeeID': user_emp_id,
                    'DeviceToken': device_token
                })
                print(f"DEBUG: Unregistered token {device_token} for employee {user_emp_id} on logout.")
            except Exception as e:
                print(f"ERROR: Failed to unregister token on logout: {e}")

        if uid:
            try:
                # Clear active session in UsersTable
                UsersTable.update_item(
                    Key={'UserID': uid},
                    UpdateExpression="REMOVE ActiveSessionToken, LastActivityTime"
                )
            except Exception as e:
                print(f"ERROR: Failed to clear active session token on logout: {e}")

        if 'user_id' in request.session:
            del request.session['user_id']
        if 'session_token' in request.session:
            del request.session['session_token']
            
        reason = request.GET.get('reason')
        if reason == 'tab_closed':
            messages.warning(request, "Your session has expired because the tab was closed. Please log in again.")
        else:
            messages.success(request, "You have been logged out.")
        return redirect('login')

class ForgotPasswordView(View):
    def get(self, request):
        return render(request, 'auth_custom/forgot_password.html')

    def post(self, request):
        email = request.POST.get('email')
        if not email:
            messages.error(request, "Please enter your email.")
            return render(request, 'auth_custom/forgot_password.html')

        users = UsersTable.query(
            IndexName='EmailIndex',
            KeyConditionExpression=Key('Email').eq(email)
        )
        if not users:
            messages.info(request, "If an account exists for this email, you will receive a reset link.")
            return render(request, 'auth_custom/forgot_password.html')

        token = str(uuid.uuid4())
        expiry = (get_local_now() + datetime.timedelta(hours=1)).isoformat()
        
        try:
            PasswordResetTokensTable.put_item({
                'Token': token,
                'Email': email,
                'Expiry': expiry
            })
            
            reset_url = request.build_absolute_uri(f'/auth/reset-password/{token}/')
            subject = 'Reset Your Lurnexa HR Admin Password'
            message = f"""
            Hello,

            You requested a password reset for your Lurnexa HR Admin account.
            Please click the link below to reset your password:

            {reset_url}

            This link will expire in 1 hour.

            If you did not request this, please ignore this email.
            """
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            messages.success(request, "Password reset link has been sent to your email.")
        except Exception as e:
            messages.error(request, f"Failed to process request: {str(e)}")
            
        return render(request, 'auth_custom/forgot_password.html')

class ResetPasswordView(View):
    def get(self, request, token):
        token_data = PasswordResetTokensTable.get_item({'Token': token})
        if not token_data:
            messages.error(request, "Invalid or expired reset token.")
            return redirect('login')
        
        expiry = datetime.datetime.fromisoformat(token_data['Expiry'])
        if get_local_now() > expiry:
            PasswordResetTokensTable.delete_item({'Token': token})
            messages.error(request, "Password reset token has expired.")
            return redirect('login')
            
        return render(request, 'auth_custom/reset_password.html', {'token': token})

    def post(self, request, token):
        new_password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if not new_password or new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'auth_custom/reset_password.html', {'token': token})

        # Password Strength Validation
        import re
        password_regex = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$'
        if not re.match(password_regex, new_password):
            messages.error(request, "Password is too weak. It must be at least 8 characters long and include uppercase letters, lowercase letters, numbers, and special characters.")
            return render(request, 'auth_custom/reset_password.html', {'token': token})

        token_data = PasswordResetTokensTable.get_item({'Token': token})
        if not token_data:
            messages.error(request, "Invalid or expired reset token.")
            return redirect('login')

        email = token_data['Email']
        users = UsersTable.query(
            IndexName='EmailIndex',
            KeyConditionExpression=Key('Email').eq(email)
        )
        
        if users:
            user_data = users[0]
            from django.contrib.auth.hashers import make_password
            hashed_pw = make_password(new_password)
            
            UsersTable.update_item(
                Key={'UserID': user_data['UserID']},
                UpdateExpression="SET PasswordHash = :p",
                ExpressionAttributeValues={':p': hashed_pw}
            )
            
            PasswordResetTokensTable.delete_item({'Token': token})
            messages.success(request, "Password has been reset successfully. You can now log in.")
            return redirect('login')
        else:
            messages.error(request, "User not found.")
            return redirect('login')

class Forbidden403View(View):
    def get(self, request):
        return render(request, 'auth_custom/403.html', status=403)

