from django.views import View
from django.shortcuts import render, redirect
from django.contrib import messages
from auth_custom.mixins import RoleRequiredMixin
from core.dynamodb_service import OrganizationsTable, UsersTable, EmployeesTable, SubscriptionsTable, DepartmentsTable
from core.features import FEATURE_REGISTRY, PLAN_FEATURES, PLAN_LIMITS
import bcrypt
import datetime
from decimal import Decimal


class PlatformDashboardView(RoleRequiredMixin, View):
    allowed_roles = ['Platform Admin']

    def get(self, request):
        # Fetch all orgs
        try:
            orgs = OrganizationsTable.scan()
        except Exception:
            orgs = []

        # Fetch all employees
        try:
            all_emps = EmployeesTable.scan()
        except Exception:
            all_emps = []

        # Fetch all users for dashboard metric
        try:
            all_users = UsersTable.scan()
        except Exception:
            all_users = []

        # Fetch all subscriptions for revenue
        try:
            subscriptions = SubscriptionsTable.scan()
        except Exception:
            subscriptions = []

        # Compute metrics
        total_orgs = len(orgs)
        active_orgs = sum(1 for o in orgs if o.get('Status', 'active') == 'active')
        suspended_orgs = total_orgs - active_orgs
        total_employees = len(all_emps)
        total_users = len(all_users)

        # Plan distribution
        plan_dist = {}
        for org in orgs:
            p = org.get('Plan', 'basic').lower()
            if p == 'whitelabel':
                p = 'professional'
            p = p.capitalize()
            plan_dist[p] = plan_dist.get(p, 0) + 1

        # Revenue
        total_revenue = 0.0
        for sub in subscriptions:
            try:
                amt = float(sub.get('Amount', 0))
                if sub.get('Gateway') == 'Platform':
                    total_revenue += amt
                else:
                    total_revenue += amt * 1.18
            except (ValueError, TypeError):
                pass

        # Employee distribution per org (top 5)
        emp_counts = {}
        single_org_id = orgs[0].get('OrgID') if len(orgs) == 1 else None
        for emp in all_emps:
            oid = emp.get('OrgID') or single_org_id
            if oid:
                emp_counts[oid] = emp_counts.get(oid, 0) + 1

        org_name_map = {o.get('OrgID'): o.get('Name', 'Unnamed') for o in orgs}
        top_orgs = sorted(emp_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_orgs_data = [{'name': org_name_map.get(oid, oid), 'count': cnt} for oid, cnt in top_orgs]

        # Recent orgs (sorted by creation, most recent first, top 5)
        recent_orgs = sorted(orgs, key=lambda x: x.get('CreatedAt', ''), reverse=True)[:5]
        recent_orgs_data = []
        for o in recent_orgs:
            p = o.get('Plan', 'basic').lower()
            if p == 'whitelabel':
                p = 'professional'
            recent_orgs_data.append({
                'OrgID': o.get('OrgID'),
                'Name': o.get('Name', 'Unnamed'),
                'Plan': p,
                'Status': o.get('Status', 'active'),
                'CreatedAt': o.get('CreatedAt', '')[:10],
            })

        context = {
            'total_orgs': total_orgs,
            'active_orgs': active_orgs,
            'suspended_orgs': suspended_orgs,
            'total_employees': total_employees,
            'total_users': total_users,
            'total_revenue': total_revenue,
            'plan_distribution': plan_dist,
            'top_orgs': top_orgs_data,
            'recent_orgs': recent_orgs_data,
            'total_subscriptions': len(subscriptions),
        }
        return render(request, 'platform/dashboard.html', context)


class PlatformOrgListView(RoleRequiredMixin, View):
    allowed_roles = ['Platform Admin']

    def get(self, request):
        try:
            orgs = OrganizationsTable.scan()
        except Exception as e:
            messages.error(request, f"Error scanning organizations: {e}")
            orgs = []

        try:
            all_emps = EmployeesTable.scan()
        except Exception:
            all_emps = []

        try:
            all_users = UsersTable.scan()
        except Exception:
            all_users = []

        emp_counts = {}
        for emp in all_emps:
            oid = emp.get('OrgID')
            if oid:
                emp_counts[oid] = emp_counts.get(oid, 0) + 1

        org_admins = {}
        for u in all_users:
            oid = u.get('OrgID')
            role = u.get('Role')
            if oid and role in ['Super admin', 'HR ADMIN']:
                if oid not in org_admins:
                    org_admins[oid] = []
                org_admins[oid].append({
                    'Email': u.get('Email'),
                    'Role': role
                })

        enriched_orgs = []
        for org in orgs:
            oid = org.get('OrgID')
            plan = org.get('Plan', 'basic')
            
            # Normalize WHITELABEL to professional
            if plan.lower() == 'whitelabel':
                plan = 'professional'
                
            max_emp = org.get('MaxEmployees') or PLAN_LIMITS.get(plan, {}).get('max_employees', 25)
            admins = org_admins.get(oid, [])

            enriched_orgs.append({
                'OrgID': oid,
                'Name': org.get('Name', 'Unnamed'),
                'Slug': org.get('Slug', ''),
                'Plan': plan,
                'Status': org.get('Status', 'active'),
                'CreatedAt': org.get('CreatedAt', ''),
                'EmployeeCount': emp_counts.get(oid, 0),
                'MaxEmployees': max_emp,
                'Admins': admins,
            })

        context = {
            'organizations': enriched_orgs
        }
        return render(request, 'platform/org_list.html', context)

class PlatformCreateOrgView(RoleRequiredMixin, View):
    allowed_roles = ['Platform Admin']

    def get(self, request):
        context = {
            'feature_registry': FEATURE_REGISTRY,
            'plan_features': PLAN_FEATURES,
            'plans': PLAN_LIMITS.keys(),
            'subscription_history': [],
            'active_sub': None,
        }
        return render(request, 'platform/org_form.html', context)

    def post(self, request):
        import uuid
        org_id = request.POST.get('org_id', '').strip()
        name = request.POST.get('name', '').strip()
        plan = request.POST.get('plan', 'basic')
        status = request.POST.get('status', 'active')
        max_employees = request.POST.get('max_employees', '').strip()
        custom_features = request.POST.getlist('custom_features')

        # Calculator inputs
        plan_rate = request.POST.get('plan_rate', '50').strip()
        billing_seats = request.POST.get('billing_seats', '25').strip()
        discount_percent = request.POST.get('discount_percent', '0').strip()
        billing_amount = request.POST.get('billing_amount', '0.00').strip()
        term_start = request.POST.get('term_start', '').strip()
        term_end = request.POST.get('term_end', '').strip()
        payment_mode = request.POST.get('payment_mode', 'Platform').strip()
        transaction_id_input = request.POST.get('transaction_id', '').strip()

        if not org_id or not name:
            messages.error(request, "Organization ID and Name are required.")
            return self.get(request)

        if payment_mode != 'Cash' and not transaction_id_input:
            messages.error(request, f"Proof ID / Transaction ID is required for {payment_mode} payments.")
            return self.get(request)

        try:
            # Check if OrgID already exists
            existing = OrganizationsTable.get_item({'OrgID': org_id})
            if existing:
                messages.error(request, f"Organization ID '{org_id}' already exists.")
                return self.get(request)
        except Exception:
            pass

        try:
            plan_rate_val = float(plan_rate)
        except ValueError:
            plan_rate_val = 50.0

        try:
            billing_seats_val = int(billing_seats)
        except ValueError:
            billing_seats_val = 25

        try:
            discount_percent_val = float(discount_percent)
        except ValueError:
            discount_percent_val = 0.0

        try:
            billing_amount_val = float(billing_amount)
        except ValueError:
            billing_amount_val = 0.0

        hierarchy_mode = request.POST.get('hierarchy_mode', 'flat').strip()

        org_item = {
            'OrgID': org_id,
            'Name': name,
            'Slug': org_id.lower(),
            'Plan': plan,
            'Status': status,
            'CustomFeatures': custom_features,
            'CreatedAt': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'PlanRate': Decimal(str(plan_rate_val)),
            'BillingSeats': billing_seats_val,
            'DiscountPercent': Decimal(str(discount_percent_val)),
            'BillingAmount': Decimal(str(round(billing_amount_val * 1.18, 2))),
            'TermStart': term_start,
            'TermEnd': term_end,
            'HierarchyMode': hierarchy_mode,
        }

        if max_employees:
            try:
                org_item['MaxEmployees'] = int(max_employees)
            except ValueError:
                pass

        try:
            OrganizationsTable.put_item(org_item)

            # Log this as a subscription transaction so it reflects in global revenue
            payment_id = "" if payment_mode == 'Cash' else transaction_id_input
            period_start = f"{term_start}T00:00:00Z" if term_start else datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            period_end = f"{term_end}T23:59:59Z" if term_end else (datetime.date.today() + datetime.timedelta(days=365)).isoformat() + "T23:59:59Z"

            sub_item = {
                'OrgID': org_id,
                'PeriodStart': period_start,
                'PeriodEnd': period_end,
                'Plan': plan.lower(),
                'Amount': str(billing_amount_val),
                'TransactionID': payment_id,
                'Status': 'Paid',
                'Gateway': payment_mode,
            }
            SubscriptionsTable.put_item(sub_item)

            messages.success(request, f"Organization '{name}' created successfully with plan transaction registered.")
            return redirect('platform_org_list')
        except Exception as e:
            messages.error(request, f"Error saving organization: {e}")
            return self.get(request)

class PlatformEditOrgView(RoleRequiredMixin, View):
    allowed_roles = ['Platform Admin']

    def get(self, request, org_id):
        try:
            org = OrganizationsTable.get_item({'OrgID': org_id})
        except Exception as e:
            messages.error(request, f"Error fetching organization: {e}")
            return redirect('platform_org_list')

        if not org:
            messages.error(request, "Organization not found.")
            return redirect('platform_org_list')

        if org.get('Plan', '').lower() == 'whitelabel':
            org['Plan'] = 'professional'

        # Get subscription history
        try:
            subs = SubscriptionsTable.query(
                KeyConditionExpression="OrgID = :oid",
                ExpressionAttributeValues={":oid": org_id}
            )
            subs = sorted(subs, key=lambda x: x.get('PeriodStart', ''), reverse=True)
        except Exception:
            subs = []

        subscription_history = []
        active_sub = None
        for i, sub in enumerate(subs):
            try:
                amt = float(sub.get('Amount', 0.0))
            except (ValueError, TypeError):
                amt = 0.0
            
            amount_paid = round(amt * 1.18, 2)
            
            sub_status = "Paid"
            try:
                pe_str = sub.get('PeriodEnd', '').split('T')[0]
                pe_date = datetime.datetime.strptime(pe_str, '%Y-%m-%d').date()
                if pe_date < datetime.date.today():
                    sub_status = "Expired"
                else:
                    sub_status = "Active"
            except Exception:
                pass
                
            sub_history_item = {
                'Plan': sub.get('Plan', 'basic').upper(),
                'AmountPaid': amount_paid,
                'TransactionID': sub.get('TransactionID'),
                'PeriodStart': sub.get('PeriodStart', '').split('T')[0],
                'PeriodEnd': sub.get('PeriodEnd', '').split('T')[0],
                'Status': sub_status,
                'Gateway': sub.get('Gateway', 'Platform'),
            }
            subscription_history.append(sub_history_item)
            
            if i == 0:
                active_sub = sub_history_item

        org_users = []
        try:
            org_users = [u for u in UsersTable.scan() if u.get('OrgID') == org_id]
        except Exception:
            pass

        context = {
            'org': org,
            'feature_registry': FEATURE_REGISTRY,
            'plan_features': PLAN_FEATURES,
            'plans': PLAN_LIMITS.keys(),
            'custom_features_enabled': org.get('CustomFeatures', []),
            'subscription_history': subscription_history,
            'active_sub': active_sub,
            'org_users': org_users,
        }
        return render(request, 'platform/org_form.html', context)

    def post(self, request, org_id):
        import uuid
        name = request.POST.get('name', '').strip()
        plan = request.POST.get('plan', 'basic')
        status = request.POST.get('status', 'active')
        max_employees = request.POST.get('max_employees', '').strip()
        custom_features = request.POST.getlist('custom_features')

        # Calculator inputs
        plan_rate = request.POST.get('plan_rate', '50').strip()
        billing_seats = request.POST.get('billing_seats', '25').strip()
        discount_percent = request.POST.get('discount_percent', '0').strip()
        billing_amount = request.POST.get('billing_amount', '0.00').strip()
        term_start = request.POST.get('term_start', '').strip()
        term_end = request.POST.get('term_end', '').strip()
        payment_mode = request.POST.get('payment_mode', 'Platform').strip()
        transaction_id_input = request.POST.get('transaction_id', '').strip()

        if not name:
            messages.error(request, "Organization Name is required.")
            return self.get(request, org_id)

        if payment_mode != 'Cash' and not transaction_id_input:
            messages.error(request, f"Proof ID / Transaction ID is required for {payment_mode} payments.")
            return self.get(request, org_id)

        try:
            org = OrganizationsTable.get_item({'OrgID': org_id})
            if not org:
                messages.error(request, "Organization not found.")
                return redirect('platform_org_list')
        except Exception as e:
            messages.error(request, f"Error fetching organization: {e}")
            return redirect('platform_org_list')

        try:
            plan_rate_val = float(plan_rate)
        except ValueError:
            plan_rate_val = 50.0

        try:
            billing_seats_val = int(billing_seats)
        except ValueError:
            billing_seats_val = 25

        try:
            discount_percent_val = float(discount_percent)
        except ValueError:
            discount_percent_val = 0.0

        try:
            billing_amount_val = float(billing_amount)
        except ValueError:
            billing_amount_val = 0.0

        billing_amount_with_gst = round(billing_amount_val * 1.18, 2)

        try:
            old_plan_rate = float(org.get('PlanRate') or 0)
        except (ValueError, TypeError):
            old_plan_rate = 0.0

        try:
            old_billing_seats = int(org.get('BillingSeats') or 0)
        except (ValueError, TypeError):
            old_billing_seats = 0

        try:
            old_discount = float(org.get('DiscountPercent') or 0)
        except (ValueError, TypeError):
            old_discount = 0.0

        try:
            old_billing_amount = float(org.get('BillingAmount') or 0)
        except (ValueError, TypeError):
            old_billing_amount = 0.0

        billing_changed = (
            org.get('Plan') != plan or
            old_plan_rate != plan_rate_val or
            old_billing_seats != billing_seats_val or
            old_discount != discount_percent_val or
            old_billing_amount != billing_amount_with_gst or
            org.get('TermStart') != term_start or
            org.get('TermEnd') != term_end
        )

        org['Name'] = name
        org['Plan'] = plan
        org['Status'] = status
        org['CustomFeatures'] = custom_features
        org['PlanRate'] = Decimal(str(plan_rate_val))
        org['BillingSeats'] = billing_seats_val
        org['DiscountPercent'] = Decimal(str(discount_percent_val))
        org['BillingAmount'] = Decimal(str(billing_amount_with_gst))
        org['TermStart'] = term_start
        org['TermEnd'] = term_end
        org['HierarchyMode'] = request.POST.get('hierarchy_mode', 'flat').strip()

        if max_employees:
            try:
                org['MaxEmployees'] = int(max_employees)
            except ValueError:
                org['MaxEmployees'] = None
        else:
            org['MaxEmployees'] = None

        try:
            OrganizationsTable.put_item(org)

            if billing_changed:
                payment_id = "" if payment_mode == 'Cash' else transaction_id_input
                period_start = f"{term_start}T00:00:00Z" if term_start else datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                period_end = f"{term_end}T23:59:59Z" if term_end else (datetime.date.today() + datetime.timedelta(days=365)).isoformat() + "T23:59:59Z"

                sub_item = {
                    'OrgID': org_id,
                    'PeriodStart': period_start,
                    'PeriodEnd': period_end,
                    'Plan': plan.lower(),
                    'Amount': str(billing_amount_val),
                    'TransactionID': payment_id,
                    'Status': 'Paid',
                    'Gateway': payment_mode,
                }
                SubscriptionsTable.put_item(sub_item)
                messages.success(request, f"Organization '{name}' updated successfully and new billing transaction logged.")
            else:
                messages.success(request, f"Organization '{name}' updated successfully.")
            return redirect('platform_org_list')
        except Exception as e:
            messages.error(request, f"Error saving organization: {e}")
            return self.get(request, org_id)

class PlatformCreateOrgAdminView(RoleRequiredMixin, View):
    allowed_roles = ['Platform Admin']

    def get(self, request, org_id):
        try:
            org = OrganizationsTable.get_item({'OrgID': org_id})
        except Exception:
            org = None
        if not org:
            messages.error(request, "Organization not found.")
            return redirect('platform_org_list')

        context = {
            'org': org
        }
        return render(request, 'platform/admin_form.html', context)

    def post(self, request, org_id):
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role = request.POST.get('role', 'Super admin').strip()

        if role not in ['Super admin', 'HR ADMIN']:
            role = 'Super admin'

        if role == 'Super admin':
            try:
                all_users = UsersTable.scan()
                existing_sa = any(u.get('OrgID') == org_id and u.get('Role') == 'Super admin' for u in all_users)
                if existing_sa:
                    messages.error(request, f"Organization '{org_id}' already has a Super Admin. Only one Super Admin can exist per organization.")
                    return self.get(request, org_id)
            except Exception:
                pass

        if not email or not password or not first_name:
            messages.error(request, "Email, Password, and First Name are required.")
            return self.get(request, org_id)

        try:
            # Check if user already exists
            existing_user = UsersTable.get_item({'UserID': email})
            if existing_user:
                messages.error(request, f"User with email '{email}' already exists.")
                return self.get(request, org_id)
        except Exception:
            pass

        # Hash password using bcrypt exactly like onboarding and employee creation views
        hashed_pw = bcrypt.hashpw(password.encode('utf-8')[:72], bcrypt.gensalt()).decode('utf-8')
        
        # Let's count existing employees for this org to generate a unique Employee ID prefix
        try:
            all_emps = EmployeesTable.scan()
            org_emps_count = sum(1 for e in all_emps if e.get('OrgID') == org_id)
        except Exception:
            org_emps_count = 0
            
        role_code = 'SA' if role == 'Super admin' else 'HR'
        emp_id = f"{org_id.upper()}-{role_code}-{org_emps_count + 1:03d}"

        user_item = {
            'UserID': email,
            'Email': email,
            'Role': role,
            'PasswordHash': hashed_pw,
            'EmployeeID': emp_id,
            'IsActive': True,
            'OrgID': org_id,
        }

        emp_item = {
            'EmployeeID': emp_id,
            'UserID': email,
            'Email': email,
            'FirstName': first_name,
            'LastName': last_name,
            'Role': role,
            'OrgID': org_id,
            'IsActive': True,
            'OnboardingStatus': 'Approved',
        }

        try:
            UsersTable.put_item(user_item)
            EmployeesTable.put_item(emp_item)
            messages.success(request, f"{role} '{email}' created successfully for {org_id}.")
            return redirect('platform_org_list')
        except Exception as e:
            messages.error(request, f"Error creating user/employee: {e}")
            return self.get(request, org_id)

class PlatformRenewOrgView(RoleRequiredMixin, View):
    allowed_roles = ['Platform Admin']

    def post(self, request, org_id):
        import uuid
        plan = request.POST.get('renew_plan', 'basic').lower()
        plan_rate = request.POST.get('renew_plan_rate', '50').strip()
        billing_seats = request.POST.get('renew_billing_seats', '25').strip()
        discount_percent = request.POST.get('renew_discount_percent', '0').strip()
        term_start = request.POST.get('renew_term_start', '').strip()
        term_end = request.POST.get('renew_term_end', '').strip()
        payment_mode = request.POST.get('renew_payment_mode', 'Platform').strip()
        transaction_id_input = request.POST.get('renew_transaction_id', '').strip()

        if payment_mode != 'Cash' and not transaction_id_input:
            messages.error(request, f"Proof ID / Transaction ID is required for {payment_mode} renewal.")
            return redirect('platform_billing')

        try:
            org = OrganizationsTable.get_item({'OrgID': org_id})
            if not org:
                messages.error(request, "Organization not found.")
                return redirect('platform_org_list')
        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect('platform_org_list')

        # Parsing inputs
        try:
            plan_rate_val = float(plan_rate)
        except ValueError:
            plan_rate_val = 50.0

        try:
            billing_seats_val = int(billing_seats)
        except ValueError:
            billing_seats_val = 25

        try:
            discount_percent_val = float(discount_percent)
        except ValueError:
            discount_percent_val = 0.0

        base_amount = plan_rate_val * billing_seats_val * (1 - discount_percent_val / 100)
        billing_amount_with_gst = round(base_amount * 1.18, 2)

        # Update Org
        org['Plan'] = plan
        org['PlanRate'] = Decimal(str(plan_rate_val))
        org['BillingSeats'] = billing_seats_val
        org['DiscountPercent'] = Decimal(str(discount_percent_val))
        org['BillingAmount'] = Decimal(str(billing_amount_with_gst))
        
        if term_start:
            org['TermStart'] = term_start
        if term_end:
            org['TermEnd'] = term_end

        try:
            OrganizationsTable.put_item(org)

            # Create a new subscription record
            payment_id = "" if payment_mode == 'Cash' else transaction_id_input
            
            period_start = f"{term_start}T00:00:00Z" if term_start else datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            period_end = f"{term_end}T23:59:59Z" if term_end else (datetime.date.today() + datetime.timedelta(days=365)).isoformat() + "T23:59:59Z"

            sub_item = {
                'OrgID': org_id,
                'PeriodStart': period_start,
                'PeriodEnd': period_end,
                'Plan': plan.lower(),
                'Amount': str(base_amount),
                'TransactionID': payment_id,
                'Status': 'Paid',
                'Gateway': payment_mode,
            }
            SubscriptionsTable.put_item(sub_item)
            messages.success(request, f"Subscription for '{org.get('Name')}' renewed successfully!")
        except Exception as e:
            messages.error(request, f"Error renewing subscription: {e}")
            
        return redirect('platform_billing')


class PlatformOrgWorkflowsView(RoleRequiredMixin, View):
    allowed_roles = ['Platform Admin', 'Super admin']

    def get(self, request, org_id):
        # Multi-tenant safety check
        if request.user.role == 'Super admin' and request.user.org_id != org_id:
            return redirect('forbidden_403')

        try:
            org = OrganizationsTable.get_item({'OrgID': org_id})
        except Exception:
            org = None
        if not org:
            messages.error(request, "Organization not found.")
            if request.user.role == 'Super admin':
                return redirect('index')
            return redirect('platform_org_list')

        # Fetch departments
        try:
            departments = DepartmentsTable.scan(
                FilterExpression="OrgID = :oid",
                ExpressionAttributeValues={":oid": org_id}
            )
        except Exception:
            departments = []

        # Get existing workflow rules, or initialize with defaults
        workflow_rules = org.get('WorkflowRules')
        if not workflow_rules:
            workflow_rules = {}
        for r_type, defaults in [
            ('leave_request', {'Employee': ['Manager'], 'Manager': ['HR ADMIN'], 'HR ADMIN': ['Super admin'], 'Super admin': []}),
            ('expense_claim', {'Employee': ['Manager'], 'Manager': ['HR ADMIN'], 'HR ADMIN': ['Super admin'], 'Super admin': []}),
            ('wfh_request', {'Employee': ['Manager'], 'Manager': ['HR ADMIN'], 'HR ADMIN': ['Super admin'], 'Super admin': []}),
            ('payroll_approval', {'Employee': ['Manager', 'HR ADMIN', 'Super admin'], 'Manager': ['HR ADMIN', 'Super admin'], 'HR ADMIN': ['Super admin'], 'Super admin': []})
        ]:
            if r_type not in workflow_rules:
                workflow_rules[r_type] = defaults

        import json
        is_platform_admin = (request.user.role == 'Platform Admin')
        context = {
            'org': org,
            'departments': departments,
            'workflow_rules': workflow_rules,
            'workflow_rules_json': json.dumps(workflow_rules),
            'roles_list': ['Employee', 'Manager', 'HR ADMIN', 'Super admin'],
            'approvers_pool': ['Manager', 'Team Lead', 'HR ADMIN', 'Super admin'],
            'is_platform_admin': is_platform_admin
        }
        return render(request, 'platform/org_workflows.html', context)

    def post(self, request, org_id):
        # Multi-tenant safety check
        if request.user.role == 'Super admin' and request.user.org_id != org_id:
            return redirect('forbidden_403')

        # Read-only restriction for Platform Admin
        if request.user.role == 'Platform Admin':
            messages.error(request, "Platform Admins are only authorized to view workflows, not change them.")
            return redirect('platform_org_workflows', org_id=org_id)

        import uuid
        action = request.POST.get('action')
        try:
            org = OrganizationsTable.get_item({'OrgID': org_id})
        except Exception:
            org = None
        if not org:
            messages.error(request, "Organization not found.")
            if request.user.role == 'Super admin':
                return redirect('index')
            return redirect('platform_org_list')

        if action == 'create_department':
            dept_name = request.POST.get('department_name', '').strip()
            dept_desc = request.POST.get('department_desc', '').strip()
            if not dept_name:
                messages.error(request, "Department name is required.")
                return redirect('platform_org_workflows', org_id=org_id)

            dept_id = f"DEPT-{uuid.uuid4().hex[:6].upper()}"
            dept_item = {
                'OrgID': org_id,
                'DepartmentID': dept_id,
                'Name': dept_name,
                'Description': dept_desc,
                'CreatedAt': datetime.datetime.utcnow().isoformat()
            }
            try:
                DepartmentsTable.put_item(dept_item)
                messages.success(request, f"Department '{dept_name}' created successfully.")
            except Exception as e:
                messages.error(request, f"Error creating department: {e}")

        elif action == 'delete_department':
            dept_id = request.POST.get('department_id', '').strip()
            try:
                DepartmentsTable.delete_item({'OrgID': org_id, 'DepartmentID': dept_id})
                messages.success(request, "Department deleted successfully.")
            except Exception as e:
                messages.error(request, f"Error deleting department: {e}")

        elif action == 'save_workflows':
            new_rules = {
                'leave_request': {},
                'expense_claim': {},
                'wfh_request': {},
                'payroll_approval': {}
            }
            roles = ['Employee', 'Manager', 'HR ADMIN', 'Super admin']
            for req_type in ['leave_request', 'expense_claim', 'wfh_request', 'payroll_approval']:
                for r in roles:
                    steps_str = request.POST.get(f"{req_type}_{r}", "").strip()
                    if steps_str:
                        steps_list = [s.strip() for s in steps_str.split(',') if s.strip()]
                    else:
                        steps_list = []
                    new_rules[req_type][r] = steps_list

            org['WorkflowRules'] = new_rules
            try:
                OrganizationsTable.put_item(org)
                messages.success(request, "Workflow rules updated successfully.")
            except Exception as e:
                messages.error(request, f"Error saving workflow rules: {e}")

        return redirect('platform_org_workflows', org_id=org_id)


class PlatformResetDatabaseView(RoleRequiredMixin, View):
    allowed_roles = ['Platform Admin']

    def post(self, request):
        from core.dynamodb_service import (
            OrganizationsTable, UsersTable, EmployeesTable, ReportingHierarchyTable,
            LeaveRequestsTable, AttendanceTable, PayslipsTable, ExpensesTable,
            ResignationsTable, HolidaysTable, PoliciesTable, OnboardingTokensTable,
            LoginHistoryTable, PasswordResetTokensTable, NotificationsTable,
            SettingsTable, SubscriptionsTable, WFHRequestsTable, PFSettingsTable,
            PFTransactionsTable, PayrollApprovalsTable, EmployeeLettersTable,
            AssetsTable, OKRsTable, AssetRequestsTable, AppraisalCyclesTable,
            AppraisalsTable, DeviceTokensTable
        )
        import uuid
        import bcrypt

        current_user_email = getattr(request.user, 'email', 'lurnexasolution@gmail.com')
        current_user_id = getattr(request.user, 'id', str(uuid.uuid4()))

        tables_and_keys = [
            (OrganizationsTable, ['OrgID']),
            (UsersTable, ['UserID']),
            (EmployeesTable, ['EmployeeID']),
            (ReportingHierarchyTable, ['ManagerID', 'EmployeeID']),
            (LeaveRequestsTable, ['EmployeeID', 'LeaveDate']),
            (AttendanceTable, ['EmployeeID', 'RecordDate']),
            (PayslipsTable, ['EmployeeID', 'MonthYear']),
            (ExpensesTable, ['EmployeeID', 'RequestID']),
            (ResignationsTable, ['EmployeeID']),
            (HolidaysTable, ['HolidayID']),
            (PoliciesTable, ['PolicyID']),
            (OnboardingTokensTable, ['Token']),
            (LoginHistoryTable, ['UserID', 'LoginTime']),
            (PasswordResetTokensTable, ['Token']),
            (NotificationsTable, ['EmployeeID', 'Timestamp']),
            (SettingsTable, ['SettingKey']),
            (SubscriptionsTable, ['SubID']),
            (WFHRequestsTable, ['EmployeeID', 'RequestID']),
            (PFSettingsTable, ['SettingKey']),
            (PFTransactionsTable, ['EmployeeID', 'MonthYear']),
            (PayrollApprovalsTable, ['RequestID']),
            (EmployeeLettersTable, ['EmployeeID', 'LetterID']),
            (AssetsTable, ['AssetID']),
            (OKRsTable, ['EmployeeID', 'GoalID']),
            (AssetRequestsTable, ['EmployeeID', 'RequestID']),
            (AppraisalCyclesTable, ['CycleID']),
            (AppraisalsTable, ['EmployeeID', 'CycleID']),
            (DeviceTokensTable, ['EmployeeID', 'DeviceToken']),
        ]

        total_deleted = 0
        try:
            for tbl, key_fields in tables_and_keys:
                try:
                    items = tbl._get_table().scan().get('Items', [])
                    for item in items:
                        key = {k: item[k] for k in key_fields if k in item}
                        if len(key) == len(key_fields):
                            tbl._get_table().delete_item(Key=key)
                            total_deleted += 1
                except Exception as tbl_err:
                    print(f"Error resetting table {tbl.table_name}: {tbl_err}")

            # Re-seed Platform Admin User so current admin remains active
            plat_user_id = current_user_id or str(uuid.uuid4())
            plat_emp_id = 'LXP-PLAT-001'
            plat_pw_hash = bcrypt.hashpw('Password@123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            user_item = {
                'UserID': plat_user_id,
                'Email': current_user_email or 'lurnexasolution@gmail.com',
                'Role': 'Platform Admin',
                'PasswordHash': plat_pw_hash,
                'EmployeeID': plat_emp_id,
                'IsActive': True
            }
            UsersTable._get_table().put_item(Item=user_item)

            employee_item = {
                'EmployeeID': plat_emp_id,
                'UserID': plat_user_id,
                'Email': current_user_email or 'lurnexasolution@gmail.com',
                'FirstName': 'Lurnexa',
                'LastName': 'Technologies',
                'Department': 'Administration',
                'Designation': 'Platform Admin'
            }
            EmployeesTable._get_table().put_item(Item=employee_item)

            messages.success(request, f"Database reset completed successfully! Cleared {total_deleted} items across all tables. Platform Admin account preserved.")
        except Exception as e:
            messages.error(request, f"Error performing database reset: {e}")

        return redirect('platform_dashboard')
