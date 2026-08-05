"""Company onboarding and owner-only company management UI."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Mapping
from urllib.parse import urlparse

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from access_context import AccessContext, coerce_access_context
from company_service import (
    CompanyServiceError,
    create_company,
    get_company,
    get_company_usage,
    update_company,
)


OWNER_ROLES = {"company_owner", "system_admin"}


def can_open_company_page(actor: AccessContext | Mapping[str, Any]) -> bool:
    """Return the navigation visibility rule from the approved specification."""
    context = coerce_access_context(actor)
    return context.company_id is None or context.role in OWNER_ROLES


class CompanyFormDialog(QDialog):
    """Collect company details; the service repeats every validation server-side."""

    def __init__(self, company=None, parent=None):
        super().__init__(parent)
        self.company = dict(company or {})
        self.setObjectName("companyDialog")
        self.setWindowTitle(
            "Редактирование компании" if self.company else "Создание компании"
        )
        self.setMinimumSize(620, 620)
        self._build_ui()
        self._populate()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setObjectName("companyDialogScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget(scroll)
        content.setObjectName("companyDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)

        title = QLabel(self.windowTitle(), content)
        title.setObjectName("companyDialogTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setObjectName("companyForm")
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(22)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.name_input = self._line("Например, ООО Альфа")
        self.inn_input = self._line("10 или 12 цифр", 12)
        self.kpp_input = self._line("9 цифр, если применимо", 9)
        self.legal_address_input = self._text("Юридический адрес")
        self.actual_address_input = self._text("Фактический адрес")
        self.email_input = self._line("company@example.ru")
        self.website_input = self._line("https://example.ru")

        form.addRow("Наименование *", self.name_input)
        form.addRow("ИНН *", self.inn_input)
        form.addRow("КПП", self.kpp_input)
        form.addRow("Юридический адрес", self.legal_address_input)
        form.addRow("Фактический адрес", self.actual_address_input)
        form.addRow("Email для связи", self.email_input)
        form.addRow("Сайт", self.website_input)
        layout.addLayout(form)

        note = QLabel(
            "После создания компании вы станете её владельцем. "
            "Базовый лимит составляет 15 активных и приглашённых сотрудников.",
            content,
        )
        note.setObjectName("companyDialogNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=content
        )
        buttons.setObjectName("companyDialogButtons")
        buttons.button(QDialogButtonBox.Save).setText(
            "Сохранить" if self.company else "Создать"
        )
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        scroll.setWidget(content)
        root.addWidget(scroll)

    @staticmethod
    def _line(placeholder, maximum_length=None):
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setClearButtonEnabled(True)
        if maximum_length:
            field.setMaxLength(maximum_length)
        return field

    @staticmethod
    def _text(placeholder):
        field = QTextEdit()
        field.setPlaceholderText(placeholder)
        field.setAcceptRichText(False)
        field.setFixedHeight(74)
        return field

    def _populate(self):
        if not self.company:
            return
        self.name_input.setText(str(self.company.get("name") or ""))
        self.inn_input.setText(str(self.company.get("inn") or ""))
        self.kpp_input.setText(str(self.company.get("kpp") or ""))
        self.legal_address_input.setPlainText(
            str(self.company.get("legal_address") or "")
        )
        self.actual_address_input.setPlainText(
            str(self.company.get("actual_address") or "")
        )
        self.email_input.setText(str(self.company.get("contact_email") or ""))
        self.website_input.setText(str(self.company.get("website_url") or ""))

    def data(self):
        return {
            "name": self.name_input.text().strip(),
            "inn": self.inn_input.text().strip(),
            "kpp": self.kpp_input.text().strip() or None,
            "legal_address": self.legal_address_input.toPlainText().strip() or None,
            "actual_address": self.actual_address_input.toPlainText().strip() or None,
            "contact_email": self.email_input.text().strip().casefold() or None,
            "website_url": self.website_input.text().strip() or None,
        }

    def _validate_and_accept(self):
        data = self.data()
        if not data["name"]:
            QMessageBox.warning(self, "Проверьте данные", "Укажите наименование компании.")
            self.name_input.setFocus()
            return
        if not re.fullmatch(r"\d{10}|\d{12}", data["inn"]):
            QMessageBox.warning(self, "Проверьте данные", "ИНН должен содержать 10 или 12 цифр.")
            self.inn_input.setFocus()
            return
        if data["kpp"] and not re.fullmatch(r"\d{9}", data["kpp"]):
            QMessageBox.warning(self, "Проверьте данные", "КПП должен содержать 9 цифр.")
            self.kpp_input.setFocus()
            return
        email = data["contact_email"]
        if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            QMessageBox.warning(self, "Проверьте данные", "Укажите корректный email.")
            self.email_input.setFocus()
            return
        website = data["website_url"]
        if website and urlparse(website).scheme.casefold() not in {"http", "https"}:
            QMessageBox.warning(
                self, "Проверьте данные", "Сайт должен начинаться с http:// или https://."
            )
            self.website_input.setFocus()
            return
        self.accept()


class CompanyWidget(QWidget):
    companyContextChanged = Signal(object)
    employeesRequested = Signal()

    def __init__(self, actor, parent=None):
        super().__init__(parent)
        self.actor = coerce_access_context(actor)
        self.company = None
        self.setObjectName("companyPage")
        self._build_ui()
        self.reload()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QFrame(self)
        toolbar.setObjectName("companyToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(20, 14, 20, 14)
        toolbar_layout.setSpacing(10)

        self.toolbar_title = QLabel("Компания", toolbar)
        self.toolbar_title.setObjectName("companyToolbarTitle")
        toolbar_layout.addWidget(self.toolbar_title)
        toolbar_layout.addStretch()

        self.employees_button = QPushButton("Сотрудники", toolbar)
        self.employees_button.setObjectName("companySecondaryButton")
        self.employees_button.clicked.connect(
            lambda checked=False: self.employeesRequested.emit()
        )
        toolbar_layout.addWidget(self.employees_button)

        self.edit_button = QPushButton("Изменить", toolbar)
        self.edit_button.setObjectName("companyPrimaryButton")
        self.edit_button.clicked.connect(self._edit_company)
        toolbar_layout.addWidget(self.edit_button)

        self.refresh_button = QPushButton("Обновить", toolbar)
        self.refresh_button.setObjectName("companySecondaryButton")
        self.refresh_button.clicked.connect(self.reload)
        toolbar_layout.addWidget(self.refresh_button)
        root.addWidget(toolbar)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("companyScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget(self.scroll)
        content.setObjectName("companyContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 26, 28, 28)
        content_layout.setSpacing(22)

        self.state_frame = QFrame(content)
        self.state_frame.setObjectName("companyState")
        state_layout = QVBoxLayout(self.state_frame)
        state_layout.setContentsMargins(32, 46, 32, 46)
        state_layout.setSpacing(12)
        state_layout.setAlignment(Qt.AlignCenter)
        self.state_title = QLabel(self.state_frame)
        self.state_title.setObjectName("companyStateTitle")
        self.state_title.setAlignment(Qt.AlignCenter)
        self.state_text = QLabel(self.state_frame)
        self.state_text.setObjectName("companyStateText")
        self.state_text.setAlignment(Qt.AlignCenter)
        self.state_text.setWordWrap(True)
        self.create_button = QPushButton("Создать компанию", self.state_frame)
        self.create_button.setObjectName("companyPrimaryButton")
        self.create_button.clicked.connect(self._create_company)
        state_layout.addWidget(self.state_title)
        state_layout.addWidget(self.state_text)
        state_layout.addSpacing(8)
        state_layout.addWidget(self.create_button, 0, Qt.AlignCenter)
        content_layout.addWidget(self.state_frame)

        self.details = QWidget(content)
        self.details.setObjectName("companyDetails")
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(20)

        heading_row = QHBoxLayout()
        heading_text = QVBoxLayout()
        heading_text.setSpacing(4)
        self.company_name = QLabel(self.details)
        self.company_name.setObjectName("companyName")
        self.company_status = QLabel(self.details)
        self.company_status.setObjectName("companyStatus")
        heading_text.addWidget(self.company_name)
        heading_text.addWidget(self.company_status)
        heading_row.addLayout(heading_text)
        heading_row.addStretch()
        self.plan_label = QLabel(self.details)
        self.plan_label.setObjectName("companyPlan")
        heading_row.addWidget(self.plan_label, 0, Qt.AlignTop)
        details_layout.addLayout(heading_row)

        usage_title = QLabel("Лимит сотрудников", self.details)
        usage_title.setObjectName("companySectionTitle")
        details_layout.addWidget(usage_title)

        usage_grid = QGridLayout()
        usage_grid.setHorizontalSpacing(12)
        usage_grid.setVerticalSpacing(12)
        self.usage_labels = {}
        for column, (key, label) in enumerate(
            (
                ("limit", "Лимит"),
                ("active_count", "Занято"),
                ("reserved_count", "Зарезервировано"),
                ("free_count", "Свободно"),
            )
        ):
            panel = QFrame(self.details)
            panel.setObjectName("companyMetric")
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(16, 13, 16, 13)
            panel_layout.setSpacing(2)
            value = QLabel("0", panel)
            value.setObjectName("companyMetricValue")
            caption = QLabel(label, panel)
            caption.setObjectName("companyMetricLabel")
            panel_layout.addWidget(value)
            panel_layout.addWidget(caption)
            usage_grid.addWidget(panel, 0, column)
            self.usage_labels[key] = value
        details_layout.addLayout(usage_grid)

        requisites_title = QLabel("Реквизиты", self.details)
        requisites_title.setObjectName("companySectionTitle")
        details_layout.addWidget(requisites_title)

        requisites = QFrame(self.details)
        requisites.setObjectName("companyRequisites")
        requisites_layout = QGridLayout(requisites)
        requisites_layout.setContentsMargins(18, 16, 18, 16)
        requisites_layout.setHorizontalSpacing(28)
        requisites_layout.setVerticalSpacing(12)
        self.field_labels = {}
        fields = (
            ("inn", "ИНН"),
            ("kpp", "КПП"),
            ("legal_address", "Юридический адрес"),
            ("actual_address", "Фактический адрес"),
            ("contact_email", "Email"),
            ("website_url", "Сайт"),
            ("owner_name", "Владелец"),
            ("updated_at", "Изменено"),
        )
        for row, (key, label) in enumerate(fields):
            caption = QLabel(label, requisites)
            caption.setObjectName("companyFieldCaption")
            value = QLabel("-", requisites)
            value.setObjectName("companyFieldValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            requisites_layout.addWidget(caption, row, 0, Qt.AlignTop)
            requisites_layout.addWidget(value, row, 1)
            self.field_labels[key] = value
        requisites_layout.setColumnStretch(1, 1)
        details_layout.addWidget(requisites)
        details_layout.addStretch()
        content_layout.addWidget(self.details, 1)

        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

    def update_actor_context(self, actor):
        self.actor = coerce_access_context(actor)
        self.reload()

    def _show_state(self, title, text, *, can_create=False):
        self.state_title.setText(title)
        self.state_text.setText(text)
        self.create_button.setVisible(can_create)
        self.state_frame.show()
        self.details.hide()
        self.edit_button.hide()
        self.employees_button.setVisible(self.actor.company_id is not None)

    def reload(self):
        if not can_open_company_page(self.actor):
            self._show_state(
                "Доступ ограничен",
                "Карточка компании доступна только владельцу компании.",
            )
            return
        if self.actor.role == "system_admin" and self.actor.company_id is None:
            self._show_state(
                "Системный контекст",
                "Для работы с компанией системному администратору нужен отдельный серверный контекст.",
            )
            return
        if self.actor.company_id is None:
            self.company = None
            self._show_state(
                "Компания не создана",
                "Создайте компанию, чтобы приглашать сотрудников и использовать общий рабочий контур.",
                can_create=True,
            )
            self.refresh_button.hide()
            return

        self.refresh_button.show()
        try:
            company = get_company(self.actor)
            usage = get_company_usage(self.actor)
        except CompanyServiceError as error:
            self._show_state("Не удалось загрузить компанию", str(error))
            return
        except Exception as error:
            self._show_state("Не удалось загрузить компанию", str(error))
            return

        if not company:
            self._show_state("Компания не найдена", "Обновите сессию и повторите вход.")
            return
        self.company = dict(company)
        self._render_company(self.company, dict(usage or {}))

    def _render_company(self, company, usage):
        self.state_frame.hide()
        self.details.show()
        self.edit_button.setVisible(self.actor.role in OWNER_ROLES)
        self.employees_button.show()
        self.company_name.setText(str(company.get("name") or "Компания"))
        status = str(company.get("status") or "active")
        self.company_status.setText(
            {"active": "Активна", "blocked": "Заблокирована", "archived": "В архиве"}.get(
                status, status
            )
        )
        plan = str(company.get("plan_code") or "default")
        self.plan_label.setText(f"Тариф: {plan}")

        limit_value = usage.get("limit", usage.get("employee_limit", company.get("employee_limit", 15)))
        active = usage.get("active_count", usage.get("current_count", 0))
        reserved = usage.get("reserved_count", 0)
        free = usage.get("free_count")
        if free is None:
            free = max(int(limit_value or 0) - int(active or 0) - int(reserved or 0), 0)
        values = {
            "limit": limit_value,
            "active_count": active,
            "reserved_count": reserved,
            "free_count": free,
        }
        for key, label in self.usage_labels.items():
            label.setText(str(values.get(key, 0)))

        owner_name = company.get("owner_name") or company.get("owner_full_name")
        fields = {
            "inn": company.get("inn"),
            "kpp": company.get("kpp"),
            "legal_address": company.get("legal_address"),
            "actual_address": company.get("actual_address"),
            "contact_email": company.get("contact_email"),
            "website_url": company.get("website_url"),
            "owner_name": owner_name,
            "updated_at": company.get("updated_at"),
        }
        for key, label in self.field_labels.items():
            label.setText(str(fields.get(key) or "-"))

    def _create_company(self):
        dialog = CompanyFormDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.create_button.setEnabled(False)
        try:
            company = create_company(self.actor, dialog.data())
        except CompanyServiceError as error:
            QMessageBox.warning(self, "Компания не создана", str(error))
            return
        except Exception as error:
            QMessageBox.critical(self, "Компания не создана", str(error))
            return
        finally:
            self.create_button.setEnabled(True)

        company = dict(company or {})
        company_id = company.get("id") or company.get("company_id")
        company_name = company.get("name") or dialog.data()["name"]
        if company_id is not None:
            self.actor = replace(
                self.actor,
                company_id=int(company_id),
                company_name=str(company_name),
                role="company_owner",
                company_status="active",
                session_generation=self.actor.session_generation + 1,
            )
        self.companyContextChanged.emit(self.actor)
        QMessageBox.information(self, "Компания создана", "Компания успешно создана.")
        self.reload()

    def _edit_company(self):
        if not self.company:
            return
        dialog = CompanyFormDialog(self.company, self)
        if dialog.exec() != QDialog.Accepted:
            return
        row_version = self.company.get("row_version")
        self.edit_button.setEnabled(False)
        try:
            updated = update_company(
                self.actor,
                dialog.data(),
                row_version=row_version,
            )
        except CompanyServiceError as error:
            QMessageBox.warning(self, "Изменения не сохранены", str(error))
            return
        except Exception as error:
            QMessageBox.critical(self, "Изменения не сохранены", str(error))
            return
        finally:
            self.edit_button.setEnabled(True)
        if updated:
            self.company = dict(updated)
        QMessageBox.information(self, "Компания", "Реквизиты сохранены.")
        self.reload()
