"""
Окно регистрации.
"""

import re
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QDateEdit, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, QDate


class RegisterWindow(QDialog):
    """Окно регистрации нового пользователя."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Регистрация")
        self.setFixedSize(450, 650)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

        self.init_ui()
        self.load_comboboxes()

    def init_ui(self):
        """Построение интерфейса."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(8)
        layout.setContentsMargins(25, 15, 25, 15)

        # Заголовок
        title = QLabel("Регистрация сотрудника")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("title")
        title.setMinimumHeight(35)

        # Фамилия
        last_name_label = QLabel("Фамилия:")
        self.last_name_input = QLineEdit()
        self.last_name_input.setPlaceholderText("Введите фамилию")
        self.last_name_input.setMinimumHeight(30)

        # Имя
        first_name_label = QLabel("Имя:")
        self.first_name_input = QLineEdit()
        self.first_name_input.setPlaceholderText("Введите имя")
        self.first_name_input.setMinimumHeight(30)

        # Отчество
        middle_name_label = QLabel("Отчество:")
        self.middle_name_input = QLineEdit()
        self.middle_name_input.setPlaceholderText("Введите отчество (необязательно)")
        self.middle_name_input.setMinimumHeight(30)

        # Дата рождения
        birth_date_label = QLabel("Дата рождения:")
        self.birth_date_input = QDateEdit()
        self.birth_date_input.setCalendarPopup(True)
        self.birth_date_input.setDate(QDate(1990, 1, 1))
        self.birth_date_input.setMinimumHeight(30)

        # Дата начала работы
        start_date_label = QLabel("Дата начала работы:")
        self.start_date_input = QDateEdit()
        self.start_date_input.setCalendarPopup(True)
        self.start_date_input.setDate(QDate.currentDate())
        self.start_date_input.setMinimumHeight(30)

        # Должность
        position_label = QLabel("Должность:")
        self.position_combo = QComboBox()
        self.position_combo.setMinimumHeight(30)

        # Отдел
        department_label = QLabel("Отдел:")
        self.department_combo = QComboBox()
        self.department_combo.setMinimumHeight(30)

        # Email
        email_label = QLabel("Email:")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Введите email")
        self.email_input.setMinimumHeight(30)

        # Логин
        login_label = QLabel("Логин:")
        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText("Придумайте логин")
        self.login_input.setMinimumHeight(30)

        # Пароль
        password_label = QLabel("Пароль:")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Придумайте пароль")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMinimumHeight(30)

        # Подтверждение пароля
        password_confirm_label = QLabel("Подтверждение пароля:")
        self.password_confirm_input = QLineEdit()
        self.password_confirm_input.setPlaceholderText("Повторите пароль")
        self.password_confirm_input.setEchoMode(QLineEdit.Password)
        self.password_confirm_input.setMinimumHeight(30)

        # Требования к паролю
        self.password_requirements = QLabel(
            "Пароль должен содержать:\n"
            "• Не менее 8 символов\n"
            "• Только латинские буквы\n"
            "• Минимум одну заглавную букву\n"
            "• Минимум одну цифру\n"
            "• Минимум один спецсимвол"
        )
        self.password_requirements.setStyleSheet("color: #666666; font-size: 12px; padding: 5px;")
        self.password_requirements.setWordWrap(True)

        # Сообщение
        self.message_label = QLabel("")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setMinimumHeight(25)

        # Кнопка
        self.register_button = QPushButton("Зарегистрировать")
        self.register_button.setMinimumHeight(38)
        self.register_button.clicked.connect(self.handle_register)

        # Собираем
        layout.addWidget(title)
        layout.addWidget(last_name_label)
        layout.addWidget(self.last_name_input)
        layout.addWidget(first_name_label)
        layout.addWidget(self.first_name_input)
        layout.addWidget(middle_name_label)
        layout.addWidget(self.middle_name_input)
        layout.addWidget(birth_date_label)
        layout.addWidget(self.birth_date_input)
        layout.addWidget(start_date_label)
        layout.addWidget(self.start_date_input)
        layout.addWidget(position_label)
        layout.addWidget(self.position_combo)
        layout.addWidget(department_label)
        layout.addWidget(self.department_combo)
        layout.addWidget(email_label)
        layout.addWidget(self.email_input)
        layout.addWidget(login_label)
        layout.addWidget(self.login_input)
        layout.addWidget(password_label)
        layout.addWidget(self.password_input)
        layout.addWidget(password_confirm_label)
        layout.addWidget(self.password_confirm_input)
        layout.addWidget(self.password_requirements)
        layout.addWidget(self.message_label)
        layout.addWidget(self.register_button)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def load_comboboxes(self):
        """Загрузить данные в выпадающие списки."""
        from db import get_positions, get_departments

        positions = get_positions()
        for pos_id, pos_title in positions:
            self.position_combo.addItem(pos_title, pos_id)

        departments = get_departments()
        for dep_id, dep_title in departments:
            self.department_combo.addItem(dep_title, dep_id)

    def validate_password(self, password):
        """
        Проверить пароль по правилам.
        Возвращает (True, "") если всё ок,
        иначе (False, "причина ошибки").
        """
        errors = []

        # Длина не менее 8
        if len(password) < 8:
            errors.append("Пароль должен содержать не менее 8 символов")

        # Только латиница, цифры и спецсимволы
        if not re.match("^[a-zA-Z0-9!@#$%^&*()_+\\-=\\[\\]{};':\"\\\\|,.<>\\/?`~]+$", password):
            errors.append("Пароль должен содержать только латинские буквы, цифры и спецсимволы")
        else:
            # Минимум одна заглавная буква
            if not re.search("[A-Z]", password):
                errors.append("Не хватает заглавной буквы (A-Z)")

            # Минимум одна цифра
            if not re.search("[0-9]", password):
                errors.append("Не хватает цифры (0-9)")

            # Минимум один спецсимвол
            if not re.search("[!@#$%^&*()_+\\-=\\[\\]{};':\"\\\\|,.<>\\/?`~]", password):
                errors.append("Не хватает спецсимвола (!@#$%^&* и т.д.)")

        if errors:
            return False, "\n".join(errors)

        return True, ""

    def handle_register(self):
        """Обработка регистрации."""
        from db import register_user

        last_name = self.last_name_input.text().strip()
        first_name = self.first_name_input.text().strip()
        middle_name = self.middle_name_input.text().strip()
        birth_date = self.birth_date_input.date().toString("yyyy-MM-dd")
        start_date = self.start_date_input.date().toString("yyyy-MM-dd")
        position_id = self.position_combo.currentData()
        department_id = self.department_combo.currentData()
        email = self.email_input.text().strip()
        login = self.login_input.text().strip()
        password = self.password_input.text().strip()
        password_confirm = self.password_confirm_input.text().strip()

        # Проверка обязательных полей
        if not last_name or not first_name:
            self.show_message("Фамилия и имя обязательны", "error")
            return

        if not email:
            self.show_message("Email обязателен", "error")
            return

        if not login:
            self.show_message("Логин обязателен", "error")
            return

        if not password:
            self.show_message("Пароль обязателен", "error")
            return

        # Проверка подтверждения пароля
        if password != password_confirm:
            self.show_message("Пароли не совпадают", "error")
            return

        # Проверка правил пароля
        valid, error_message = self.validate_password(password)
        if not valid:
            self.show_message(error_message, "error")
            return

        # Регистрируем
        success, message = register_user(
            last_name, first_name, middle_name,
            birth_date, start_date,
            position_id, department_id,
            email, login, password
        )

        if success:
            self.show_message(message, "success")
            self.register_button.setEnabled(False)
        else:
            self.show_message(message, "error")

    def show_message(self, message, msg_type):
        """Показать сообщение."""
        self.message_label.setText(message)
        if msg_type == "error":
            self.message_label.setStyleSheet("color: #d32f2f; font-size: 13px; padding: 5px;")
        else:
            self.message_label.setStyleSheet("color: #2e7d32; font-size: 13px; padding: 5px;")