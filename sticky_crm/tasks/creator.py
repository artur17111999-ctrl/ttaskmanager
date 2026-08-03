"""
Виджет создания новой задачи.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSplitter,
    QTextEdit, QLineEdit, QComboBox, QDateEdit, QListWidget, QListWidgetItem,
    QMessageBox, QFormLayout, QGroupBox
)
from PySide6.QtCore import Qt, QDate, Signal
from PySide6.QtGui import QColor

from screenshot_attachments import ScreenshotTextEdit, ScreenshotPreview
from .base import TaskBaseWidget, EMPLOYEE_ID_ROLE, TAG_ID_ROLE, TAG_COLOR_ROLE


class TaskCreatorWidget(TaskBaseWidget):
    """Виджет создания новой задачи."""
    
    taskCreated = Signal()  # Сигнал о создании задачи
    backRequested = Signal()  # Сигнал возврата назад
    
    def __init__(self, current_user_id, current_user_name):
        super().__init__(current_user_id, current_user_name)
        self.init_ui()
        self.load_employees()
        self.load_statuses()
        self.load_priorities()
        self.load_tags()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Заголовок и кнопка назад
        header_layout = QHBoxLayout()
        
        back_btn = QPushButton("← Назад")
        back_btn.setObjectName("backButton")
        header_layout.addWidget(back_btn)
        back_btn.clicked.connect(self.go_back)
        
        header_layout.addStretch()
        
        header_label = QLabel("Создание новой задачи")
        header_label.setObjectName("taskHeaderLabel")
        header_layout.addWidget(header_label)
        
        header_layout.addStretch()
        
        empty_spacer = QLabel("")
        empty_spacer.setMinimumWidth(100)
        header_layout.addWidget(empty_spacer)
        
        main_layout.addLayout(header_layout)
        
        # Основной контейнер с разделителем
        splitter = QSplitter(Qt.Horizontal)
        
        # Левая часть - основная информация
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(15)
        
        left_layout.addWidget(QLabel("Наименование задачи:"))
        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("titleEdit")
        self.title_edit.setPlaceholderText("Введите название задачи")
        left_layout.addWidget(self.title_edit)
        
        left_layout.addWidget(QLabel("Полное описание задачи:"))
        self.description_edit = ScreenshotTextEdit()
        self.description_edit.setObjectName("descriptionEdit")
        self.description_edit.setPlaceholderText("Введите подробное описание задачи")
        self.description_edit.setMinimumHeight(200)
        left_layout.addWidget(self.description_edit)
        left_layout.addWidget(ScreenshotPreview(self.description_edit))
        
        files_label = QLabel("📎 Скриншоты можно вставить из буфера обмена (Ctrl+V)")
        files_label.setObjectName("filesLabel")
        files_label.setStyleSheet("color: #888; font-style: italic;")
        left_layout.addWidget(files_label)
        
        splitter.addWidget(left_widget)
        
        # Правая часть - дополнительная информация
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(15)
        
        right_layout.addWidget(QLabel("Автор:"))
        self.author_label = QLabel(self.current_user_name)
        self.author_label.setObjectName("authorLabel")
        right_layout.addWidget(self.author_label)
        
        right_layout.addWidget(QLabel("Исполнитель:"))
        self.executor_combo = QComboBox()
        self.executor_combo.setObjectName("executorCombo")
        right_layout.addWidget(self.executor_combo)
        
        right_layout.addWidget(QLabel("Статус:"))
        self.status_combo = QComboBox()
        self.status_combo.setObjectName("statusCombo")
        right_layout.addWidget(self.status_combo)
        
        right_layout.addWidget(QLabel("Приоритет:"))
        self.priority_combo = QComboBox()
        self.priority_combo.setObjectName("priorityCombo")
        right_layout.addWidget(self.priority_combo)
        
        right_layout.addWidget(QLabel("Наблюдатели:"))
        self.observers_list = QListWidget()
        self.observers_list.setObjectName("observersList")
        right_layout.addWidget(self.observers_list)
        
        right_layout.addWidget(QLabel("Теги:"))
        tags_layout = QVBoxLayout()
        
        self.tags_list = QListWidget()
        self.tags_list.setSelectionMode(QListWidget.MultiSelection)
        self.tags_list.setObjectName("tagsList")
        tags_layout.addWidget(self.tags_list)
        
        create_tag_layout = QHBoxLayout()
        self.new_tag_edit = QLineEdit()
        self.new_tag_edit.setObjectName("newTagEdit")
        self.new_tag_edit.setPlaceholderText("Новый тег")
        create_tag_layout.addWidget(self.new_tag_edit)
        
        create_tag_btn = QPushButton("➕")
        create_tag_btn.setObjectName("createTagButton")
        create_tag_btn.setMaximumWidth(40)
        create_tag_btn.clicked.connect(self.create_new_tag)
        create_tag_layout.addWidget(create_tag_btn)
        
        tags_layout.addLayout(create_tag_layout)
        right_layout.addLayout(tags_layout)
        
        right_layout.addWidget(QLabel("Дедлайн:"))
        self.deadline_edit = QDateEdit()
        self.deadline_edit.setObjectName("deadlineEdit")
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setMinimumDate(QDate.currentDate())
        self.deadline_edit.setDate(QDate.currentDate().addDays(7))
        right_layout.addWidget(self.deadline_edit)
        
        right_layout.addStretch()
        
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        
        # Кнопки действий
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.clicked.connect(self.cancel_creation)
        buttons_layout.addWidget(cancel_btn)
        
        create_btn = QPushButton("Создать задачу")
        create_btn.setObjectName("createTaskMainButton")
        create_btn.clicked.connect(self.create_task)
        buttons_layout.addWidget(create_btn)
        
        main_layout.addLayout(buttons_layout)
    
    def load_employees(self):
        """Загрузить список сотрудников."""
        from db import get_all_employees_for_selector as db_get_all_employees_for_selector
        
        try:
            employees = db_get_all_employees_for_selector()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить сотрудников:\n{e}")
            return
        
        self.executor_combo.clear()
        self.observers_list.clear()
        
        for emp in employees:
            self.executor_combo.addItem(emp['name'], emp['id'])
            
            item = QListWidgetItem(emp['name'])
            item.setData(EMPLOYEE_ID_ROLE, emp['id'])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.observers_list.addItem(item)
    
    def load_statuses(self):
        """Загрузить список статусов из БД."""
        self.load_statuses_from_db(self.status_combo)
    
    def load_priorities(self):
        """Загрузить список приоритетов из БД."""
        self.load_priorities_from_db(self.priority_combo)
    
    def load_tags(self):
        """Загрузить существующие теги."""
        self.load_tags_from_db(self.tags_list)
    
    def create_new_tag(self):
        """Создать новый тег."""
        tag_name = self.new_tag_edit.text().strip()
        tag_id = self.create_tag(tag_name)
        
        if tag_id:
            item = QListWidgetItem(tag_name)
            item.setData(TAG_ID_ROLE, tag_id)
            item.setData(TAG_COLOR_ROLE, "#808080")
            item.setForeground(QColor("#808080"))
            self.tags_list.addItem(item)
            self.new_tag_edit.clear()
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось создать тег")
    
    def create_task(self):
        """Создать задачу."""
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Ошибка", "Введите название задачи")
            return
        
        description = self.description_edit.toPlainText().strip()
        
        if len(description) < 10:
            QMessageBox.warning(self, "Ошибка", "Описание слишком короткое (минимум 10 символов)")
            return
        
        if self.executor_combo.count() == 0:
            QMessageBox.warning(self, "Ошибка", "Нет доступных исполнителей")
            return
        
        executor_id = self.executor_combo.currentData()
        if not executor_id:
            QMessageBox.warning(self, "Ошибка", "Выберите исполнителя")
            return
        
        if self.deadline_edit.date() < QDate.currentDate():
            QMessageBox.warning(self, "Ошибка", "Дедлайн не может быть в прошлом")
            return
        
        # Получаем наблюдателей
        observers_ids = []
        for i in range(self.observers_list.count()):
            item = self.observers_list.item(i)
            if item.checkState() == Qt.Checked:
                observers_ids.append(item.data(EMPLOYEE_ID_ROLE))
        
        # Получаем теги
        selected_tag_ids = []
        for item in self.tags_list.selectedItems():
            selected_tag_ids.append(item.data(TAG_ID_ROLE))
        
        # Получаем статус и приоритет (ID)
        status_id = self.status_combo.currentData()
        priority_id = self.priority_combo.currentData()
        deadline = self.deadline_edit.date().toString("yyyy-MM-dd")
        
        from db import create_task as db_create_task
        
        try:
            task_id = db_create_task(
                title=title,
                description=description,
                author_id=self.current_user_id,
                executor_id=executor_id,
                observers_ids=observers_ids,
                deadline=deadline,
                priority=None,
                tag_ids=selected_tag_ids,
                creator_id=self.current_user_id,
                status_id=status_id,
                priority_id=priority_id,
                images=self.description_edit.screenshots
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать задачу:\n{e}")
            return
        
        if task_id:
            QMessageBox.information(self, "Успех", "Задача успешно создана")
            self.taskCreated.emit()
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось создать задачу")
    
    def cancel_creation(self):
        """Отменить создание задачи."""
        has_data = (
            self.title_edit.text().strip() or
            self.description_edit.toPlainText().strip() or
            self.description_edit.screenshots
        )
        
        if has_data:
            reply = QMessageBox.question(
                self,
                "Отмена",
                "Удалить введенные данные?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        
        self.title_edit.clear()
        self.description_edit.clear()
        self.description_edit.clear_screenshots()
        self.executor_combo.setCurrentIndex(0)
        self.deadline_edit.setDate(QDate.currentDate().addDays(7))
        self.priority_combo.setCurrentIndex(1)
        
        for i in range(self.observers_list.count()):
            item = self.observers_list.item(i)
            item.setCheckState(Qt.Unchecked)
        
        for i in range(self.tags_list.count()):
            item = self.tags_list.item(i)
            item.setSelected(False)
    
    def go_back(self):
        """Вернуться к списку задач."""
        self.backRequested.emit()
