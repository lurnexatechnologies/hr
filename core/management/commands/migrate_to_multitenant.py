from django.core.management.base import BaseCommand
from core.dynamodb_service import (
    OrganizationsTable, UsersTable, EmployeesTable, ReportingHierarchyTable,
    LeaveRequestsTable, AttendanceTable, PayslipsTable, ExpensesTable,
    ResignationsTable, HolidaysTable, PoliciesTable, OnboardingTokensTable,
    LoginHistoryTable, PasswordResetTokensTable, NotificationsTable,
    SettingsTable, WFHRequestsTable, PFSettingsTable, PFTransactionsTable,
    PayrollApprovalsTable, EmployeeLettersTable, AssetsTable, OKRsTable,
    AssetRequestsTable, AppraisalCyclesTable, AppraisalsTable, DeviceTokensTable
)
import datetime

class Command(BaseCommand):
    help = 'Migrate all existing DynamoDB table records to default ORG-LURNEXA organization for multi-tenancy'

    def handle(self, *args, **options):
        self.stdout.write("Starting multi-tenant database migration...")

        # 1. Create default organization if not exists
        default_org_id = "ORG-LURNEXA"
        try:
            org = OrganizationsTable.get_item({'OrgID': default_org_id})
            if not org:
                org_item = {
                    'OrgID': default_org_id,
                    'Name': 'Lurnexa Default',
                    'Slug': 'lurnexa-default',
                    'Plan': 'professional',
                    'CustomFeatures': [],
                    'MaxEmployees': 9999,
                    'Status': 'active',
                    'CreatedAt': datetime.datetime.now().isoformat(),
                    'CreatedBy': 'SYSTEM'
                }
                OrganizationsTable.put_item(org_item)
                self.stdout.write(self.style.SUCCESS(f"Created default organization: {default_org_id}"))
            else:
                self.stdout.write(f"Default organization {default_org_id} already exists.")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error checking/creating default org: {e}"))
            return

        # 2. Map of tables with their primary keys (hash and optional range keys)
        table_mappings = [
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

        # 3. Iterate and backfill OrgID on each table
        for table_service, key_fields in table_mappings:
            table_name = table_service.table_name
            self.stdout.write(f"Scanning and migrating table: {table_name}...")
            try:
                items = table_service.scan()
                updated_count = 0
                for item in items:
                    if 'OrgID' not in item:
                        # Extract the key fields
                        key = {kf: item[kf] for kf in key_fields if kf in item}
                        if len(key) == len(key_fields):
                            table_service.update_item(
                                Key=key,
                                UpdateExpression="SET OrgID = :oid",
                                ExpressionAttributeValues={":oid": default_org_id}
                            )
                            updated_count += 1
                if updated_count > 0:
                    self.stdout.write(self.style.SUCCESS(f"Successfully migrated {updated_count} items in {table_name}."))
                else:
                    self.stdout.write(f"No pending updates for table {table_name}.")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error migrating table {table_name}: {e}"))

        self.stdout.write(self.style.SUCCESS("All tables migrated to multi-tenancy successfully!"))
