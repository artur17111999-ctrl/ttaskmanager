from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QSplitter, QTextEdit, QLineEdit, QComboBox, QDateEdit,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QMenu,
    QToolButton, QSizePolicy, QStackedWidget, QGroupBox, QCheckBox
)
from PySide6.QtCore import Qt, QDate, Signal
from PySide6.QtGui import QAction

from db import (
    get_all_employees_for_selector,
    get_all_tags,
    create_tag,
    create_task,
    get_tasks,
    get_task_detail
)


class TaskCreatorWidget(QWidget):
    """Виджет создания новой задачи."""
    
    taskCreated = Signal()  # Сигнал о создании задачи
    
    def __init__(self, current_user_id, current_user_name):
        super().__init__()
        self.current_user_id = current_user_id
        self.current_user_name = current_user_name
        self.selected_tags = []
        self.attached_files = []
        self.init_ui()
        self.load_employees()
        self.load_tags()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Заголовок
        header_label = QLabel("Создание новой задачи")
        header_label.setObjectName("taskHeaderLabel")
        header_label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        main_layout.addWidget(header_label)
        
        # Основной контейнер с разделителем
        splitter = QSplitter(Qt.Horizontal)
        
        # Левая часть - основная информация
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(15)
        
        # Наименование задачи
        left_layout.addWidget(QLabel("Наименование задачи:"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Введите название задачи")
        self.title_edit.setMinimumHeight(40)
        self.title_edit.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #0078d4;
            }
        """)
        left_layout.addWidget(self.title_edit)
        
        # Полное описание
        left_layout.addWidget(QLabel("Полное описание задачи:"))
        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Введите подробное описание задачи")
        self.description_edit.setMinimumHeight(200)
        self.description_edit.setStyleSheet("""
            QTextEdit {
                padding: 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
                font-size: 14px;
            }
            QTextEdit:focus {
                border: 2px solid #0078d4;
            }
        """)
        left_layout.addWidget(self.description_edit)
        
        # Прикрепление файлов
        files_layout = QHBoxLayout()
        self.files_label = QLabel("Прикрепленные файлы: нет")
        self.files_label.setStyleSheet("color: #666;")
        files_layout.addWidget(self.files_label)
        
        attach_btn = QPushButton("📎 Прикрепить файл")
        attach_btn.clicked.connect(self.attach_file)
        attach_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        files_layout.addWidget(attach_btn)
        left_layout.addLayout(files_layout)
        
        splitter.addWidget(left_widget)
        
        # Правая часть - дополнительная информация
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(15)
        
        # Автор (автоматически)
        right_layout.addWidget(QLabel("Автор:"))
        self.author_label = QLabel(self.current_user_name)
        self.author_label.setStyleSheet("""
            QLabel {
                background-color: #e3f2fd;
                padding: 10px;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
        right_layout.addWidget(self.author_label)
        
        # Исполнитель
        right_layout.addWidget(QLabel("Исполнитель:"))
        self.executor_combo = QComboBox()
        self.executor_combo.setMinimumHeight(40)
        self.executor_combo.setStyleSheet("""
            QComboBox {
                padding: 8px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QComboBox:focus {
                border: 2px solid #0078d4;
            }
        """)
        right_layout.addWidget(self.executor_combo)
        
        # Наблюдатели
        right_layout.addWidget(QLabel("Наблюдатели:"))
        self.observers_list = QListWidget()
        self.observers_list.setMinimumHeight(100)
        self.observers_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
            }
        """)
        right_layout.addWidget(self.observers_list)
        
        # Теги
        right_layout.addWidget(QLabel("Теги:"))
        tags_layout = QVBoxLayout()
        
        self.tags_list = QListWidget()
        self.tags_list.setSelectionMode(QListWidget.MultiSelection)
        self.tags_list.setMinimumHeight(80)
        self.tags_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
            }
        """)
        tags_layout.addWidget(self.tags_list)
        
        create_tag_layout = QHBoxLayout()
        self.new_tag_edit = QLineEdit()
        self.new_tag_edit.setPlaceholderText("Новый тег")
        self.new_tag_edit.setMinimumHeight(35)
        create_tag_layout.addWidget(self.new_tag_edit)
        
        create_tag_btn = QPushButton("➕")
        create_tag_btn.setMaximumWidth(40)
        create_tag_btn.clicked.connect(self.create_new_tag)
        create_tag_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0063b1;
            }
        """)
        create_tag_layout.addWidget(create_tag_btn)
        
        tags_layout.addLayout(create_tag_layout)
        right_layout.addLayout(tags_layout)
        
        # Дедлайн
        right_layout.addWidget(QLabel("Дедлайн:"))
        self.deadline_edit = QDateEdit()
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setMinimumDate(QDate.currentDate())
        self.deadline_edit.setDate(QDate.currentDate().addDays(7))
        self.deadline_edit.setMinimumHeight(40)
        self.deadline_edit.setStyleSheet("""
            QDateEdit {
                padding: 8px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QDateEdit:focus {
                border: 2px solid #0078d4;
            }
        """)
        right_layout.addWidget(self.deadline_edit)
        
        # Критичность
        right_layout.addWidget(QLabel("Уровень критичности:"))
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["Низкий", "Средний", "Критичный", "Блокер"])
        self.priority_combo.setMinimumHeight(40)
        self.priority_combo.setStyleSheet("""
            QComboBox {
                padding: 8px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QComboBox:focus {
                border: 2px solid #0078d4;
            }
        """)
        right_layout.addWidget(self.priority_combo)
        
        right_layout.addStretch()
        
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        
        # Кнопки действий
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.cancel_creation)
        cancel_btn.setMinimumHeight(45)
        cancel_btn.setMinimumWidth(120)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        buttons_layout.addWidget(cancel_btn)
        
        create_btn = QPushButton("Создать задачу")
        create_btn.clicked.connect(self.create_task)
        create_btn.setMinimumHeight(45)
        create_btn.setMinimumWidth(150)
        create_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0063b1;
            }
        """)
        buttons_layout.addWidget(create_btn)
        
        main_layout.addLayout(buttons_layout)
    
    def load_employees(self):
        """Загрузить список сотрудников."""
        employees = get_all_employees_for_selector()
        self.executor_combo.clear()
        self.observers_list.clear()
        
        for emp in employees:
            self.executor_combo.addItem(emp['name'], emp['id'])
            
            item = QListWidgetItem(emp['name'])
            item.setData(Qt.UserRole, emp['id'])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.observers_list.addItem(item)
    
    def load_tags(self):
        """Загрузить существующие теги."""
        tags = get_all_tags()
        self.tags_list.clear()
        
        for tag in tags:
            item = QListWidgetItem(f"{tag[1]}")
            item.setData(Qt.UserRole, tag[0])
            item.setData(Qt.UserRole + 1, tag[2])  # цвет
            self.tags_list.addItem(item)
    
    def create_new_tag(self):
        """Создать новый тег."""
        tag_name = self.new_tag_edit.text().strip()
        if not tag_name:
            QMessageBox.warning(self, "Ошибка", "Введите название тега")
            return
        
        tag_id = create_tag(tag_name)
        if tag_id:
            item = QListWidgetItem(tag_name)
            item.setData(Qt.UserRole, tag_id)
            self.tags_list.addItem(item)
            self.new_tag_edit.clear()
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось создать тег")
    
    def attach_file(self):
        """Прикрепить файл к задаче."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите файл")
        if file_path:
            self.attached_files.append(file_path)
            self.files_label.setText(f"Прикреплено файлов: {len(self.attached_files)}")
    
    def create_task(self):
        """Создать задачу."""
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Ошибка", "Введите название задачи")
            return
        
        description = self.description_edit.toPlainText().strip()
        
        executor_id = self.executor_combo.currentData()
        if not executor_id:
            QMessageBox.warning(self, "Ошибка", "Выберите исполнителя")
            return
        
        # Получаем наблюдателей
        observers_ids = []
        for i in range(self.observers_list.count()):
            item = self.observers_list.item(i)
            if item.checkState() == Qt.Checked:
                observers_ids.append(item.data(Qt.UserRole))
        
        # Получаем теги
        selected_tag_ids = []
        for item in self.tags_list.selectedItems():
            selected_tag_ids.append(item.data(Qt.UserRole))
        
        deadline = self.deadline_edit.date().toString("yyyy-MM-dd")
        priority = self.priority_combo.currentText()
        
        task_id = create_task(
            title=title,
            description=description,
            author_id=self.current_user_id,
            executor_id=executor_id,
            observers_ids=observers_ids,
            deadline=deadline,
            priority=priority,
            tag_ids=selected_tag_ids,
            creator_id=self.current_user_id
        )
        
        if task_id:
            QMessageBox.information(self, "Успех", "Задача успешно создана")
            self.taskCreated.emit()
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось создать задачу")
    
    def cancel_creation(self):
        """Отменить создание задачи."""
        self.title_edit.clear()
        self.description_edit.clear()
        self.executor_combo.setCurrentIndex(0)
        self.deadline_edit.setDate(QDate.currentDate().addDays(7))
        self.priority_combo.setCurrentIndex(1)
        self.attached_files.clear()
        self.files_label.setText("Прикрепленные файлы: нет")
        
        for i in range(self.observers_list.count()):
            item = self.observers_list.item(i)
            item.setCheckState(Qt.Unchecked)
        
        for i in range(self.tags_list.count()):
            item = self.tags_list.item(i)
            item.setSelected(False)


class TasksWidget(QWidget):
    """Основной виджет управления задачами."""
    
    def __init__(self, current_user_id, current_user_name):
        super().__init__()
        self.current_user_id = current_user_id
        self.current_user_name = current_user_name
        self.init_ui()
        self.load_tasks()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Стекированный виджет для переключения между списком и созданием
        self.stacked_widget = QStackedWidget()
        
        # Страница списка задач
        self.list_page = QWidget()
        list_layout = QVBoxLayout(self.list_page)
        list_layout.setContentsMargins(20, 20, 20, 20)
        list_layout.setSpacing(15)
        
        # Заголовок и кнопка создания
        header_layout = QHBoxLayout()
        title_label = QLabel("Все задачи")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        create_btn = QPushButton("➕ Создать задачу")
        create_btn.setObjectName("createTaskButton")
        create_btn.setMinimumHeight(40)
        create_btn.setMinimumWidth(150)
        create_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #0063b1;
            }
        """)
        create_btn.clicked.connect(self.show_creator)
        header_layout.addWidget(create_btn)
        
        list_layout.addLayout(header_layout)
        
        # Список задач
        self.tasks_scroll = QScrollArea()
        self.tasks_scroll.setWidgetResizable(True)
        self.tasks_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tasks_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #f9f9f9;
            }
        """)
        
        self.tasks_container = QWidget()
        self.tasks_layout = QVBoxLayout(self.tasks_container)
        self.tasks_layout.setContentsMargins(0, 0, 0, 0)
        self.tasks_layout.setSpacing(10)
        self.tasks_layout.addStretch()
        
        self.tasks_scroll.setWidget(self.tasks_container)
        list_layout.addWidget(self.tasks_scroll)
        
        self.stacked_widget.addWidget(self.list_page)
        
        # Страница создания задачи
        self.creator_widget = TaskCreatorWidget(self.current_user_id, self.current_user_name)
        self.creator_widget.taskCreated.connect(self.on_task_created)
        self.stacked_widget.addWidget(self.creator_widget)
        
        main_layout.addWidget(self.stacked_widget)
    
    def load_tasks(self):
        """Загрузить список задач."""
        # Очищаем текущий список
        while self.tasks_layout.count() > 1:  # 1 - это stretch
            item = self.tasks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        tasks = get_tasks()
        
        if not tasks:
            empty_label = QLabel("Нет задач")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("font-size: 18px; color: #999; padding: 50px;")
            self.tasks_layout.insertWidget(0, empty_label)
            return
        
        for task in tasks:
            task_card = self.create_task_card(task)
            self.tasks_layout.insertWidget(self.tasks_layout.count() - 1, task_card)
    
    def create_task_card(self, task_data):
        """Создать карточку задачи."""
        card = QFrame()
        card.setObjectName("taskCard")
        card.setStyleSheet("""
            QFrame#taskCard {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 15px;
            }
            QFrame#taskCard:hover {
                border: 1px solid #0078d4;
                background-color: #f5f9ff;
            }
        """)
        
        layout = QVBoxLayout(card)
        layout.setSpacing(8)
        
        # Заголовок и статус
        header_layout = QHBoxLayout()
        
        title_label = QLabel(task_data['title'])
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        # Приоритет
        priority_colors = {
            "Низкий": "#4caf50",
            "Средний": "#ff9800",
            "Критичный": "#f44336",
            "Блокер": "#9c27b0"
        }
        priority_color = priority_colors.get(task_data['priority'], "#808080")
        
        priority_label = QLabel(task_data['priority'])
        priority_label.setStyleSheet(f"""
            QLabel {{
                background-color: {priority_color};
                color: white;
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: bold;
            }}
        """)
        header_layout.addWidget(priority_label)
        
        layout.addLayout(header_layout)
        
        # Описание (обрезанное)
        desc = task_data['description'] or "Нет описания"
        if len(desc) > 150:
            desc = desc[:150] + "..."
        
        desc_label = QLabel(desc)
        desc_label.setStyleSheet("color: #666; font-size: 14px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Информация об исполнителе и дедлайне
        info_layout = QHBoxLayout()
        
        executor_label = QLabel(f"👤 {task_data['executor_name']}")
        executor_label.setStyleSheet("color: #555; font-size: 13px;")
        info_layout.addWidget(executor_label)
        
        if task_data['deadline']:
            deadline_label = QLabel(f"📅 {task_data['deadline']}")
            deadline_label.setStyleSheet("color: #555; font-size: 13px;")
            info_layout.addWidget(deadline_label)
        
        info_layout.addStretch()
        
        author_label = QLabel(f"Автор: {task_data['author_name']}")
        author_label.setStyleSheet("color: #888; font-size: 12px;")
        info_layout.addWidget(author_label)
        
        layout.addLayout(info_layout)
        
        return card
    
    def show_creator(self):
        """Показать страницу создания задачи."""
        self.stacked_widget.setCurrentWidget(self.creator_widget)
    
    def on_task_created(self):
        """Обработчик создания задачи."""
        self.load_tasks()
        self.stacked_widget.setCurrentWidget(self.list_page)
