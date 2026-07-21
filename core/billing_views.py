from django.views import View
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from auth_custom.mixins import RoleRequiredMixin
from core.dynamodb_service import OrganizationsTable, SubscriptionsTable, EmployeesTable
import datetime


class InvoiceDetailView(RoleRequiredMixin, View):
    allowed_roles = ['Super admin', 'Platform Admin']

    def get(self, request, period_start):
        user_role = getattr(request.user, 'role', None)
        if user_role == 'Platform Admin':
            org_id = request.GET.get('org_id')
            fallback_redirect = 'platform_billing'
        else:
            org_id = getattr(request.user, 'org_id', None)
            fallback_redirect = 'tenant_billing_dashboard'

        if not org_id:
            messages.error(request, "Organization context not found.")
            return redirect(fallback_redirect)

        org = OrganizationsTable.get_item({'OrgID': org_id})
        if not org:
            messages.error(request, "Organization not found.")
            return redirect(fallback_redirect)

        # Fetch the specific subscription record
        try:
            subs = SubscriptionsTable.query(
                KeyConditionExpression="OrgID = :oid",
                ExpressionAttributeValues={":oid": org_id}
            )
            sub = next((s for s in subs if s.get('PeriodStart', '').replace(':', '%3A') == period_start or s.get('PeriodStart', '') == period_start), None)
        except Exception:
            sub = None

        if not sub:
            messages.error(request, "Invoice not found.")
            return redirect('tenant_billing_dashboard')

        # Parse amounts
        try:
            base_amount = float(sub.get('Amount', 0))
        except (ValueError, TypeError):
            base_amount = 0.0

        try:
            plan_rate = float(org.get('PlanRate', 0))
        except (ValueError, TypeError):
            plan_rate = 0.0

        try:
            billing_seats = int(org.get('BillingSeats', 0))
        except (ValueError, TypeError):
            billing_seats = 0

        try:
            discount_pct = float(org.get('DiscountPercent', 0))
        except (ValueError, TypeError):
            discount_pct = 0.0

        # Calculate breakdown
        gross_amount = plan_rate * billing_seats if plan_rate and billing_seats else base_amount
        discount_amount = round(gross_amount * (discount_pct / 100), 2)
        net_amount = round(gross_amount - discount_amount, 2)
        gst_amount = round(net_amount * 0.18, 2)
        total_amount = round(net_amount + gst_amount, 2)

        # Generate invoice number from period start
        period_start_clean = sub.get('PeriodStart', '').split('T')[0]
        period_end_clean = sub.get('PeriodEnd', '').split('T')[0]
        inv_number = f"INV-{org_id[:6].upper()}-{period_start_clean.replace('-', '')}"

        invoice = {
            'InvoiceNumber': inv_number,
            'InvoiceDate': period_start_clean,
            'OrgID': org_id,
            'OrgName': org.get('Name', 'Organization'),
            'Plan': sub.get('Plan', 'basic'),
            'PlanRate': plan_rate,
            'BillingSeats': billing_seats,
            'PeriodStart': period_start_clean,
            'PeriodEnd': period_end_clean,
            'BaseAmount': f"{gross_amount:,.2f}",
            'DiscountPercent': discount_pct,
            'DiscountAmount': f"{discount_amount:,.2f}",
            'NetAmount': f"{net_amount:,.2f}",
            'GSTAmount': f"{gst_amount:,.2f}",
            'TotalAmount': f"{total_amount:,.2f}",
            'TransactionID': sub.get('TransactionID', ''),
            'Gateway': sub.get('Gateway', 'Platform'),
            'Status': sub.get('Status', 'Paid'),
        }

        return render(request, 'billing/invoice.html', {'invoice': invoice})

class TenantBillingDashboardView(RoleRequiredMixin, View):
    allowed_roles = ['Super admin']

    def get(self, request):
        org_id = getattr(request.user, 'org_id', None)
        if not org_id:
            messages.error(request, "Organization context not found.")
            return redirect('super_admin_dashboard')

        org = OrganizationsTable.get_item({'OrgID': org_id})
        if not org:
            messages.error(request, "Organization not found.")
            return redirect('super_admin_dashboard')

        try:
            invoices = SubscriptionsTable.query(
                KeyConditionExpression="OrgID = :oid",
                ExpressionAttributeValues={":oid": org_id}
            )
        except Exception:
            invoices = []

        invoices = sorted(invoices, key=lambda x: x.get('PeriodStart', ''), reverse=True)
        for inv in invoices:
            try:
                inv['DisplayAmount'] = round(float(inv.get('Amount', 0.0)) * 1.18, 2)
            except (ValueError, TypeError):
                inv['DisplayAmount'] = 0.0

        try:
            current_count = len(EmployeesTable.scan(
                FilterExpression="OrgID = :oid AND IsActive = :active",
                ExpressionAttributeValues={":oid": org_id, ":active": True}
            ))
        except Exception:
            current_count = 0

        from core.features import PLAN_LIMITS
        plan = org.get('Plan', 'basic').lower()
        if plan == 'whitelabel':
            plan = 'professional'
        max_emp = org.get('MaxEmployees') or PLAN_LIMITS.get(plan, {}).get('max_employees', 25)

        context = {
            'org': org,
            'plan': plan,
            'max_employees': max_emp,
            'current_employees': current_count,
            'usage_pct': min(100, int((current_count / max_emp) * 100)) if max_emp else 100,
            'invoices': invoices,
        }
        return render(request, 'billing/dashboard.html', context)

class TenantBillingPaymentView(RoleRequiredMixin, View):
    allowed_roles = ['Super admin']

    def post(self, request):
        import uuid
        org_id = getattr(request.user, 'org_id', None)
        if not org_id:
            return JsonResponse({'success': False, 'message': 'Org context missing'})

        plan = request.POST.get('plan', 'basic').lower()
        amount = request.POST.get('amount', '0').strip()
        
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        period_start = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        period_end = (datetime.date.today() + datetime.timedelta(days=365)).isoformat() + "T23:59:59Z"

        org = OrganizationsTable.get_item({'OrgID': org_id})
        if org:
            org['Plan'] = plan
            from core.features import PLAN_LIMITS
            org['MaxEmployees'] = PLAN_LIMITS.get(plan, {}).get('max_employees', 25)
            OrganizationsTable.put_item(org)

        sub_item = {
            'OrgID': org_id,
            'PeriodStart': period_start,
            'PeriodEnd': period_end,
            'Plan': plan,
            'Amount': amount,
            'TransactionID': payment_id,
            'Status': 'Paid',
            'Gateway': 'Stripe',
        }
        SubscriptionsTable.put_item(sub_item)
        
        messages.success(request, f"Successfully upgraded to {plan.title()} plan!")
        return JsonResponse({'success': True, 'transaction_id': payment_id})

class PlatformBillingView(RoleRequiredMixin, View):
    allowed_roles = ['Platform Admin']

    def get(self, request):
        try:
            subscriptions = SubscriptionsTable.scan()
        except Exception:
            subscriptions = []

        try:
            orgs = OrganizationsTable.scan()
        except Exception:
            orgs = []

        org_map = {o.get('OrgID'): o.get('Name', 'Unnamed') for o in orgs}
        
        total_revenue = 0.0
        enriched_subs = []
        for sub in subscriptions:
            try:
                amt = float(sub.get('Amount', 0.0))
            except ValueError:
                amt = 0.0
            
            # Apply 18% GST to all subscription amounts
            display_amt = amt * 1.18
            total_revenue += display_amt
            
            enriched_subs.append({
                'OrgID': sub.get('OrgID'),
                'OrgName': org_map.get(sub.get('OrgID'), 'Unknown'),
                'PeriodStart': sub.get('PeriodStart', '').split('T')[0],
                'RawPeriodStart': sub.get('PeriodStart', ''),
                'PeriodEnd': sub.get('PeriodEnd', '').split('T')[0],
                'Plan': 'professional' if sub.get('Plan', 'basic').lower() == 'whitelabel' else sub.get('Plan', 'basic'),
                'Amount': round(display_amt, 2),
                'TransactionID': sub.get('TransactionID'),
                'Status': sub.get('Status'),
                'Gateway': sub.get('Gateway', 'Platform'),
            })

        enriched_subs = sorted(enriched_subs, key=lambda x: x.get('PeriodStart', ''), reverse=True)

        context = {
            'subscriptions': enriched_subs,
            'total_revenue': round(total_revenue, 2),
            'orgs_count': len(orgs),
            'organizations': sorted(orgs, key=lambda o: o.get('Name', '').lower()),
        }
        return render(request, 'platform/billing.html', context)
