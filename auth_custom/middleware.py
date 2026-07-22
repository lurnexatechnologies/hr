from .models import DynamoUser, DynamoAnonymousUser
from core.dynamodb_service import UsersTable, EmployeesTable
import logging
import time
import time as _time
from django.shortcuts import redirect
from django.contrib import messages
from core.features import PLAN_FEATURES, PLAN_LIMITS

logger = logging.getLogger(__name__)

# Simple in-memory cache: {org_id: (org_data, timestamp)}
_org_cache = {}
_ORG_CACHE_TTL = 60  # seconds

def _get_org_cached(org_id):
    """Load org from DynamoDB with 60s in-memory TTL cache."""
    cached = _org_cache.get(org_id)
    if cached and (_time.time() - cached[1]) < _ORG_CACHE_TTL:
        return cached[0]
    from core.dynamodb_service import OrganizationsTable
    try:
        org = OrganizationsTable.get_item({'OrgID': org_id})
        if org:
            _org_cache[org_id] = (org, _time.time())
            return org
    except Exception as e:
        logger.error(f"Error fetching organization details: {e}")
    return None


def get_user_permissions(user_data, org):
    """
    Resolves the list of fine-grained permissions for a user.
    """
    role_raw = user_data.get('Role', 'Employee').strip()
    role_upper = role_raw.upper()
    
    # 1. Start with default permissions based on the role
    effective_permissions = set()
    
    if role_upper in ['PLATFORM ADMIN', 'PLATFORM SUPER ADMIN']:
        # Platform admins get everything
        return ['payroll_access', 'employee_write', 'employee_read', 'leave_approve', 'expense_approve']
    elif role_upper in ['SUPER ADMIN', 'SUPERADMIN']:
        # Super admin gets all tenant privileges except payroll
        effective_permissions.update(['employee_write', 'employee_read', 'leave_approve', 'expense_approve'])
        
    # 2. Check CustomRoles defined in the organization
    custom_roles = {}
    if org:
        custom_roles = org.get('CustomRoles', {})
        
    if role_raw in custom_roles:
        # Load permissions from dynamic custom roles registry
        effective_permissions.update(custom_roles[role_raw].get('Permissions', []))
    else:
        # Fallback to standard defaults
        if role_upper in ['HR ADMIN', 'HRADMIN', 'HR']:
            # HR has general employee management and leaves, but NO payroll by default
            effective_permissions.update(['employee_write', 'employee_read', 'leave_approve'])
        elif role_upper == 'MANAGER':
            effective_permissions.update(['employee_read', 'leave_approve'])
        elif role_upper == 'EMPLOYEE':
            effective_permissions.update([])
            
    # 3. Add individual user-specific overrides stored in UserData or EmployeeData
    if user_data.get('Permissions'):
        effective_permissions.update(user_data.get('Permissions', []))
    if user_data.get('PermissionsOverride'):
        effective_permissions.update(user_data.get('PermissionsOverride', []))
        
    # 4. Check if this specific user is marked as the designated Payroll/PF/Historical Payroll Officer on the organization
    user_id = user_data.get('UserID')
    if org:
        if org.get('PayrollManagerUserID') == user_id:
            if role_upper not in ['SUPER ADMIN', 'SUPERADMIN']:
                effective_permissions.add('payroll_access')
        if org.get('PFManagerUserID') == user_id:
            if role_upper not in ['SUPER ADMIN', 'SUPERADMIN']:
                effective_permissions.add('pf_access')
        if org.get('HistoricalPayrollManagerUserID') == user_id:
            if role_upper not in ['SUPER ADMIN', 'SUPERADMIN']:
                effective_permissions.add('historical_payroll_access')

    # Ensure role permissions logic discard them if not explicitly designated
    if role_upper not in ['PLATFORM ADMIN', 'PLATFORM SUPER ADMIN']:
        if not org or org.get('PayrollManagerUserID') != user_id:
            effective_permissions.discard('payroll_access')
        if not org or org.get('PFManagerUserID') != user_id:
            effective_permissions.discard('pf_access')
        if not org or org.get('HistoricalPayrollManagerUserID') != user_id:
            effective_permissions.discard('historical_payroll_access')

    # Explicitly ensure Super Admin never gets payroll_access or pf_access
    if role_upper in ['SUPER ADMIN', 'SUPERADMIN']:
        effective_permissions.discard('payroll_access')
        effective_permissions.discard('pf_access')
        
    return list(effective_permissions)




class DynamoDBAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.session.get('user_id')
        if user_id:
            try:
                user_data = UsersTable.get_item({'UserID': user_id})
                if user_data:
                    session_token = request.session.get('session_token')
                    db_token = user_data.get('ActiveSessionToken')
                    
                    if db_token and session_token != db_token:
                        if 'user_id' in request.session:
                            del request.session['user_id']
                        if 'session_token' in request.session:
                            del request.session['session_token']
                        
                        path = request.path
                        if not (path.endswith('/notifications/poll/') or 
                                path.endswith('/api/register-device/') or 
                                path.endswith('/api/unregister-device/')):
                            messages.warning(request, "Your session has been terminated because you logged in on another device.")
                            return redirect('login')
                        
                        request.user = DynamoAnonymousUser()
                    else:
                        # optionally fetch employee details to enrich user object
                        emp_id = user_data.get('EmployeeID')
                        emp_data = None
                        if emp_id:
                            emp_data = EmployeesTable.get_item({'EmployeeID': emp_id})
                            if emp_data:
                                user_data['FirstName'] = emp_data.get('FirstName', '')
                                user_data['LastName'] = emp_data.get('LastName', '')
                                user_data['PassportPhoto'] = emp_data.get('PassportPhoto')
                                user_data['OnboardingStatus'] = emp_data.get('OnboardingStatus', 'Approved')
                                user_data['RejectionReason'] = emp_data.get('RejectionReason', '')

                        # Ensure OrgID resolution
                        if not user_data.get('OrgID') and emp_data and emp_data.get('OrgID'):
                            user_data['OrgID'] = emp_data.get('OrgID')

                        role_upper = (user_data.get('Role') or '').strip().upper()
                        if role_upper not in ['PLATFORM ADMIN', 'PLATFORM SUPER ADMIN'] and not user_data.get('OrgID'):
                            from core.dynamodb_service import OrganizationsTable
                            try:
                                all_orgs = OrganizationsTable.scan()
                                if all_orgs:
                                    fallback_org = all_orgs[0]
                                    fallback_org_id = fallback_org.get('OrgID')
                                    if fallback_org_id:
                                        user_data['OrgID'] = fallback_org_id
                                        # Auto-persist OrgID to DB for this user
                                        try:
                                            UsersTable._get_table().update_item(
                                                Key={'UserID': user_id},
                                                UpdateExpression="SET OrgID = :oid",
                                                ExpressionAttributeValues={":oid": fallback_org_id}
                                            )
                                            if emp_id:
                                                EmployeesTable._get_table().update_item(
                                                    Key={'EmployeeID': emp_id},
                                                    UpdateExpression="SET OrgID = :oid",
                                                    ExpressionAttributeValues={":oid": fallback_org_id}
                                                )
                                        except Exception as err:
                                            logger.error(f"Failed to auto-update OrgID on DB: {err}")
                            except Exception as err:
                                logger.error(f"Error resolving fallback OrgID: {err}")

                        if not user_data.get('IsActive', True):
                            if 'user_id' in request.session:
                                del request.session['user_id']
                            from django.contrib import messages
                            messages.error(request, "This profile is deactivated. Please contact HR to reactivate.")
                            request.user = DynamoAnonymousUser()
                        else:
                            request.user = DynamoUser(user_data)

                            # Load organization context
                            org_id = request.user.org_id
                            org = None
                            if org_id:
                                org = _get_org_cached(org_id)
                            
                            if not org:
                                from core.dynamodb_service import OrganizationsTable
                                try:
                                    all_orgs = OrganizationsTable.scan()
                                    if all_orgs:
                                        org = all_orgs[0]
                                        org_id = org.get('OrgID')
                                        request.user.org_id = org_id
                                except Exception as err:
                                    logger.error(f"Error resolving org fallback in middleware: {err}")

                            if org:
                                request.user.org = org
                                request.org = org
                                raw_plan = org.get('Plan')
                                if not raw_plan or str(raw_plan).strip().lower() in ['none', 'null', '']:
                                    plan = 'professional'
                                else:
                                    plan = str(raw_plan).strip().lower()
                                
                                if plan in ['whitelabel', 'custom', 'unlimited']:
                                    plan = 'professional'
                                
                                request.user.plan = plan
                                plan_features = PLAN_FEATURES.get(plan, PLAN_FEATURES.get('professional', []))
                                custom_features = org.get('CustomFeatures', []) or []
                                request.user.features = list(set(plan_features) | set(custom_features))
                            else:
                                request.user.plan = 'professional'
                                request.user.features = PLAN_FEATURES.get('professional', [])
                            
                            # Resolve and assign user permissions
                            request.user.permissions = get_user_permissions(user_data, org)
                            
                            # Update LastActivityTime in the database for non-polling page requests
                            path = request.path
                            if not (path.endswith('/notifications/poll/') or 
                                    path.endswith('/api/register-device/') or 
                                    path.endswith('/api/unregister-device/')):
                                import time
                                try:
                                    UsersTable.update_item(
                                        Key={'UserID': user_id},
                                        UpdateExpression="SET LastActivityTime = :act_time",
                                        ExpressionAttributeValues={":act_time": int(time.time())}
                                    )
                                except Exception as e:
                                    logger.error(f"Error updating LastActivityTime: {e}")
                else:
                    request.user = DynamoAnonymousUser()
            except Exception as e:
                logger.error(f"Error fetching user from dynamodb: {e}")
                request.user = DynamoAnonymousUser()
        else:
            request.user = DynamoAnonymousUser()
        
        # Enforce Platform Admin route restrictions: they can only access dashboard, organizations, and billing.
        if hasattr(request, 'user') and request.user.is_authenticated and request.user.role == 'Platform Admin':
            from django.urls import resolve, Resolver404
            try:
                match = resolve(request.path_info)
                url_name = match.url_name
            except Resolver404:
                url_name = None

            is_static_or_media = (
                request.path.startswith('/static/') or 
                request.path.startswith('/media/') or 
                request.path_info.startswith('/static/') or 
                request.path_info.startswith('/media/')
            )
            
            allowed_url_names = {
                'login',
                'logout',
                'forgot_password',
                'reset_password',
                'forbidden_403',
                'index',
                'dashboard_redirect',
                'platform_dashboard',
                'platform_org_list',
                'platform_create_org',
                'platform_edit_org',
                'platform_org_workflows',
                'platform_renew_org',
                'platform_create_org_admin',
                'platform_billing',
                'platform_reset_database',
                'billing_invoice_detail',
                'settings',
                'sitemap',
                'robots_txt',
                'favicon',
                'manifest_json',
                'service_worker_js',
                'offline',
            }

            if not is_static_or_media and url_name and url_name not in allowed_url_names:
                from django.shortcuts import redirect
                return redirect('forbidden_403')

        response = self.get_response(request)
        
        # Prevent caching of all pages to secure browser history (Back/Forward)
        # This ensures that 'Back' clicks always hit the server to trigger session checks.
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
            
        return response


class SessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            from core.utils import is_mobile_app
            if not is_mobile_app(request):
                # Skip checking for programmatic background/polling requests and explicit logouts
                path = request.path
                if not (path.endswith('/notifications/poll/') or 
                        path.endswith('/api/register-device/') or 
                        path.endswith('/api/unregister-device/') or
                        '/logout/' in path):
                    
                    last_activity = request.session.get('last_activity')
                    now = time.time()
                    TIMEOUT_SECONDS = 3600  # 1 hour
                    
                    if last_activity:
                        elapsed = now - last_activity
                        if elapsed > TIMEOUT_SECONDS:
                            user_id = request.session.get('user_id')
                            if user_id:
                                try:
                                    UsersTable.update_item(
                                        Key={'UserID': user_id},
                                        UpdateExpression="REMOVE ActiveSessionToken, LastActivityTime"
                                    )
                                except Exception as e:
                                    logger.error(f"Error clearing active session on timeout: {e}")
                            
                            # Flush the session
                            if 'user_id' in request.session:
                                del request.session['user_id']
                            if 'last_activity' in request.session:
                                del request.session['last_activity']
                            
                            messages.warning(request, "Your session has expired due to inactivity. Please log in again.")
                            return redirect('login')
                    
                    request.session['last_activity'] = now
                
        response = self.get_response(request)
        return response


class PolicyAcknowledgmentMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            user = request.user
            role = (getattr(user, 'role', '') or '').strip().upper()
            
            # Super admin and Platform Admin are exempt
            if role not in ['SUPER ADMIN', 'SUPERADMIN', 'PLATFORM ADMIN', 'PLATFORM SUPER ADMIN']:
                from django.urls import resolve, Resolver404
                try:
                    match = resolve(request.path_info)
                    url_name = match.url_name
                except Resolver404:
                    url_name = None

                path = request.path
                is_static_or_media = (
                    path.startswith('/static/') or 
                    path.startswith('/media/') or 
                    path.startswith('/sitemap.xml') or 
                    path.startswith('/robots.txt') or 
                    path.startswith('/favicon.ico') or 
                    path.startswith('/manifest.json') or 
                    path.startswith('/service-worker.js')
                )

                allowed_url_names = {
                    'policies',
                    'add_policy',
                    'edit_policy',
                    'delete_policy',
                    'approve_policy',
                    'reject_policy',
                    'acknowledge_policy',
                    'notification_poll',
                    'register_device',
                    'unregister_device',
                    'login',
                    'logout',
                    'forgot_password',
                    'reset_password',
                    'hr_dashboard',
                    'manager_dashboard',
                    'employee_dashboard',
                    'index',
                    'dashboard_redirect',
                    'offline',
                    'forbidden_403',
                }

                if not is_static_or_media and url_name and url_name not in allowed_url_names:
                    try:
                        from core.dynamodb_service import PoliciesTable, PolicyAcknowledgementsTable
                        
                        # Fetch all approved policies for this organization
                        all_policies = PoliciesTable.scan(
                            FilterExpression="OrgID = :oid AND ApprovalStatus = :status",
                            ExpressionAttributeValues={':oid': user.org_id, ':status': 'Approved'}
                        )
                        
                        if all_policies:
                            emp_id = getattr(user, 'employee_id', None) or user.user_id
                            
                            # Fetch all acknowledgments by this employee
                            user_acks = PolicyAcknowledgementsTable.scan(
                                FilterExpression="EmployeeID = :eid AND OrgID = :oid",
                                ExpressionAttributeValues={':eid': emp_id, ':oid': user.org_id}
                            )
                            
                            acked_policy_ids = {ack.get('PolicyID') for ack in user_acks if ack.get('PolicyID')}
                            
                            # Check if there is any policy not yet acknowledged
                            pending_policies = [p for p in all_policies if p.get('PolicyID') not in acked_policy_ids]
                            
                            if pending_policies:
                                from django.shortcuts import render
                                return render(request, 'core/please_acknowledge.html', {
                                    'pending_policies': pending_policies
                                })
                    except Exception as e:
                        logger.error(f"Error checking pending policies in middleware: {e}")

        response = self.get_response(request)
        return response


