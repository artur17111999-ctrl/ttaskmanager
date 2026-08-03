from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QFrame,
    QGraphicsOpacityEffect,
    QToolButton,
    QMenu
)
from PySide6.QtGui import QAction    # ← правильный импорт
from PySide6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QTimer
)

from contacts_widget import ContactsWidget
from tasks_widget import TasksWidget
from db import get_unread_notification_count, get_notifications, mark_notifications_as_read


class MainWindow(QMainWindow):
    def __init__(self, user_data):
        super().__init__()
        self.user_data = user_data
        self.active_button = None
        self.page_animation = None
        self.menu_buttons = []

        # Таймер для обновления бейджа уведомлений
        self.notification_timer = QTimer(self)
        self.notification_timer.timeout.connect(self.update_notification_badge)
        self.notification_timer.start(5000)

        self.setWindowTitle("Sticky CRM")
        self.init_ui()
        self.showMaximized()

        if self.menu_buttons:
            self.menu_buttons[0].click()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Левая панель меню
        self.menu_panel = QFrame()
        self.menu_panel.setObjectName("menuPanel")
        self.menu_panel.setFixedWidth(300)

        menu_layout = QVBoxLayout(self.menu_panel)
        menu_layout.setContentsMargins(10, 10, 10, 10)
        menu_layout.setSpacing(5)

        menu_header = QLabel("Sticky CRM")
        menu_header.setObjectName("menuHeader")
        menu_header.setAlignment(Qt.AlignCenter)
        menu_layout.addWidget(menu_header)

        menu_data = [
            ("👥  Контакты", 1, "Контакты"),
            ("✓  Задачи", 2, "Задачи"),
            ("📅  Календарь", 0, "Календарь"),
            ("📄  Документы", 0, "Документы"),
            ("📊  Отчёты", 0, "Отчёты"),
            ("⚙  Настройки", 0, "Настройки")
        ]

        for text, page_index, title in menu_data:
            btn = QPushButton(text)
            btn.setObjectName("menuButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=page_index, b=btn, t=title:
                                self.change_page(idx, b, t))
            self.menu_buttons.append(btn)
            menu_layout.addWidget(btn)

        menu_layout.addStretch()

        user_info = QLabel(f"👤 {self.user_data.get('full_name', 'Пользователь')}")
        user_info.setObjectName("userInfoLabel")
        user_info.setAlignment(Qt.AlignCenter)
        menu_layout.addWidget(user_info)

        # Правая часть с верхней панелью и контентом
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Верхняя панель с заголовком раздела и кнопкой уведомлений
        self.header_panel = QFrame()
        self.header_panel.setObjectName("headerPanel")
        header_layout = QHBoxLayout(self.header_panel)
        header_layout.setContentsMargins(15, 8, 15, 8)

        self.page_title_label = QLabel("Контакты")
        self.page_title_label.setObjectName("pageTitleLabel")
        header_layout.addWidget(self.page_title_label)

        header_layout.addStretch()

        # Кнопка уведомлений
        self.notif_btn = QToolButton()
        self.notif_btn.setObjectName("notificationButton")
        self.notif_btn.setText("🔔")
        self.notif_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.notif_btn.setPopupMode(QToolButton.InstantPopup)
        self.notif_btn.setMenu(self.create_notification_menu())
        header_layout.addWidget(self.notif_btn)

        right_layout.addWidget(self.header_panel)

        # Стекированный контент страниц
        self.content_area = QStackedWidget()
        self.content_area.setObjectName("contentArea")

        empty_page = QLabel("Выберите пункт меню")
        empty_page.setAlignment(Qt.AlignCenter)
        empty_page.setObjectName("emptyPage")
        self.content_area.addWidget(empty_page)

        self.contacts_page = ContactsWidget(current_user_id=self.user_data['employee_id'])
        self.content_area.addWidget(self.contacts_page)

        self.tasks_page = TasksWidget(
            current_user_id=self.user_data['employee_id'],
            current_user_name=self.user_data['full_name']
        )
        self.content_area.addWidget(self.tasks_page)

        right_layout.addWidget(self.content_area, 1)

        main_layout.addWidget(self.menu_panel)
        main_layout.addWidget(right_widget, 1)

    def create_notification_menu(self):
        self.notif_menu = QMenu(self)
        self.notif_menu.aboutToShow.connect(self.refresh_notification_menu)
        return self.notif_menu

    def refresh_notification_menu(self):
        self.notif_menu.clear()
        notifs = get_notifications(self.user_data['employee_id'], limit=10)
        if not notifs:
            empty_action = QAction("Нет уведомлений", self)
            empty_action.setEnabled(False)
            self.notif_menu.addAction(empty_action)
        else:
            for n in notifs:
                prefix = "🔵 " if not n['is_read'] else "  "
                action = QAction(f"{prefix}{n['text']}  ({n['created_at']})", self)
                action.setData(n['chat_id'])
                action.triggered.connect(lambda checked, chat_id=n['chat_id']: self.open_chat_from_notification(chat_id))
                self.notif_menu.addAction(action)
            self.notif_menu.addSeparator()
            mark_all_action = QAction("Отметить все прочитанными", self)
            mark_all_action.triggered.connect(self.mark_all_read)
            self.notif_menu.addAction(mark_all_action)

    def open_chat_from_notification(self, chat_id):
        if chat_id:
            # Переключаемся на контакты
            self.change_page(1, self.menu_buttons[0], "Контакты")
            if hasattr(self.contacts_page, 'open_chat_by_id'):
                self.contacts_page.open_chat_by_id(chat_id)

    def mark_all_read(self):
        mark_notifications_as_read(self.user_data['employee_id'])
        self.update_notification_badge()

    def update_notification_badge(self):
        count = get_unread_notification_count(self.user_data['employee_id'])
        if count > 0:
            self.notif_btn.setText(f"🔔 {count}")
        else:
            self.notif_btn.setText("🔔")

    def change_page(self, index, button, title=None):
        if self.active_button:
            self.active_button.setChecked(False)
        button.setChecked(True)
        self.active_button = button
        if title:
            self.page_title_label.setText(title)

        widget = self.content_area.widget(index)
        effect = QGraphicsOpacityEffect()
        widget.setGraphicsEffect(effect)

        animation = QPropertyAnimation(effect, b"opacity")
        animation.setDuration(300)
        animation.setStartValue(0)
        animation.setEndValue(1)
        animation.setEasingCurve(QEasingCurve.InOutCubic)

        self.content_area.setCurrentIndex(index)
        animation.start()

        def cleanup():
            widget.setGraphicsEffect(None)
        animation.finished.connect(cleanup)

        self.page_animation = animation

    def resizeEvent(self, event):
        if hasattr(self, "menu_panel"):
            width = int(self.width() * 0.18)
            if width < 260:
                width = 260
            if width > 360:
                width = 360
            self.menu_panel.setFixedWidth(width)
        super().resizeEvent(event)