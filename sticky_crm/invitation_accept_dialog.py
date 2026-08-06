import uuid

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from invitation_service import (
    EmailConflictError,
    IdempotencyConflictError,
    InvitationServiceError,
    InvalidInvitationError,
    LoginConflictError,
    accept_invitation,
    inspect_invitation,
)
from company_service import ConflictError, ValidationError


ROLE_TITLES = {
    "employee": "Сотрудник",
    "company_admin": "Администратор компании",
}

INVALID_INVITATION_MESSAGE = "Приглашение недействительно или срок его действия истёк."


class InvitationAcceptDialog(QDialog):
    """Creates an employee account from a one-time invitation token."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("invitationAcceptDialog")
        self.setWindowTitle("Принять приглашение")
        self.setMinimumSize(560, 590)
        self.setModal(True)

        self.created_login = None
        self._token = None
        self._preview = None
        self._idempotency_key = None
        self._submitting = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Принять приглашение", self)
        title.setObjectName("invitationTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Введите одноразовый код, полученный от администратора компании.",
            self,
        )
        subtitle.setObjectName("invitationSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.token_frame = QFrame(self)
        self.token_frame.setObjectName("invitationTokenFrame")
        token_layout = QVBoxLayout(self.token_frame)
        token_layout.setContentsMargins(16, 16, 16, 16)
        token_layout.setSpacing(10)

        token_label = QLabel("Одноразовый код", self.token_frame)
        token_label.setObjectName("invitationFieldLabel")
        token_layout.addWidget(token_label)

        token_row = QHBoxLayout()
        token_row.setSpacing(10)
        self.token_input = QLineEdit(self.token_frame)
        self.token_input.setObjectName("invitationTokenInput")
        self.token_input.setPlaceholderText("Вставьте код приглашения")
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setMaxLength(512)
        self.token_input.returnPressed.connect(self._inspect)
        token_row.addWidget(self.token_input, 1)

        self.inspect_button = QPushButton("Проверить", self.token_frame)
        self.inspect_button.setObjectName("invitationInspectButton")
        self.inspect_button.clicked.connect(self._inspect)
        token_row.addWidget(self.inspect_button)
        token_layout.addLayout(token_row)
        root.addWidget(self.token_frame)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("invitationError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)

        self.preview_frame = QFrame(self)
        self.preview_frame.setObjectName("invitationPreviewFrame")
        preview_layout = QVBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(16, 14, 16, 14)
        preview_layout.setSpacing(9)

        preview_title = QLabel("Данные приглашения", self.preview_frame)
        preview_title.setObjectName("invitationSectionTitle")
        preview_layout.addWidget(preview_title)

        preview_form = QFormLayout()
        preview_form.setHorizontalSpacing(18)
        preview_form.setVerticalSpacing(7)
        self.company_value = self._preview_value()
        self.email_value = self._preview_value()
        self.name_value = self._preview_value()
        self.position_value = self._preview_value()
        self.department_value = self._preview_value()
        self.start_date_value = self._preview_value()
        self.role_value = self._preview_value()
        self.expires_value = self._preview_value()
        preview_form.addRow("Компания", self.company_value)
        preview_form.addRow("Email", self.email_value)
        preview_form.addRow("ФИО", self.name_value)
        preview_form.addRow("Должность", self.position_value)
        preview_form.addRow("Подразделение", self.department_value)
        preview_form.addRow("Начало работы", self.start_date_value)
        preview_form.addRow("Роль", self.role_value)
        preview_form.addRow("Действительно до", self.expires_value)
        preview_layout.addLayout(preview_form)
        self.preview_frame.hide()
        root.addWidget(self.preview_frame)

        self.account_frame = QFrame(self)
        self.account_frame.setObjectName("invitationAccountFrame")
        account_layout = QVBoxLayout(self.account_frame)
        account_layout.setContentsMargins(16, 14, 16, 16)
        account_layout.setSpacing(11)

        account_title = QLabel("Учётная запись", self.account_frame)
        account_title.setObjectName("invitationSectionTitle")
        account_layout.addWidget(account_title)

        account_form = QFormLayout()
        account_form.setHorizontalSpacing(18)
        account_form.setVerticalSpacing(9)
        self.login_input = QLineEdit(self.account_frame)
        self.login_input.setObjectName("invitationLoginInput")
        self.login_input.setPlaceholderText("От 3 до 100 символов")
        self.login_input.setMaxLength(100)
        self.birth_date_input = QDateEdit(self.account_frame)
        self.birth_date_input.setObjectName("invitationBirthDateInput")
        self.birth_date_input.setCalendarPopup(True)
        self.birth_date_input.setDisplayFormat("dd.MM.yyyy")
        self.birth_date_input.setMaximumDate(QDate.currentDate().addDays(-1))
        self.birth_date_input.setDate(QDate.currentDate().addYears(-18))
        self.password_input = QLineEdit(self.account_frame)
        self.password_input.setObjectName("invitationPasswordInput")
        self.password_input.setPlaceholderText("Не менее 12 символов")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMaxLength(1024)
        self.password_confirmation_input = QLineEdit(self.account_frame)
        self.password_confirmation_input.setObjectName("invitationPasswordConfirmationInput")
        self.password_confirmation_input.setEchoMode(QLineEdit.Password)
        self.password_confirmation_input.setMaxLength(1024)
        self.password_confirmation_input.returnPressed.connect(self._accept_invitation)
        account_form.addRow("Логин", self.login_input)
        account_form.addRow("Дата рождения", self.birth_date_input)
        account_form.addRow("Пароль", self.password_input)
        account_form.addRow("Повторите пароль", self.password_confirmation_input)
        account_layout.addLayout(account_form)

        self.consent_checkbox = QCheckBox(
            "Я принимаю политику обработки персональных данных",
            self.account_frame,
        )
        self.consent_checkbox.setObjectName("invitationConsent")
        account_layout.addWidget(self.consent_checkbox)
        self.account_frame.hide()
        root.addWidget(self.account_frame)

        root.addStretch()
        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_button = QPushButton("Отмена", self)
        self.cancel_button.setObjectName("invitationCancelButton")
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)

        self.accept_button = QPushButton("Принять и создать учётную запись", self)
        self.accept_button.setObjectName("invitationAcceptButton")
        self.accept_button.clicked.connect(self._accept_invitation)
        self.accept_button.hide()
        actions.addWidget(self.accept_button)
        root.addLayout(actions)

    def _preview_value(self):
        label = QLabel("-", self.preview_frame)
        label.setObjectName("invitationPreviewValue")
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setWordWrap(True)
        return label

    def _set_busy(self, busy):
        self._submitting = busy
        self.inspect_button.setEnabled(not busy)
        self.accept_button.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)

    def _show_error(self, message):
        self.error_label.setText(message)
        self.error_label.show()

    def _inspect(self):
        if self._submitting:
            return
        token = self.token_input.text().strip()
        if not token:
            self._show_error("Введите код приглашения.")
            return

        self.error_label.hide()
        self._set_busy(True)
        try:
            preview = inspect_invitation(token)
        except InvalidInvitationError:
            self._show_error(INVALID_INVITATION_MESSAGE)
            return
        except InvitationServiceError as error:
            self._show_error(str(error))
            return
        except Exception:
            self._show_error("Сервис приглашений временно недоступен. Повторите попытку позже.")
            return
        finally:
            self._set_busy(False)

        self._token = token
        self._preview = dict(preview or {})
        self._idempotency_key = uuid.uuid4().hex
        self.token_input.clear()
        self.token_frame.hide()
        self._show_preview(self._preview)
        self.preview_frame.show()
        self.account_frame.show()
        self.accept_button.show()
        self.login_input.setFocus()

    def _show_preview(self, preview):
        profile = dict(preview.get("profile_data") or {})
        name = " ".join(
            str(profile.get(key) or "").strip()
            for key in ("last_name", "first_name", "middle_name")
        ).strip()
        role = preview.get("requested_role") or profile.get("requested_role")
        self.company_value.setText(str(preview.get("company_name") or "-"))
        self.email_value.setText(str(preview.get("email") or "-"))
        self.name_value.setText(name or "-")
        self.position_value.setText(str(profile.get("position") or profile.get("position_name") or "-"))
        self.department_value.setText(
            str(profile.get("department") or profile.get("department_name") or "-")
        )
        self.start_date_value.setText(str(profile.get("start_date") or "-"))
        self.role_value.setText(ROLE_TITLES.get(role, str(role or "-")))
        self.expires_value.setText(str(preview.get("expires_at") or "-"))

    def _accept_invitation(self):
        if self._submitting or not self._token:
            return
        login = self.login_input.text().strip()
        password = self.password_input.text()
        confirmation = self.password_confirmation_input.text()
        if len(login) < 3:
            self._show_error("Логин должен содержать не менее 3 символов.")
            return
        if len(password) < 12:
            self._show_error("Пароль должен содержать не менее 12 символов.")
            return
        if password != confirmation:
            self._show_error("Пароли не совпадают.")
            return
        if not self.consent_checkbox.isChecked():
            self._show_error("Подтвердите согласие с политикой обработки персональных данных.")
            return

        self.error_label.hide()
        self._set_busy(True)
        try:
            result = accept_invitation(
                self._token,
                {
                    "login": login,
                    "password": password,
                    "birth_date": self.birth_date_input.date().toString("yyyy-MM-dd"),
                    "policy_version": "1",
                },
                idempotency_key=self._idempotency_key,
            )
        except InvalidInvitationError:
            self._show_error(INVALID_INVITATION_MESSAGE)
            return
        except LoginConflictError:
            self._show_error("Этот логин уже занят. Выберите другой.")
            return
        except EmailConflictError:
            self._show_error("Для этого email уже существует учётная запись.")
            return
        except IdempotencyConflictError:
            self._show_error("Запрос изменился. Закройте окно и повторите принятие приглашения.")
            return
        except ValidationError as error:
            self._show_error(str(error))
            return
        except ConflictError:
            self._show_error("Учётную запись не удалось создать из-за конфликта данных.")
            return
        except InvitationServiceError as error:
            self._show_error(str(error))
            return
        except Exception:
            self._show_error("Не удалось создать учётную запись. Повторите попытку позже.")
            return
        finally:
            self._set_busy(False)

        self.created_login = str(dict(result or {}).get("login") or login)
        self._clear_sensitive_fields()
        QMessageBox.information(
            self,
            "Учётная запись создана",
            "Учётная запись создана. Теперь можно войти с новым логином и паролем.",
        )
        self.accept()

    def _clear_sensitive_fields(self):
        self._token = None
        self._preview = None
        self._idempotency_key = None
        self.token_input.clear()
        self.login_input.clear()
        self.password_input.clear()
        self.password_confirmation_input.clear()
        self.consent_checkbox.setChecked(False)

    def done(self, result):
        self._clear_sensitive_fields()
        super().done(result)
