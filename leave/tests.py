import datetime
from django.test import TestCase
from unittest.mock import patch, MagicMock
from core.utils import get_initial_leave_balance, refresh_monthly_leaves

class MockDate(datetime.date):
    _today_val = None
    @classmethod
    def today(cls):
        return cls._today_val

class LeavePolicyTests(TestCase):
    def test_get_initial_leave_balance_intern(self):
        employee = {
            'EmploymentType': 'Intern',
            'JoinedDate': '2026-05-15'
        }
        self.assertEqual(get_initial_leave_balance(employee, 'SL'), 0.0)
        self.assertEqual(get_initial_leave_balance(employee, 'CL'), 0.0)

    def test_get_initial_leave_balance_prior_year(self):
        employee = {
            'EmploymentType': 'Permanent',
            'JoinedDate': '2025-05-15'
        }
        MockDate._today_val = datetime.date(2026, 6, 1)
        with patch('core.utils.datetime.date', MockDate):
            self.assertEqual(get_initial_leave_balance(employee, 'SL'), 12.0)
            self.assertEqual(get_initial_leave_balance(employee, 'CL'), 12.0)

    def test_get_initial_leave_balance_current_year_may(self):
        employee = {
            'EmploymentType': 'Permanent',
            'JoinedDate': '2026-05-15'
        }
        MockDate._today_val = datetime.date(2026, 6, 1)
        with patch('core.utils.datetime.date', MockDate):
            # May is month 5: 12 - 5 + 1 = 8.0
            self.assertEqual(get_initial_leave_balance(employee, 'SL'), 8.0)
            self.assertEqual(get_initial_leave_balance(employee, 'CL'), 8.0)

    def test_get_initial_leave_balance_current_year_december(self):
        employee = {
            'EmploymentType': 'Permanent',
            'JoinedDate': '2026-12-01'
        }
        MockDate._today_val = datetime.date(2026, 12, 10)
        with patch('core.utils.datetime.date', MockDate):
            # December is month 12: 12 - 12 + 1 = 1.0
            self.assertEqual(get_initial_leave_balance(employee, 'SL'), 1.0)
            self.assertEqual(get_initial_leave_balance(employee, 'CL'), 1.0)

    @patch('core.utils.EmployeesTable')
    @patch('payroll.views.get_attendance_summary')
    def test_refresh_monthly_leaves_normal_month(self, mock_summary, mock_table):
        mock_summary.return_value = {'paid_days': 20.0}
        employee = {
            'EmployeeID': 'EMP001',
            'EmploymentType': 'Permanent',
            'LastLeaveRefresh': '2026-04',
            'Balance_PL': '5.0'
        }
        MockDate._today_val = datetime.date(2026, 5, 1)
        with patch('core.utils.datetime.date', MockDate):
            refresh_monthly_leaves(employee)
            # Should not reset SL/CL to 12.0, only update LastLeaveRefresh and Balance_PL
            # 20.0 / 20.0 = 1.0. New EL balance = 5.0 + 1.0 = 6.0
            mock_table.update_item.assert_called_once_with(
                Key={'EmployeeID': 'EMP001'},
                UpdateExpression="SET Balance_PL = :pl, LastLeaveRefresh = :lr",
                ExpressionAttributeValues={
                    ':pl': '6.0',
                    ':lr': '2026-05'
                }
            )

    @patch('core.utils.EmployeesTable')
    @patch('payroll.views.get_attendance_summary')
    def test_refresh_monthly_leaves_jan_first(self, mock_summary, mock_table):
        mock_summary.return_value = {'paid_days': 20.0}
        employee = {
            'EmployeeID': 'EMP001',
            'EmploymentType': 'Permanent',
            'LastLeaveRefresh': '2025-12',
            'Balance_PL': '5.0'
        }
        MockDate._today_val = datetime.date(2026, 1, 1)
        with patch('core.utils.datetime.date', MockDate):
            refresh_monthly_leaves(employee)
            # Should reset balances to 12.0 and update Balance_PL
            # 20.0 / 20.0 = 1.0. New EL balance = 5.0 + 1.0 = 6.0
            mock_table.update_item.assert_called_once_with(
                Key={'EmployeeID': 'EMP001'},
                UpdateExpression="SET Balance_SL = :sl, Balance_CL = :cl, Balance_PL = :pl, LastLeaveRefresh = :lr",
                ExpressionAttributeValues={
                    ':sl': '12.0',
                    ':cl': '12.0',
                    ':pl': '6.0',
                    ':lr': '2026-01'
                }
            )
