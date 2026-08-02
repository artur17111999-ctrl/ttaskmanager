"""
Окно авторизации.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel,
    QLineEdit, QPushButton
)
from PySide6.QtCore import Qt
from register_window import RegisterWindow


class AuthWindow(QDialog):
    """Окно входа в систему."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Вход в систему")
        self.setFixedSize(400, 370)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

        self.user_data = None
        self.init_ui()

    def init_ui(self):
        """Построение интерфейса."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(30, 20, 30, 20)

        # Заголовок
        title = QLabel("Авторизация")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("title")

        # Поле логина
        login_label = QLabel("Логин:")
        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText("Введите логин")
        self.login_input.setMinimumHeight(35)

        # Поле пароля
        password_label = QLabel("Пароль:")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Введите пароль")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMinimumHeight(35)

        # Сообщение об ошибке
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)

        # Кнопка входа
        self.login_button = QPushButton("Войти")
        self.login_button.setMinimumHeight(40)
        self.login_button.clicked.connect(self.handle_login)

        # Кнопка регистрации
        self.register_button = QPushButton("Регистрация")
        self.register_button.setMinimumHeight(35)
        self.register_button.clicked.connect(self.open_register)

        # Собираем layout
        layout.addWidget(title)
        layout.addSpacing(5)
        layout.addWidget(login_label)
        layout.addWidget(self.login_input)
        layout.addWidget(password_label)
        layout.addWidget(self.password_input)
        layout.addWidget(self.error_label)
        layout.addSpacing(5)
        layout.addWidget(self.login_button)
        layout.addWidget(self.register_button)

        self.setLayout(layout)

        # Привязываем Enter к кнопке
        self.login_input.returnPressed.connect(self.login_button.click)
        self.password_input.returnPressed.connect(self.login_button.click)

    def handle_login(self):
        """Обработка входа."""
        login = self.login_input.text().strip()
        password = self.password_input.text().strip()

        self.error_label.setVisible(False)

        if not login or not password:
            self.show_error("Заполните все поля")
            return

        from db import check_user
        success, result = check_user(login, password)

        if success:
            self.user_data = result
            self.accept()
        else:
            self.show_error(result)

    def show_error(self, message):
        """Показать ошибку."""
        self.error_label.setText(message)
        self.error_label.setVisible(True)

    def open_register(self):
        """Открыть окно регистрации."""
        register = RegisterWindow(self)
        register.exec()