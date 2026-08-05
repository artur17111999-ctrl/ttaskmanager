from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from db import get_company_employees


ROLE_TITLES = {
    "employee": "Сотрудник",
    "company_admin": "Администратор компании",
    "system_admin": "Системный администратор",
}


class EmployeesWidget(QWidget):
    def __init__(self, current_user_id, company_id=None, company_name=None, parent=None):
        super().__init__(parent)
        self.current_user_id = current_user_id
        self.company_id = company_id
        self.company_name = company_name or ""
        self.setObjectName("employeesPage")

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self.reload)

        self._build_ui()
        self.reload()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QFrame(self)
        toolbar.setObjectName("employeesToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(20, 14, 20, 14)
        toolbar_layout.setSpacing(10)

        self.company_label = QLabel(self.company_name or "Компания не назначена", toolbar)
        self.company_label.setObjectName("employeesCompanyLabel")
        toolbar_layout.addWidget(self.company_label)
        toolbar_layout.addStretch()

        self.search_input = QLineEdit(toolbar)
        self.search_input.setObjectName("employeesSearch")
        self.search_input.setPlaceholderText("Поиск по ФИО или email")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMaximumWidth(360)
        self.search_input.textChanged.connect(lambda: self.search_timer.start())
        toolbar_layout.addWidget(self.search_input)

        refresh_button = QToolButton(toolbar)
        refresh_button.setObjectName("employeesRefreshButton")
        refresh_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        refresh_button.setToolTip("Обновить список")
        refresh_button.clicked.connect(self.reload)
        toolbar_layout.addWidget(refresh_button)
        root.addWidget(toolbar)

        content = QWidget(self)
        content.setObjectName("employeesContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 18, 20, 20)
        content_layout.setSpacing(12)

        self.state_label = QLabel(content)
        self.state_label.setObjectName("employeesStateLabel")
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setWordWrap(True)
        self.state_label.hide()
        content_layout.addWidget(self.state_label)

        self.table = QTableWidget(0, 6, content)
        self.table.setObjectName("employeesTable")
        self.table.setHorizontalHeaderLabels(
            ["Сотрудник", "Должность", "Подразделение", "Email", "Роль", "Статус"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        content_layout.addWidget(self.table, 1)
        root.addWidget(content, 1)

    def reload(self):
        if self.company_id is None:
            self.table.setRowCount(0)
            self.table.hide()
            self.state_label.setText("Компания не назначена. Обратитесь к администратору.")
            self.state_label.show()
            return

        rows = get_company_employees(
            self.current_user_id,
            self.search_input.text().strip() or None,
        )
        self.table.setRowCount(len(rows))

        for row_index, employee in enumerate(rows):
            values = (
                employee["full_name"],
                employee.get("position") or "—",
                employee.get("department") or "—",
                employee.get("email") or "—",
                ROLE_TITLES.get(employee.get("role"), employee.get("role") or "Сотрудник"),
                "Уволен" if employee.get("is_dismissed") else "Активен",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, employee["id"])
                if column == 5:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_index, column, item)

        has_rows = bool(rows)
        self.table.setVisible(has_rows)
        self.state_label.setVisible(not has_rows)
        if not has_rows:
            self.state_label.setText("Сотрудники не найдены")
