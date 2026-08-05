import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "sticky_crm"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import db
import employees_widget
from company_widget import can_open_company_page
from employees_widget import EmployeesWidget


class _EmployeeCursorStub:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.query = None
        self.params = None
        self.closed = False

    def execute(self, query, params=None):
        self.query = str(query)
        self.params = params

    def fetchall(self):
        return list(self.rows)

    def close(self):
        self.closed = True


class _EmployeeConnectionStub:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


class CompanyEmployeesQueryTests(unittest.TestCase):
    def _call(self, actor_user_id, search_query=None, rows=()):
        cursor = _EmployeeCursorStub(rows)
        connection = _EmployeeConnectionStub(cursor)
        with patch.object(db, "get_connection", return_value=connection):
            result = db.get_company_employees(actor_user_id, search_query)
        return result, cursor, connection

    def test_tenant_filter_is_derived_from_actor_user_id(self):
        rows = [
            (7, "Иванов Иван", "Разработчик", "ИТ", "i@example.test", "employee", False)
        ]

        result, cursor, connection = self._call(42, rows=rows)

        compact_sql = " ".join(cursor.query.split()).casefold()
        self.assertIn("e.company_id = (", compact_sql)
        self.assertIn("select actor.company_id", compact_sql)
        self.assertIn("where actor.id = %s", compact_sql)
        self.assertEqual(cursor.params, (42,))
        self.assertNotIn("company_id = %s", compact_sql)
        self.assertEqual(result[0]["id"], 7)
        self.assertTrue(cursor.closed)
        self.assertTrue(connection.closed)

    def test_search_text_is_bound_as_parameters(self):
        unsafe_search = "%' OR 1=1 --"

        _, cursor, _ = self._call(42, unsafe_search)

        self.assertNotIn(unsafe_search, cursor.query)
        self.assertEqual(cursor.query.count("ILIKE %s"), 4)
        self.assertEqual(cursor.params[0], 42)
        self.assertEqual(cursor.params[1:], tuple([f"%{unsafe_search}%"] * 4))

    def test_connection_failure_returns_empty_list(self):
        with patch.object(db, "get_connection", return_value=None):
            self.assertEqual(db.get_company_employees(42, "Иван"), [])


class EmployeesWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.app.processEvents()

    def test_missing_company_does_not_query_database(self):
        with patch.object(employees_widget, "get_company_employees") as get_employees:
            widget = EmployeesWidget(
                current_user_id=42,
                company_id=None,
                company_name=None,
            )

        try:
            get_employees.assert_not_called()
            self.assertEqual(widget.table.rowCount(), 0)
            self.assertTrue(widget.table.isHidden())
            self.assertFalse(widget.state_label.isHidden())
            self.assertIn("Компания не назначена", widget.state_label.text())
        finally:
            widget.close()
            widget.deleteLater()

    def test_assigned_company_populates_table(self):
        employees = [
            {
                "id": 7,
                "full_name": "Иванов Иван",
                "position": "Разработчик",
                "department": "ИТ",
                "email": "ivanov@example.test",
                "role": "company_admin",
                "is_dismissed": False,
            },
            {
                "id": 8,
                "full_name": "Петров Пётр",
                "position": None,
                "department": None,
                "email": None,
                "role": "employee",
                "is_dismissed": True,
            },
        ]
        with patch.object(
            employees_widget, "get_company_employees", return_value=employees
        ) as get_employees:
            widget = EmployeesWidget(
                current_user_id=42,
                company_id=5,
                company_name="Компания A",
            )

        try:
            get_employees.assert_called_once_with(42, None)
            self.assertEqual(widget.company_label.text(), "Компания A")
            self.assertEqual(widget.table.rowCount(), 2)
            self.assertEqual(widget.table.item(0, 0).text(), "Иванов Иван")
            self.assertEqual(widget.table.item(0, 4).text(), "Администратор компании")
            self.assertEqual(widget.table.item(0, 5).text(), "Активен")
            self.assertEqual(widget.table.item(1, 1).text(), "—")
            self.assertEqual(widget.table.item(1, 5).text(), "Уволен")
            self.assertEqual(widget.table.item(0, 0).data(0x0100), 7)
            self.assertFalse(widget.table.isHidden())
            self.assertTrue(widget.state_label.isHidden())
        finally:
            widget.close()
            widget.deleteLater()

    def test_reload_passes_trimmed_search_with_actor_only(self):
        with patch.object(
            employees_widget, "get_company_employees", return_value=[]
        ) as get_employees:
            widget = EmployeesWidget(42, company_id=5, company_name="Компания A")
            get_employees.reset_mock()
            widget.search_input.setText("  Иванов  ")
            widget.reload()

        try:
            get_employees.assert_called_once_with(42, "Иванов")
        finally:
            widget.search_timer.stop()
            widget.close()
            widget.deleteLater()

    def test_owner_manager_controls_use_actor_aware_service(self):
        employee = {
            "id": 8,
            "full_name": "Test Employee",
            "email": "employee@example.test",
            "role": "employee",
            "is_dismissed": False,
        }
        actor = {
            "account_id": 1,
            "employee_id": 42,
            "full_name": "Company Owner",
            "company_id": 5,
            "company_name": "Acme",
            "role": "company_owner",
        }
        with patch.object(
            employees_widget, "list_company_employees", return_value=[employee]
        ) as list_employees:
            widget = EmployeesWidget(42, actor_context=actor)

        try:
            list_employees.assert_called_once_with(widget.actor, None)
            self.assertFalse(widget.invite_button.isHidden())
            actions_button = widget.table.cellWidget(0, 6)
            self.assertIsNotNone(actions_button)
            self.assertGreaterEqual(len(actions_button.menu().actions()), 2)
        finally:
            widget.close()
            widget.deleteLater()

    def test_delegated_admin_can_invite_and_manage_employee_state(self):
        employee = {
            "id": 8,
            "full_name": "Test Employee",
            "email": "employee@example.test",
            "role": "employee",
            "is_dismissed": False,
        }
        actor = {
            "account_id": 1,
            "employee_id": 42,
            "full_name": "Delegated Admin",
            "company_id": 5,
            "company_name": "Acme",
            "role": "company_admin",
        }
        with patch.object(
            employees_widget, "list_company_employees", return_value=[employee]
        ):
            widget = EmployeesWidget(42, actor_context=actor)

        try:
            self.assertFalse(widget.invite_button.isHidden())
            actions_button = widget.table.cellWidget(0, 6)
            self.assertIsNotNone(actions_button)
            self.assertEqual(len(actions_button.menu().actions()), 1)
        finally:
            widget.close()
            widget.deleteLater()


class CompanyPageVisibilityTests(unittest.TestCase):
    @staticmethod
    def _actor(*, company_id, role):
        return {
            "account_id": 1,
            "employee_id": 42,
            "full_name": "Test User",
            "company_id": company_id,
            "company_name": "Acme" if company_id is not None else None,
            "role": role,
        }

    def test_no_company_employee_sees_onboarding(self):
        self.assertTrue(
            can_open_company_page(self._actor(company_id=None, role="employee"))
        )

    def test_owner_sees_company_page(self):
        self.assertTrue(
            can_open_company_page(
                self._actor(company_id=5, role="company_owner")
            )
        )

    def test_delegated_admin_does_not_see_company_page(self):
        self.assertFalse(
            can_open_company_page(
                self._actor(company_id=5, role="company_admin")
            )
        )

    def test_assigned_employee_does_not_see_company_page(self):
        self.assertFalse(
            can_open_company_page(self._actor(company_id=5, role="employee"))
        )


class EmployeesPageWiringContractTests(unittest.TestCase):
    def test_menu_index_matches_stacked_page_order(self):
        source = (APP_ROOT / "main_window.py").read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r"menu_data\.insert\(3,\s*\([^,\n]+,\s*5,",
        )
        self.assertRegex(
            source,
            r"if can_open_company_page\(self\.access_context\):\s*"
            r"menu_data\.insert\(3,\s*\([^,\n]+,\s*4,",
        )
        stickies_position = source.index("self.content_area.addWidget(self.stickies_page)")
        company_position = source.index("self.content_area.addWidget(self.company_page)")
        employees_position = source.index("self.content_area.addWidget(self.employees_page)")
        self.assertLess(stickies_position, company_position)
        self.assertLess(company_position, employees_position)

    def test_employees_qss_covers_page_controls(self):
        qss = (APP_ROOT / "styles" / "default" / "employees.qss").read_text(
            encoding="utf-8"
        )
        for selector in (
            "QWidget#employeesPage",
            "QFrame#employeesToolbar",
            "QLineEdit#employeesSearch",
            "QPushButton#employeesInviteButton",
            "QToolButton#employeesRefreshButton",
            "QToolButton#employeesActionsButton",
            "QTableWidget#employeesTable",
            "QLabel#employeesStateLabel",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, qss)


if __name__ == "__main__":
    unittest.main()
