import boto3
from django.conf import settings
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

def get_dynamodb_resource():
    """
    Always returns a fresh DynamoDB resource using current settings.
    This ensures that mock endpoints and credentials (dummy) are respected 
    even in multi-threaded/process environments.
    """
    endpoint = getattr(settings, 'DYNAMODB_ENDPOINT_URL', None)
    region = getattr(settings, 'AWS_DEFAULT_REGION', 'us-east-1')
    key = getattr(settings, 'AWS_ACCESS_KEY_ID', 'dummy')
    secret = getattr(settings, 'AWS_SECRET_ACCESS_KEY', 'dummy')

    if endpoint:
        return boto3.resource(
            'dynamodb',
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=key,
            aws_secret_access_key=secret
        )
    else:
        return boto3.resource('dynamodb', region_name=region)

class TableService:
    def __init__(self, table_name):
        self.table_name = table_name

    def _get_table(self):
        return get_dynamodb_resource().Table(self.table_name)

    def put_item(self, item):
        if self.table_name not in ['Lurnexa_Organizations', 'Lurnexa_Subscriptions']:
            org_id = None
            try:
                from core.middleware import get_current_request
                request = get_current_request()
                if request and hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False):
                    if getattr(request.user, 'role', None) != 'Platform Admin':
                        org_id = getattr(request.user, 'org_id', None)
            except Exception:
                pass
            if org_id and 'OrgID' not in item:
                item['OrgID'] = org_id
        return self._get_table().put_item(Item=item)

    def get_item(self, key):
        item = self._get_table().get_item(Key=key).get('Item')
        if item and self.table_name not in ['Lurnexa_Organizations', 'Lurnexa_Subscriptions']:
            org_id = None
            try:
                from core.middleware import get_current_request
                request = get_current_request()
                if request and hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False):
                    if getattr(request.user, 'role', None) != 'Platform Admin':
                        org_id = getattr(request.user, 'org_id', None)
            except Exception:
                pass
            if org_id and item.get('OrgID') and item.get('OrgID') != org_id:
                return None
        return item

    def delete_item(self, key):
        if self.table_name not in ['Lurnexa_Organizations', 'Lurnexa_Subscriptions']:
            item = self.get_item(key)
            if item is None:
                return None
        return self._get_table().delete_item(Key=key)
        
    def update_item(self, **kwargs):
        if self.table_name not in ['Lurnexa_Organizations', 'Lurnexa_Subscriptions']:
            key = kwargs.get('Key')
            if key:
                item = self.get_item(key)
                if item is None:
                    raise ClientError(
                        {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'Access Denied: Tenant Isolation Violation'}},
                        'UpdateItem'
                    )
        return self._get_table().update_item(**kwargs)

    def _apply_tenant_isolation(self, kwargs):
        if self.table_name in ['Lurnexa_Organizations', 'Lurnexa_Subscriptions']:
            return kwargs

        org_id = None
        try:
            from core.middleware import get_current_request
            request = get_current_request()
            if request and hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False):
                if getattr(request.user, 'role', None) != 'Platform Admin':
                    org_id = getattr(request.user, 'org_id', None)
        except Exception:
            pass

        if org_id:
            from boto3.dynamodb.conditions import Attr
            org_filter = Attr('OrgID').eq(org_id) | Attr('OrgID').not_exists()
            if 'FilterExpression' not in kwargs:
                kwargs['FilterExpression'] = org_filter
            else:
                expr = kwargs['FilterExpression']
                if isinstance(expr, str):
                    kwargs['FilterExpression'] = f"({expr}) AND (OrgID = :autogen_org_id OR attribute_not_exists(OrgID))"
                    if 'ExpressionAttributeValues' not in kwargs:
                        kwargs['ExpressionAttributeValues'] = {}
                    kwargs['ExpressionAttributeValues'][':autogen_org_id'] = org_id
                else:
                    kwargs['FilterExpression'] = expr & org_filter
        return kwargs

    def query(self, **kwargs):
        kwargs = self._apply_tenant_isolation(kwargs)
        table = self._get_table()
        limit = kwargs.get('Limit')
        response = table.query(**kwargs)
        items = response.get('Items', [])
        
        while 'LastEvaluatedKey' in response:
            if limit and len(items) >= limit:
                break
            kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            if limit:
                kwargs['Limit'] = limit - len(items)
            response = table.query(**kwargs)
            items.extend(response.get('Items', []))
        return items

    def scan(self, **kwargs):
        kwargs = self._apply_tenant_isolation(kwargs)
        table = self._get_table()
        limit = kwargs.get('Limit')
        response = table.scan(**kwargs)
        items = response.get('Items', [])
        
        while 'LastEvaluatedKey' in response:
            if limit and len(items) >= limit:
                break
            kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            if limit:
                kwargs['Limit'] = limit - len(items)
            response = table.scan(**kwargs)
            items.extend(response.get('Items', []))
        return items

# Pre-defined Table Services
UsersTable = TableService('Lurnexa_Users')
EmployeesTable = TableService('Lurnexa_Employees')
ReportingHierarchyTable = TableService('Lurnexa_ReportingHierarchy')
LeaveRequestsTable = TableService('Lurnexa_LeaveRequests')
AttendanceTable = TableService('Lurnexa_AttendanceRecords')
PayslipsTable = TableService('Lurnexa_Payslips')
ExpensesTable = TableService('Lurnexa_Expenses')
ResignationsTable = TableService('Lurnexa_Resignations')
HolidaysTable = TableService('Lurnexa_Holidays')
PoliciesTable = TableService('Lurnexa_Policies')
OnboardingTokensTable = TableService('Lurnexa_OnboardingTokens')
LoginHistoryTable = TableService('Lurnexa_LoginHistory')
PasswordResetTokensTable = TableService('Lurnexa_PasswordResetTokens')
NotificationsTable = TableService('Lurnexa_Notifications')
SettingsTable = TableService('Lurnexa_Settings')
WFHRequestsTable = TableService('Lurnexa_WFHRequests')
PFSettingsTable = TableService('Lurnexa_PFSettings')
PFTransactionsTable = TableService('Lurnexa_PFTransactions')
PayrollApprovalsTable = TableService('Lurnexa_PayrollApprovals')
EmployeeLettersTable = TableService('Lurnexa_EmployeeLetters')
AssetsTable = TableService('Lurnexa_Assets')
OKRsTable = TableService('Lurnexa_OKRs')
AssetRequestsTable = TableService('Lurnexa_AssetRequests')
AppraisalCyclesTable = TableService('Lurnexa_AppraisalCycles')
AppraisalsTable = TableService('Lurnexa_Appraisals')
DeviceTokensTable = TableService('Lurnexa_DeviceTokens')
OrganizationsTable = TableService('Lurnexa_Organizations')
SubscriptionsTable = TableService('Lurnexa_Subscriptions')
RolesTable = TableService('Lurnexa_Roles')
DepartmentsTable = TableService('Lurnexa_Departments')
PolicyAcknowledgementsTable = TableService('Lurnexa_PolicyAcknowledgements')
Feedback360Table = TableService('Lurnexa_Feedback360')
FeedbackCyclesTable = TableService('Lurnexa_FeedbackCycles')
FeedbackTemplatesTable = TableService('Lurnexa_FeedbackTemplates')
FeedbackCompetenciesTable = TableService('Lurnexa_FeedbackCompetencies')
FeedbackQuestionsTable = TableService('Lurnexa_FeedbackQuestions')
FeedbackReviewAssignmentsTable = TableService('Lurnexa_FeedbackReviewAssignments')
FeedbackReviewResponsesTable = TableService('Lurnexa_FeedbackReviewResponses')
FeedbackDevelopmentPlansTable = TableService('Lurnexa_FeedbackDevelopmentPlans')
FeedbackAuditLogsTable = TableService('Lurnexa_FeedbackAuditLogs')

def initialize_dynamodb_tables():
    """
    Helper function to create all required DynamoDB tables.
    """
    tables_to_create = [
        {
            'TableName': 'Lurnexa_Roles',
            'KeySchema': [{'AttributeName': 'OrgID', 'KeyType': 'HASH'}, {'AttributeName': 'RoleID', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'OrgID', 'AttributeType': 'S'},
                {'AttributeName': 'RoleID', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_Departments',
            'KeySchema': [{'AttributeName': 'OrgID', 'KeyType': 'HASH'}, {'AttributeName': 'DepartmentID', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'OrgID', 'AttributeType': 'S'},
                {'AttributeName': 'DepartmentID', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_Organizations',
            'KeySchema': [{'AttributeName': 'OrgID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'OrgID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_Subscriptions',
            'KeySchema': [{'AttributeName': 'OrgID', 'KeyType': 'HASH'}, {'AttributeName': 'PeriodStart', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'OrgID', 'AttributeType': 'S'},
                {'AttributeName': 'PeriodStart', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_Users',
            'KeySchema': [{'AttributeName': 'UserID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [
                {'AttributeName': 'UserID', 'AttributeType': 'S'},
                {'AttributeName': 'Email', 'AttributeType': 'S'},
                {'AttributeName': 'Role', 'AttributeType': 'S'}
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'EmailIndex',
                    'KeySchema': [{'AttributeName': 'Email', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'}
                },
                {
                    'IndexName': 'RoleIndex',
                    'KeySchema': [{'AttributeName': 'Role', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'}
                }
            ],
        },
        {
            'TableName': 'Lurnexa_Employees',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'EmployeeID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_ReportingHierarchy',
            'KeySchema': [{'AttributeName': 'ManagerID', 'KeyType': 'HASH'}, {'AttributeName': 'EmployeeID', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'ManagerID', 'AttributeType': 'S'},
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_LeaveRequests',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'LeaveDate', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'LeaveDate', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_AttendanceRecords',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'RecordDate', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'RecordDate', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_Payslips',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'MonthYear', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'MonthYear', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_Expenses',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'RequestID', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'RequestID', 'AttributeType': 'S'}
            ],
        },

        {
            'TableName': 'Lurnexa_Resignations',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'EmployeeID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_Holidays',
            'KeySchema': [{'AttributeName': 'HolidayID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'HolidayID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_Policies',
            'KeySchema': [{'AttributeName': 'PolicyID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'PolicyID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_OnboardingTokens',
            'KeySchema': [{'AttributeName': 'Token', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'Token', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_LoginHistory',
            'KeySchema': [{'AttributeName': 'UserID', 'KeyType': 'HASH'}, {'AttributeName': 'LoginTime', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'UserID', 'AttributeType': 'S'},
                {'AttributeName': 'LoginTime', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_PasswordResetTokens',
            'KeySchema': [{'AttributeName': 'Token', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [
                {'AttributeName': 'Token', 'AttributeType': 'S'},
                {'AttributeName': 'Email', 'AttributeType': 'S'}
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'EmailIndex',
                    'KeySchema': [{'AttributeName': 'Email', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'}
                }
            ],
        },
        {
            'TableName': 'Lurnexa_Notifications',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'Timestamp', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'Timestamp', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_Settings',
            'KeySchema': [{'AttributeName': 'SettingKey', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'SettingKey', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_WFHRequests',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'RequestID', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'RequestID', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_PFSettings',
            'KeySchema': [{'AttributeName': 'SettingKey', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'SettingKey', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_PFTransactions',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'MonthYear', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'MonthYear', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_PayrollApprovals',
            'KeySchema': [{'AttributeName': 'RequestID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'RequestID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_EmployeeLetters',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'LetterID', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'LetterID', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_Assets',
            'KeySchema': [{'AttributeName': 'AssetID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'AssetID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_OKRs',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'GoalID', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'GoalID', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_AssetRequests',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'RequestID', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'RequestID', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_AppraisalCycles',
            'KeySchema': [{'AttributeName': 'CycleID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [
                {'AttributeName': 'CycleID', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_Appraisals',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'CycleID', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'CycleID', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_DeviceTokens',
            'KeySchema': [{'AttributeName': 'EmployeeID', 'KeyType': 'HASH'}, {'AttributeName': 'DeviceToken', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'},
                {'AttributeName': 'DeviceToken', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_PolicyAcknowledgements',
            'KeySchema': [{'AttributeName': 'PolicyID', 'KeyType': 'HASH'}, {'AttributeName': 'EmployeeID', 'KeyType': 'RANGE'}],
            'AttributeDefinitions': [
                {'AttributeName': 'PolicyID', 'AttributeType': 'S'},
                {'AttributeName': 'EmployeeID', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_Feedback360',
            'KeySchema': [{'AttributeName': 'FeedbackID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [
                {'AttributeName': 'FeedbackID', 'AttributeType': 'S'}
            ],
        },
        {
            'TableName': 'Lurnexa_FeedbackCycles',
            'KeySchema': [{'AttributeName': 'CycleID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'CycleID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_FeedbackTemplates',
            'KeySchema': [{'AttributeName': 'TemplateID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'TemplateID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_FeedbackCompetencies',
            'KeySchema': [{'AttributeName': 'CompetencyID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'CompetencyID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_FeedbackQuestions',
            'KeySchema': [{'AttributeName': 'QuestionID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'QuestionID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_FeedbackReviewAssignments',
            'KeySchema': [{'AttributeName': 'AssignmentID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'AssignmentID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_FeedbackReviewResponses',
            'KeySchema': [{'AttributeName': 'ResponseID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'ResponseID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_FeedbackDevelopmentPlans',
            'KeySchema': [{'AttributeName': 'PlanID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'PlanID', 'AttributeType': 'S'}],
        },
        {
            'TableName': 'Lurnexa_FeedbackAuditLogs',
            'KeySchema': [{'AttributeName': 'LogID', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'LogID', 'AttributeType': 'S'}],
        }
    ]

    dynamodb = get_dynamodb_resource()
    for table_def in tables_to_create:
        try:
            if getattr(settings, 'DYNAMODB_ENDPOINT_URL', None):
                table_def['BillingMode'] = 'PROVISIONED'
                table_def['ProvisionedThroughput'] = {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                if 'GlobalSecondaryIndexes' in table_def:
                    for gsi in table_def['GlobalSecondaryIndexes']:
                        gsi['ProvisionedThroughput'] = {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
            else:
                table_def['BillingMode'] = 'PAY_PER_REQUEST'

            client = dynamodb.meta.client
            client.create_table(**table_def)
            print(f"Table {table_def['TableName']} creation requested...")
            # Skip waiter for local dev as it's often instantaneous but can hang
            if not getattr(settings, 'DYNAMODB_ENDPOINT_URL', None):
                client.get_waiter('table_exists').wait(TableName=table_def['TableName'])
            print(f"Table {table_def['TableName']} initialized!")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceInUseException':
                print(f"Table {table_def['TableName']} already exists.")
            else:
                raise e
