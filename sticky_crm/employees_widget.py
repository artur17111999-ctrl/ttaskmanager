from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from access_context import coerce_access_context
from company_service import (
    CompanyServiceError,
    assign_company_role,
    create_invitation,
    dismiss_employee,
    list_company_employees,
    restore_employee,
)
from db import get_company_employees, get_departments, get_positions


ROLE_TITLES = {
    "employee": "Сотрудник",
    "company_admin": "Администратор компании",
    "company_owner": "Владелец компании",
    "system_admin": "Системный администратор",
}


MANAGER_ROLES = {"company_owner", "company_admin"}


class EmployeeInvitationDialog(QDialog):
    def __init__(self, parent=None, allow_admin_role=True):
        super().__init__(parent)
        self.allow_admin_role = allow_admin_role
        self.setObjectName("employeeInvitationDialog")
        self.setWindowTitle("Добавить сотрудника")
        self.setMinimumWidth(520)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(16)

        title = QLabel("Приглашение сотрудника", self)
        title.setObjectName("employeeDialogTitle")
        root.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(11)
        self.last_name = QLineEdit(self)
        self.first_name = QLineEdit(self)
        self.middle_name = QLineEdit(self)
        self.email = QLineEdit(self)
        self.email.setPlaceholderText("employee@example.ru")
        self.start_date = QDateEdit(self)
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate())
        self.position = QComboBox(self)
        self.department = QComboBox(self)
        self.role = QComboBox(self)
        self.role.addItem("Сотрудник", "employee")
        if self.allow_admin_role:
            self.role.addItem("Администратор компании", "company_admin")
        for position_id, title_text in get_positions():
            self.position.addItem(str(title_text), position_id)
        for department_id, title_text in get_departments():
            self.department.addItem(str(title_text), department_id)
        form.addRow("Фамилия *", self.last_name)
        form.addRow("Имя *", self.first_name)
        form.addRow("Отчество", self.middle_name)
        form.addRow("Email *", self.email)
        form.addRow("Дата начала работы", self.start_date)
        form.addRow("Должность", self.position)
        form.addRow("Подразделение", self.department)
        form.addRow("Роль", self.role)
        root.addLayout(form)

        note = QLabel(
            "Пароль не задаётся администратором. Сотрудник получит одноразовое "
            "приглашение и создаст пароль сам.",
            self,
        )
        note.setObjectName("employeeDialogNote")
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        buttons.button(QDialogButtonBox.Save).setText("Создать приглашение")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _validate(self):
        if not self.last_name.text().strip() or not self.first_name.text().strip():
            QMessageBox.warning(self, "Проверьте данные", "Укажите фамилию и имя.")
            return
        if "@" not in self.email.text() or "." not in self.email.text().split("@")[-1]:
            QMessageBox.warning(self, "Проверьте данные", "Укажите корректный email.")
            return
        self.accept()

    def data(self):
        return {
            "last_name": self.last_name.text().strip(),
            "first_name": self.first_name.text().strip(),
            "middle_name": self.middle_name.text().strip() or None,
            "email": self.email.text().strip().casefold(),
            "start_date": self.start_date.date().toString("yyyy-MM-dd"),
            "position_id": self.position.currentData(),
            "department_id": self.department.currentData(),
            "requested_role": self.role.currentData(),
        }


class EmployeesWidget(QWidget):
    def __init__(
        self,
        current_user_id,
        company_id=None,
        company_name=None,
        actor_context=None,
        parent=None,
    ):
        super().__init__(parent)
        actor_data = actor_context or {
            "account_id": 0,
            "employee_id": current_user_id,
            "full_name": "",
            "company_id": company_id,
            "company_name": company_name,
            "role": "employee",
        }
        self.actor = coerce_access_context(actor_data)
        self.current_user_id = self.actor.employee_id
        self.company_id = self.actor.company_id
        self.company_name = self.actor.company_name or company_name or ""
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

        self.invite_button = QPushButton("Добавить сотрудника", toolbar)
        self.invite_button.setObjectName("employeesInviteButton")
        self.invite_button.clicked.connect(self._invite_employee)
        toolbar_layout.addWidget(self.invite_button)

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

        self.table = QTableWidget(0, 7, content)
        self.table.setObjectName("employeesTable")
        self.table.setHorizontalHeaderLabels(
            ["Сотрудник", "Должность", "Подразделение", "Email", "Роль", "Статус", ""]
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
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.table.setColumnWidth(6, 48)
        content_layout.addWidget(self.table, 1)
        root.addWidget(content, 1)

    def reload(self):
        can_manage = self.actor.role in MANAGER_ROLES
        self.invite_button.setVisible(can_manage and self.company_id is not None)
        if self.company_id is None:
            self.table.setRowCount(0)
            self.table.hide()
            self.state_label.setText("Компания не назначена. Сначала создайте компанию или примите приглашение.")
            self.state_label.show()
            return

        search = self.search_input.text().strip() or None
        try:
            if can_manage:
                rows = list_company_employees(
                    self.actor,
                    {"search": search} if search else None,
                )
            else:
                rows = get_company_employees(self.current_user_id, search)
        except CompanyServiceError as error:
            self.table.setRowCount(0)
            self.table.hide()
            self.state_label.setText(str(error))
            self.state_label.show()
            return
        except Exception as error:
            self.table.setRowCount(0)
            self.table.hide()
            self.state_label.setText(f"Не удалось загрузить сотрудников: {error}")
            self.state_label.show()
            return
        self.table.setRowCount(len(rows))

        for row_index, employee in enumerate(rows):
            employee_id = employee.get("id") or employee.get("employee_id")
            status_key = str(employee.get("status") or "").casefold()
            if employee.get("is_dismissed") or status_key in {"dismissed", "blocked"}:
                status_title = "Уволен"
            elif status_key in {"pending", "invited"} or employee.get("invitation_id"):
                status_title = "Приглашён"
            else:
                status_title = "Активен"
            values = (
                employee.get("full_name") or employee.get("email") or "—",
                employee.get("position") or "—",
                employee.get("department") or "—",
                employee.get("email") or "—",
                ROLE_TITLES.get(
                    employee.get("role") or employee.get("requested_role"),
                    employee.get("role") or employee.get("requested_role") or "Сотрудник",
                ),
                status_title,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, employee_id)
                if column == 5:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_index, column, item)
            if can_manage and employee_id is not None:
                self.table.setCellWidget(
                    row_index,
                    6,
                    self._create_actions_button(employee),
                )

        has_rows = bool(rows)
        self.table.setVisible(has_rows)
        self.state_label.setVisible(not has_rows)
        if not has_rows:
            self.state_label.setText("Сотрудники не найдены")

    def update_actor_context(self, actor_context):
        self.actor = coerce_access_context(actor_context)
        self.current_user_id = self.actor.employee_id
        self.company_id = self.actor.company_id
        self.company_name = self.actor.company_name or ""
        self.company_label.setText(self.company_name or "Компания не назначена")
        self.reload()

    def _invite_employee(self):
        dialog = EmployeeInvitationDialog(
            allow_admin_role=self.actor.role == "company_owner",
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        self.invite_button.setEnabled(False)
        try:
            invitation = create_invitation(self.actor, dialog.data())
        except CompanyServiceError as error:
            QMessageBox.warning(self, "Приглашение не создано", str(error))
            return
        except Exception as error:
            QMessageBox.critical(self, "Приглашение не создано", str(error))
            return
        finally:
            self.invite_button.setEnabled(True)

        token = dict(invitation or {}).get("delivery_token")
        message = "Приглашение создано и место в лимите зарезервировано."
        if token:
            message += f"\n\nОдноразовый код:\n{token}\n\nПосле закрытия он больше не отображается."
        QMessageBox.information(self, "Приглашение", message)
        self.reload()

    def _create_actions_button(self, employee):
        button = QToolButton(self.table)
        button.setObjectName("employeesActionsButton")
        button.setText("⋯")
        button.setToolTip("Действия с сотрудником")
        button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(button)

        employee_id = employee.get("id") or employee.get("employee_id")
        role = employee.get("role") or "employee"
        is_dismissed = employee.get("is_dismissed") or str(
            employee.get("status") or ""
        ).casefold() in {"dismissed", "blocked"}
        is_owner = role == "company_owner"
        is_self = int(employee_id) == int(self.actor.employee_id)

        if not is_owner and self.actor.role == "company_owner":
            target_role = "employee" if role == "company_admin" else "company_admin"
            role_action = menu.addAction(
                "Снять роль администратора"
                if role == "company_admin"
                else "Сделать администратором"
            )
            role_action.triggered.connect(
                lambda checked=False, eid=employee_id, value=target_role: self._set_role(eid, value)
            )

        if not is_owner and not is_self:
            if is_dismissed and self.actor.role == "company_owner":
                state_action = menu.addAction("Восстановить")
                state_action.triggered.connect(
                    lambda checked=False, eid=employee_id: self._restore_employee(eid)
                )
            elif not is_dismissed:
                state_action = menu.addAction("Уволить")
                state_action.triggered.connect(
                    lambda checked=False, eid=employee_id: self._dismiss_employee(eid)
                )

        if not menu.actions():
            no_actions = menu.addAction("Нет доступных действий")
            no_actions.setEnabled(False)
        button.setMenu(menu)
        return button

    def _set_role(self, employee_id, role):
        try:
            assign_company_role(self.actor, employee_id, role)
        except CompanyServiceError as error:
            QMessageBox.warning(self, "Роль не изменена", str(error))
            return
        self.reload()

    def _dismiss_employee(self, employee_id):
        answer = QMessageBox.question(
            self,
            "Увольнение сотрудника",
            "Сотрудник потеряет доступ. Перед увольнением убедитесь, что его активные задачи переданы.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            dismiss_employee(self.actor, employee_id)
        except CompanyServiceError as error:
            QMessageBox.warning(self, "Сотрудник не уволен", str(error))
            return
        self.reload()

    def _restore_employee(self, employee_id):
        try:
            restore_employee(self.actor, employee_id)
        except CompanyServiceError as error:
            QMessageBox.warning(self, "Сотрудник не восстановлен", str(error))
            return
        self.reload()
