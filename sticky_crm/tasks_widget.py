from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QSplitter, QTextEdit, QLineEdit, QComboBox, QDateEdit,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QStackedWidget,
    QDialog, QGroupBox, QFormLayout
)
from PySide6.QtCore import Qt, QDate, Signal
from PySide6.QtGui import QColor

from db import (
    get_all_employees_for_selector as db_get_all_employees_for_selector,
    get_all_tags as db_get_all_tags,
    create_tag as db_create_tag,
    create_task as db_create_task,
    get_tasks as db_get_tasks,
    get_task_detail,
    update_task,
    delete_task
)

# Константы для ролей данных
TAG_COLOR_ROLE = Qt.UserRole + 1
EMPLOYEE_ID_ROLE = Qt.UserRole
TAG_ID_ROLE = Qt.UserRole + 2


class TaskCreatorWidget(QWidget):
    """Виджет создания новой задачи."""
    
    taskCreated = Signal()  # Сигнал о создании задачи
    backRequested = Signal()  # Сигнал возврата назад
    
    def __init__(self, current_user_id, current_user_name):
        super().__init__()
        self.current_user_id = current_user_id
        self.current_user_name = current_user_name
        self.init_ui()
        self.load_employees()
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
        
        # Пустой спейсер для баланса
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
        
        # Наименование задачи
        left_layout.addWidget(QLabel("Наименование задачи:"))
        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("titleEdit")
        self.title_edit.setPlaceholderText("Введите название задачи")
        left_layout.addWidget(self.title_edit)
        
        # Полное описание
        left_layout.addWidget(QLabel("Полное описание задачи:"))
        self.description_edit = QTextEdit()
        self.description_edit.setObjectName("descriptionEdit")
        self.description_edit.setPlaceholderText("Введите подробное описание задачи")
        self.description_edit.setMinimumHeight(200)
        left_layout.addWidget(self.description_edit)
        
        # Информация о файлах (заглушка)
        files_label = QLabel("📎 Файлы будут доступны позже")
        files_label.setObjectName("filesLabel")
        files_label.setStyleSheet("color: #888; font-style: italic;")
        left_layout.addWidget(files_label)
        
        splitter.addWidget(left_widget)
        
        # Правая часть - дополнительная информация
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(15)
        
        # Автор (автоматически)
        right_layout.addWidget(QLabel("Автор:"))
        self.author_label = QLabel(self.current_user_name)
        self.author_label.setObjectName("authorLabel")
        right_layout.addWidget(self.author_label)
        
        # Исполнитель
        right_layout.addWidget(QLabel("Исполнитель:"))
        self.executor_combo = QComboBox()
        self.executor_combo.setObjectName("executorCombo")
        right_layout.addWidget(self.executor_combo)
        
        # Наблюдатели
        right_layout.addWidget(QLabel("Наблюдатели:"))
        self.observers_list = QListWidget()
        self.observers_list.setObjectName("observersList")
        right_layout.addWidget(self.observers_list)
        
        # Теги
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
        
        # Дедлайн
        right_layout.addWidget(QLabel("Дедлайн:"))
        self.deadline_edit = QDateEdit()
        self.deadline_edit.setObjectName("deadlineEdit")
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setMinimumDate(QDate.currentDate())
        self.deadline_edit.setDate(QDate.currentDate().addDays(7))
        right_layout.addWidget(self.deadline_edit)
        
        # Критичность
        right_layout.addWidget(QLabel("Уровень критичности:"))
        self.priority_combo = QComboBox()
        self.priority_combo.setObjectName("priorityCombo")
        self.priority_combo.addItems(["Низкий", "Средний", "Критичный", "Блокер"])
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
        try:
            employees = db_get_all_employees_for_selector()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось загрузить сотрудников:\n{e}"
            )
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
    
    def load_tags(self):
        """Загрузить существующие теги."""
        try:
            tags = db_get_all_tags()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось загрузить теги:\n{e}"
            )
            return
        
        self.tags_list.clear()
        
        for tag in tags:
            item = QListWidgetItem(f"{tag[1]}")
            item.setData(TAG_ID_ROLE, tag[0])
            item.setData(TAG_COLOR_ROLE, tag[2])  # цвет
            
            # Применяем цвет тега
            if tag[2]:
                item.setForeground(QColor(tag[2]))
            
            self.tags_list.addItem(item)
    
    def create_new_tag(self):
        """Создать новый тег."""
        tag_name = self.new_tag_edit.text().strip()
        if not tag_name:
            QMessageBox.warning(self, "Ошибка", "Введите название тега")
            return
        
        try:
            tag_id = db_create_tag(tag_name)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось создать тег:\n{e}"
            )
            return
        
        if tag_id:
            item = QListWidgetItem(tag_name)
            item.setData(TAG_ID_ROLE, tag_id)
            # Сохраняем цвет (по умолчанию серый)
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
        
        # Валидация описания
        if len(description) < 10:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Описание слишком короткое (минимум 10 символов)"
            )
            return
        
        # Проверка наличия исполнителей
        if self.executor_combo.count() == 0:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Нет доступных исполнителей"
            )
            return
        
        executor_id = self.executor_combo.currentData()
        if not executor_id:
            QMessageBox.warning(self, "Ошибка", "Выберите исполнителя")
            return
        
        # Проверка дедлайна
        if self.deadline_edit.date() < QDate.currentDate():
            QMessageBox.warning(
                self,
                "Ошибка",
                "Дедлайн не может быть в прошлом"
            )
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
        
        deadline = self.deadline_edit.date().toString("yyyy-MM-dd")
        priority = self.priority_combo.currentText()
        
        try:
            task_id = db_create_task(
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
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось создать задачу:\n{e}"
            )
            return
        
        if task_id:
            QMessageBox.information(self, "Успех", "Задача успешно создана")
            self.taskCreated.emit()
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось создать задачу")
    
    def cancel_creation(self):
        """Отменить создание задачи."""
        # Проверка, есть ли введенные данные
        has_data = (
            self.title_edit.text().strip() or
            self.description_edit.toPlainText().strip()
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


class TaskDetailWidget(QWidget):
    """Виджет детального просмотра задачи."""
    
    taskUpdated = Signal()  # Сигнал об обновлении задачи
    backRequested = Signal()  # Сигнал возврата назад
    
    def __init__(self, task_data, current_user_id, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.current_user_id = current_user_id
        self.init_ui()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Заголовок с номером задачи
        header_label = QLabel(f"Задача №{self.task_data['id']}")
        header_label.setObjectName("taskDetailHeaderLabel")
        header_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(header_label)
        
        # Основной контент в скролл-области
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)
        
        # Название задачи
        title_group = QGroupBox("Название")
        title_layout = QVBoxLayout(title_group)
        title_label = QLabel(self.task_data.get('title', 'N/A'))
        title_label.setWordWrap(True)
        title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        title_layout.addWidget(title_label)
        content_layout.addWidget(title_group)
        
        # Описание
        desc_group = QGroupBox("Описание")
        desc_layout = QVBoxLayout(desc_group)
        desc_text = QTextEdit()
        desc_text.setPlainText(self.task_data.get('description', 'N/A'))
        desc_text.setReadOnly(True)
        desc_text.setMinimumHeight(150)
        desc_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        desc_layout.addWidget(desc_text)
        content_layout.addWidget(desc_group)
        
        # Информация (Автор, Исполнитель, Статус, Приоритет, Дедлайн)
        info_group = QGroupBox("Информация")
        info_layout = QFormLayout(info_group)
        
        author_label = QLabel(self.task_data.get('author_name', 'N/A'))
        info_layout.addRow("Автор:", author_label)
        
        executor_label = QLabel(self.task_data.get('executor_name', 'N/A'))
        info_layout.addRow("Исполнитель:", executor_label)
        
        status_label = QLabel(self.task_data.get('status', 'N/A'))
        info_layout.addRow("Статус:", status_label)
        
        priority_label = QLabel(self.task_data.get('priority', 'N/A'))
        info_layout.addRow("Приоритет:", priority_label)
        
        deadline_val = self.task_data.get('deadline')
        deadline_str = str(deadline_val) if deadline_val else 'Не установлен'
        deadline_label = QLabel(deadline_str)
        info_layout.addRow("Дедлайн:", deadline_label)
        
        created_at_val = self.task_data.get('created_at')
        created_at_str = str(created_at_val)[:19] if created_at_val else 'N/A'
        created_at_label = QLabel(created_at_str)
        info_layout.addRow("Создана:", created_at_label)
        
        content_layout.addWidget(info_group)
        
        # Наблюдатели
        observers_group = QGroupBox("Наблюдатели")
        observers_layout = QVBoxLayout(observers_group)
        self.observers_list = QListWidget()
        self.observers_list.setMaximumHeight(100)
        observers = self.task_data.get('observers', [])
        if observers:
            for obs in observers:
                item = QListWidgetItem(obs)
                self.observers_list.addItem(item)
        else:
            item = QListWidgetItem("Нет наблюдателей")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.observers_list.addItem(item)
        observers_layout.addWidget(self.observers_list)
        content_layout.addWidget(observers_group)
        
        # Теги
        tags_group = QGroupBox("Теги")
        tags_layout = QVBoxLayout(tags_group)
        self.tags_list = QListWidget()
        self.tags_list.setMaximumHeight(100)
        tags = self.task_data.get('tags', [])
        if tags:
            for tag in tags:
                item = QListWidgetItem(tag['name'])
                if tag.get('color'):
                    item.setForeground(QColor(tag['color']))
                self.tags_list.addItem(item)
        else:
            item = QListWidgetItem("Нет тегов")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.tags_list.addItem(item)
        tags_layout.addWidget(self.tags_list)
        content_layout.addWidget(tags_group)
        
        # Комментарии (заглушка)
        comments_group = QGroupBox("Комментарии")
        comments_layout = QVBoxLayout(comments_group)
        comments_placeholder = QLabel("Комментарии пока не реализованы")
        comments_placeholder.setAlignment(Qt.AlignCenter)
        comments_placeholder.setStyleSheet("color: gray;")
        comments_layout.addWidget(comments_placeholder)
        content_layout.addWidget(comments_group)
        
        # Файлы (заглушка)
        files_group = QGroupBox("Файлы")
        files_layout = QVBoxLayout(files_group)
        files_placeholder = QLabel("Файлы пока не реализованы")
        files_placeholder.setAlignment(Qt.AlignCenter)
        files_placeholder.setStyleSheet("color: gray;")
        files_layout.addWidget(files_placeholder)
        content_layout.addWidget(files_group)
        
        # История изменений (заглушка)
        history_group = QGroupBox("История изменений")
        history_layout = QVBoxLayout(history_group)
        history_placeholder = QLabel("История изменений пока не реализована")
        history_placeholder.setAlignment(Qt.AlignCenter)
        history_placeholder.setStyleSheet("color: gray;")
        history_layout.addWidget(history_placeholder)
        content_layout.addWidget(history_group)
        
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)
        
        # Кнопки действий
        buttons_layout = QHBoxLayout()
        
        # Кнопка назад
        back_btn = QPushButton("← Назад")
        back_btn.setObjectName("backButton")
        back_btn.clicked.connect(self.go_back)
        buttons_layout.addWidget(back_btn)
        
        buttons_layout.addStretch()
        
        # Кнопка редактирования (только если пользователь - автор или исполнитель)
        is_author = self.task_data.get('author_id') == self.current_user_id
        is_executor = self.task_data.get('executor_id') == self.current_user_id
        
        if is_author or is_executor:
            self.edit_btn = QPushButton("✏ Редактировать")
            self.edit_btn.setObjectName("editTaskButton")
            self.edit_btn.clicked.connect(self.edit_task)
            buttons_layout.addWidget(self.edit_btn)
        
        # Кнопка удаления (только если пользователь - автор)
        if is_author:
            delete_btn = QPushButton("Удалить")
            delete_btn.setObjectName("deleteTaskButton")
            delete_btn.clicked.connect(self.delete_task)
            buttons_layout.addWidget(delete_btn)
        
        main_layout.addLayout(buttons_layout)
    
    def go_back(self):
        """Вернуться к списку задач."""
        self.backRequested.emit()
    
    def edit_task(self):
        """Открыть диалог редактирования задачи."""
        dialog = TaskEditDialog(self.task_data, self.parent())
        if dialog.exec() == QDialog.Accepted:
            # Обновляем данные задачи после редактирования
            self.task_data = dialog.get_updated_task_data()
            # Эмитим сигнал об обновлении
            self.taskUpdated.emit()
            # Перезагружаем виджет с новыми данными
            self.refresh_data()
    
    def refresh_data(self):
        """Обновить данные задачи."""
        # Получаем свежие данные из БД
        try:
            from db import get_task_detail
            fresh_data = get_task_detail(self.task_data['id'])
            if fresh_data:
                self.task_data = fresh_data
                # Пересоздаём интерфейс с новыми данными
                self.clear_layout(main_layout)
                self.init_ui()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось обновить данные задачи:\n{e}"
            )
    
    def clear_layout(self, layout):
        """Очистить макет от всех виджетов."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
    
    def delete_task(self):
        """Удалить задачу."""
        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            "Вы уверены, что хотите удалить эту задачу?\nЭто действие нельзя отменить.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        from db import delete_task
        success, message = delete_task(self.task_data['id'], self.current_user_id)
        
        if success:
            QMessageBox.information(self, "Успех", message)
            self.taskUpdated.emit()
            self.go_back()
        else:
            QMessageBox.critical(self, "Ошибка", message)


class TaskEditDialog(QDialog):
    """Диалог редактирования задачи."""
    
    def __init__(self, task_data, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.updated_data = dict(task_data)  # Копия данных для сохранения изменений
        self.setWindowTitle(f"Редактирование задачи №{task_data['id']}")
        self.setMinimumSize(700, 600)
        self.init_ui()
        self.load_employees()
        self.load_tags()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Заголовок
        header_label = QLabel(f"Редактирование задачи №{self.task_data['id']}")
        header_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(header_label)
        
        # Основной контент в скролл-области
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)
        
        # Название задачи
        title_group = QGroupBox("Название")
        title_layout = QVBoxLayout(title_group)
        self.title_edit = QLineEdit(self.task_data.get('title', ''))
        self.title_edit.setPlaceholderText("Введите название задачи")
        title_layout.addWidget(self.title_edit)
        content_layout.addWidget(title_group)
        
        # Описание
        desc_group = QGroupBox("Описание")
        desc_layout = QVBoxLayout(desc_group)
        self.description_edit = QTextEdit()
        self.description_edit.setPlainText(self.task_data.get('description', ''))
        self.description_edit.setPlaceholderText("Введите подробное описание задачи")
        self.description_edit.setMinimumHeight(150)
        desc_layout.addWidget(self.description_edit)
        content_layout.addWidget(desc_group)
        
        # Информация (Исполнитель, Статус, Приоритет, Дедлайн)
        info_group = QGroupBox("Параметры задачи")
        info_layout = QFormLayout(info_group)
        
        # Исполнитель
        self.executor_combo = QComboBox()
        info_layout.addRow("Исполнитель:", self.executor_combo)
        
        # Статус
        self.status_combo = QComboBox()
        self.status_combo.addItems(["Новая", "В работе", "На проверке", "Завершена", "Отменена"])
        current_status = self.task_data.get('status', 'Новая')
        status_index = self.status_combo.findText(current_status)
        if status_index >= 0:
            self.status_combo.setCurrentIndex(status_index)
        info_layout.addRow("Статус:", self.status_combo)
        
        # Приоритет
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["Низкий", "Средний", "Критичный", "Блокер"])
        current_priority = self.task_data.get('priority', 'Средний')
        priority_index = self.priority_combo.findText(current_priority)
        if priority_index >= 0:
            self.priority_combo.setCurrentIndex(priority_index)
        info_layout.addRow("Приоритет:", self.priority_combo)
        
        # Дедлайн
        self.deadline_edit = QDateEdit()
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setMinimumDate(QDate.currentDate().addDays(-365))  # Разрешаем прошлые даты
        deadline_val = self.task_data.get('deadline')
        if deadline_val:
            try:
                from datetime import datetime
                if isinstance(deadline_val, str):
                    deadline_date = QDate.fromString(deadline_val, "yyyy-MM-dd")
                else:
                    deadline_date = QDate(deadline_val.year, deadline_val.month, deadline_val.day)
                self.deadline_edit.setDate(deadline_date)
            except:
                self.deadline_edit.setDate(QDate.currentDate())
        else:
            self.deadline_edit.setDate(QDate.currentDate())
        info_layout.addRow("Дедлайн:", self.deadline_edit)
        
        content_layout.addWidget(info_group)
        
        # Наблюдатели
        observers_group = QGroupBox("Наблюдатели")
        observers_layout = QVBoxLayout(observers_group)
        self.observers_list = QListWidget()
        self.observers_list.setSelectionMode(QListWidget.NoSelection)
        observers_layout.addWidget(self.observers_list)
        content_layout.addWidget(observers_group)
        
        # Теги
        tags_group = QGroupBox("Теги")
        tags_layout = QVBoxLayout(tags_group)
        
        self.tags_list = QListWidget()
        self.tags_list.setSelectionMode(QListWidget.MultiSelection)
        tags_layout.addWidget(self.tags_list)
        
        create_tag_layout = QHBoxLayout()
        self.new_tag_edit = QLineEdit()
        self.new_tag_edit.setPlaceholderText("Новый тег")
        create_tag_layout.addWidget(self.new_tag_edit)
        
        create_tag_btn = QPushButton("➕")
        create_tag_btn.setMaximumWidth(40)
        create_tag_btn.clicked.connect(self.create_new_tag)
        create_tag_layout.addWidget(create_tag_btn)
        
        tags_layout.addLayout(create_tag_layout)
        content_layout.addWidget(tags_group)
        
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)
        
        # Кнопки действий
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Сохранить")
        save_btn.setObjectName("saveTaskButton")
        save_btn.clicked.connect(self.save_changes)
        buttons_layout.addWidget(save_btn)
        
        main_layout.addLayout(buttons_layout)
    
    def load_employees(self):
        """Загрузить список сотрудников."""
        try:
            employees = db_get_all_employees_for_selector()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось загрузить сотрудников:\n{e}"
            )
            return
        
        self.executor_combo.clear()
        self.observers_list.clear()
        
        current_executor_name = self.task_data.get('executor_name', '')
        executor_index = -1  # По умолчанию ничего не выбрано
        
        for i, emp in enumerate(employees):
            self.executor_combo.addItem(emp['name'], emp['id'])
            if emp['name'] == current_executor_name:
                executor_index = i
            
            item = QListWidgetItem(emp['name'])
            item.setData(EMPLOYEE_ID_ROLE, emp['id'])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.observers_list.addItem(item)
        
        # Устанавливаем индекс только если исполнитель найден
        if executor_index >= 0:
            self.executor_combo.setCurrentIndex(executor_index)
        
        # Отмечаем текущих наблюдателей
        current_observers = self.task_data.get('observers', [])
        for i in range(self.observers_list.count()):
            item = self.observers_list.item(i)
            if item.text() in current_observers:
                item.setCheckState(Qt.Checked)
    
    def load_tags(self):
        """Загрузить существующие теги."""
        try:
            tags = db_get_all_tags()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось загрузить теги:\n{e}"
            )
            return
        
        self.tags_list.clear()
        
        current_tags = [tag['name'] for tag in self.task_data.get('tags', [])]
        
        for tag in tags:
            item = QListWidgetItem(f"{tag[1]}")
            item.setData(TAG_ID_ROLE, tag[0])
            item.setData(TAG_COLOR_ROLE, tag[2])  # цвет
            
            # Применяем цвет тега
            if tag[2]:
                item.setForeground(QColor(tag[2]))
            
            # Выбираем текущие теги
            if tag[1] in current_tags:
                item.setSelected(True)
            
            self.tags_list.addItem(item)
    
    def create_new_tag(self):
        """Создать новый тег."""
        tag_name = self.new_tag_edit.text().strip()
        if not tag_name:
            QMessageBox.warning(self, "Ошибка", "Введите название тега")
            return
        
        try:
            tag_id = db_create_tag(tag_name)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось создать тег:\n{e}"
            )
            return
        
        if tag_id:
            item = QListWidgetItem(tag_name)
            item.setData(TAG_ID_ROLE, tag_id)
            # Сохраняем цвет (по умолчанию серый)
            item.setData(TAG_COLOR_ROLE, "#808080")
            item.setForeground(QColor("#808080"))
            self.tags_list.addItem(item)
            self.new_tag_edit.clear()
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось создать тег")
    
    def save_changes(self):
        """Сохранить изменения."""
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Ошибка", "Введите название задачи")
            return
        
        description = self.description_edit.toPlainText().strip()
        if len(description) < 10:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Описание слишком короткое (минимум 10 символов)"
            )
            return
        
        executor_id = self.executor_combo.currentData()
        if not executor_id:
            QMessageBox.warning(self, "Ошибка", "Выберите исполнителя")
            return
        
        status = self.status_combo.currentText()
        priority = self.priority_combo.currentText()
        deadline = self.deadline_edit.date().toString("yyyy-MM-dd")
        
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
        
        try:
            success = update_task(
                task_id=self.task_data['id'],
                title=title,
                description=description,
                executor_id=executor_id,
                status=status,
                priority=priority,
                deadline=deadline,
                observers_ids=observers_ids,
                tag_ids=selected_tag_ids
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось обновить задачу:\n{e}"
            )
            return
        
        if success:
            # Обновляем локальные данные
            self.updated_data.update({
                'title': title,
                'description': description,
                'executor_name': self.executor_combo.currentText(),
                'status': status,
                'priority': priority,
                'deadline': deadline,
                'observers': [self.observers_list.item(i).text() 
                             for i in range(self.observers_list.count()) 
                             if self.observers_list.item(i).checkState() == Qt.Checked],
                'tags': [{'name': item.text(), 'color': item.data(TAG_COLOR_ROLE)} 
                        for item in self.tags_list.selectedItems()]
            })
            QMessageBox.information(self, "Успех", "Задача успешно обновлена")
            self.accept()
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось обновить задачу")
    
    def get_updated_task_data(self):
        """Вернуть обновлённые данные задачи."""
        return self.updated_data


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
        title_label.setObjectName("tasksTitleLabel")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        create_btn = QPushButton("➕ Создать задачу")
        create_btn.setObjectName("createTaskButton")
        create_btn.clicked.connect(self.show_creator)
        header_layout.addWidget(create_btn)
        
        list_layout.addLayout(header_layout)
        
        # Фильтры и поиск
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)
        
        # Поиск
        search_label = QLabel("🔎")
        filter_layout.addWidget(search_label)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск...")
        self.search_edit.setMaximumWidth(200)
        self.search_edit.textChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.search_edit)
        
        # Статус
        filter_layout.addWidget(QLabel("Статус:"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("Все", None)
        self.status_filter.addItem("Новая", "Новая")
        self.status_filter.addItem("В работе", "В работе")
        self.status_filter.addItem("На проверке", "На проверке")
        self.status_filter.addItem("Завершена", "Завершена")
        self.status_filter.addItem("Отменена", "Отменена")
        self.status_filter.currentIndexChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.status_filter)
        
        # Приоритет
        filter_layout.addWidget(QLabel("Приоритет:"))
        self.priority_filter = QComboBox()
        self.priority_filter.addItem("Все", None)
        self.priority_filter.addItem("Низкий", "Низкий")
        self.priority_filter.addItem("Средний", "Средний")
        self.priority_filter.addItem("Критичный", "Критичный")
        self.priority_filter.addItem("Блокер", "Блокер")
        self.priority_filter.currentIndexChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.priority_filter)
        
        # Исполнитель
        filter_layout.addWidget(QLabel("Исполнитель:"))
        self.executor_filter = QComboBox()
        self.executor_filter.addItem("Все", None)
        try:
            employees = db_get_all_employees_for_selector()
            for emp in employees:
                self.executor_filter.addItem(emp['name'], emp['id'])
        except:
            pass
        self.executor_filter.currentIndexChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.executor_filter)
        
        # Быстрые фильтры
        filter_layout.addStretch()
        
        self.my_tasks_btn = QPushButton("Мои задачи")
        self.my_tasks_btn.setCheckable(True)
        self.my_tasks_btn.clicked.connect(self.toggle_my_tasks)
        filter_layout.addWidget(self.my_tasks_btn)
        
        # Кнопка обновления
        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.clicked.connect(lambda: self.load_tasks())
        filter_layout.addWidget(refresh_btn)
        
        # Сортировка
        filter_layout.addWidget(QLabel("Сортировать:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("↓ Дедлайн", ("deadline", "ASC"))
        self.sort_combo.addItem("↑ Дедлайн", ("deadline", "DESC"))
        self.sort_combo.addItem("↓ Приоритет", ("priority", "DESC"))
        self.sort_combo.addItem("↑ Приоритет", ("priority", "ASC"))
        self.sort_combo.addItem("↓ Дата создания", ("created_at", "DESC"))
        self.sort_combo.addItem("↑ Дата создания", ("created_at", "ASC"))
        self.sort_combo.currentIndexChanged.connect(self.change_sort)
        filter_layout.addWidget(self.sort_combo)
        
        list_layout.addLayout(filter_layout)
        
        # Список задач
        self.tasks_scroll = QScrollArea()
        self.tasks_scroll.setObjectName("tasksScrollArea")
        self.tasks_scroll.setWidgetResizable(True)
        self.tasks_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
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
        self.creator_widget.backRequested.connect(self.show_list)
        self.stacked_widget.addWidget(self.creator_widget)
        
        # Страница детального просмотра задачи (изначально пустая)
        self.detail_page = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_page)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.stacked_widget.addWidget(self.detail_page)
        
        main_layout.addWidget(self.stacked_widget)
        
        # Сохраняем текущие параметры фильтрации
        self.filter_params = {
            'status': None,
            'priority': None,
            'executor_id': None,
            'search': '',
            'my_tasks_only': False
        }
        self.sort_params = ('created_at', 'DESC')
    
    def show_list(self):
        """Показать список задач."""
        self.stacked_widget.setCurrentWidget(self.list_page)
        self.load_tasks()
    
    def clear_layout(self, layout):
        """Очистить макет от всех виджетов."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
    
    def load_tasks(self):
        """Загрузить список задач."""
        # Очищаем текущий список
        self.clear_layout(self.tasks_layout)
        self.tasks_layout.addStretch()
        
        try:
            tasks = db_get_tasks(
                filter_params=self.filter_params,
                current_user_id=self.current_user_id,
                sort_by=self.sort_params[0],
                sort_order=self.sort_params[1]
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось загрузить задачи:\n{e}"
            )
            return
        
        if not tasks:
            empty_label = QLabel("Нет задач")
            empty_label.setObjectName("emptyTasksLabel")
            empty_label.setAlignment(Qt.AlignCenter)
            self.tasks_layout.insertWidget(0, empty_label)
            return
        
        from datetime import datetime, date
        today = date.today()
        
        for task in tasks:
            task_card = self.create_task_card(task, today)
            self.tasks_layout.insertWidget(self.tasks_layout.count() - 1, task_card)
    
    def apply_filters(self):
        """Применить фильтры и обновить список задач."""
        # Статус
        status_data = self.status_filter.currentData()
        self.filter_params['status'] = status_data
        
        # Приоритет
        priority_data = self.priority_filter.currentData()
        self.filter_params['priority'] = priority_data
        
        # Исполнитель - только если не выбраны "Мои задачи"
        if not self.filter_params.get('my_tasks_only'):
            executor_data = self.executor_filter.currentData()
            self.filter_params['executor_id'] = executor_data
        else:
            self.filter_params['executor_id'] = None
        
        # Поиск по названию, описанию и исполнителю
        self.filter_params['search'] = self.search_edit.text().strip()
        
        self.load_tasks()
    
    def toggle_my_tasks(self):
        """Переключить фильтр 'Мои задачи'."""
        checked = self.my_tasks_btn.isChecked()
        self.my_tasks_btn.setText(
            "Все задачи" if checked else "Мои задачи"
        )
        self.filter_params['my_tasks_only'] = checked
        # Сбрасываем фильтр исполнителя при включении "Мои задачи"
        if checked:
            self.filter_params['executor_id'] = None
            self.executor_filter.setCurrentIndex(0)  # "Все"
        self.apply_filters()
    
    def change_sort(self):
        """Изменить сортировку."""
        self.sort_params = self.sort_combo.currentData()
        self.load_tasks()
    
    def create_task_card(self, task_data, today=None):
        """Создать карточку задачи."""
        from datetime import date
        
        if today is None:
            today = date.today()
        
        card = QFrame()
        card.setObjectName("taskCard")
        
        # Проверяем просроченность
        is_overdue = False
        if task_data['deadline']:
            try:
                deadline_date = date.fromisoformat(str(task_data['deadline']))
                if deadline_date < today and task_data.get('status') not in ['Завершена', 'Отменена']:
                    is_overdue = True
                    card.setStyleSheet("border: 2px solid red; background-color: #fff5f5;")
            except:
                pass
        
        layout = QVBoxLayout(card)
        layout.setSpacing(8)
        
        # Заголовок и статус
        header_layout = QHBoxLayout()
        
        # Номер задачи и название
        task_id_label = QLabel(f"#{task_data['id']}")
        task_id_label.setObjectName("taskIdLabel")
        task_id_label.setStyleSheet("font-weight: bold; color: #666;")
        header_layout.addWidget(task_id_label)
        
        title_label = QLabel(task_data.get('title', 'Без названия'))
        title_label.setObjectName("taskTitleLabel")
        header_layout.addWidget(title_label)
        
        # Статус с индикатором
        status_emoji_map = {
            "Новая": "⚪",
            "В работе": "🟡",
            "На проверке": "🟠",
            "Завершена": "🟢",
            "Отменена": "🔴"
        }
        status = task_data.get('status', 'Новая')
        status_text = f"{status_emoji_map.get(status, '')} {status}"
        status_label = QLabel(status_text)
        status_label.setObjectName("taskStatusLabel")
        header_layout.addWidget(status_label)
        
        # Приоритет
        priority_class_map = {
            "Низкий": "priorityLow",
            "Средний": "priorityMedium",
            "Критичный": "priorityCritical",
            "Блокер": "priorityBlocker"
        }
        priority = task_data.get('priority', 'Средний')
        priority_class = priority_class_map.get(priority, "")
        
        priority_label = QLabel(priority)
        if priority_class:
            priority_label.setObjectName(priority_class)
        header_layout.addWidget(priority_label)
        
        layout.addLayout(header_layout)
        
        # Описание (обрезанное)
        desc = task_data.get('description') or "Нет описания"
        if len(desc) > 150:
            desc = desc[:150] + "..."
        
        desc_label = QLabel(desc)
        desc_label.setObjectName("taskDescriptionLabel")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Информация об исполнителе и дедлайне
        info_layout = QHBoxLayout()
        
        executor_name = task_data.get('executor_name', 'Не назначен')
        executor_label = QLabel(f"👤 {executor_name}")
        executor_label.setObjectName("executorInfoLabel")
        info_layout.addWidget(executor_label)
        
        if task_data.get('deadline'):
            deadline_label = QLabel(f"📅 {task_data['deadline']}")
            deadline_label.setObjectName("deadlineInfoLabel")
            
            # Если просрочено - добавляем метку
            if is_overdue:
                overdue_label = QLabel("🔴 Просрочено")
                overdue_label.setStyleSheet("color: red; font-weight: bold;")
                info_layout.addWidget(deadline_label)
                info_layout.addWidget(overdue_label)
            else:
                info_layout.addWidget(deadline_label)
        
        info_layout.addStretch()
        
        author_name = task_data.get('author_name', 'Неизвестно')
        author_label = QLabel(f"Автор: {author_name}")
        author_label.setObjectName("authorInfoLabel")
        info_layout.addWidget(author_label)
        
        # Кнопка удаления (только если пользователь - автор)
        if task_data.get('author_id') == self.current_user_id:
            delete_btn = QPushButton("Удалить")
            delete_btn.setObjectName("deleteTaskButton")
            delete_btn.setToolTip("Удалить задачу")
            delete_btn.clicked.connect(lambda checked, tid=task_data['id']: self.delete_task(tid))
            info_layout.addWidget(delete_btn)
        
        layout.addLayout(info_layout)
        
        # Делаем карточку кликабельной (кроме кнопки удаления)
        card.mousePressEvent = lambda e: self.open_task_detail(task_data['id'])
        card.setCursor(Qt.PointingHandCursor)
        
        return card
    
    def open_task_detail(self, task_id):
        """Открыть детальную информацию о задаче."""
        try:
            detail = get_task_detail(task_id)
            if detail:
                # Очищаем предыдущий виджет детали
                self.clear_layout(self.detail_layout)
                
                # Создаём новый виджет детали
                self.detail_widget = TaskDetailWidget(detail, self.current_user_id)
                self.detail_widget.taskUpdated.connect(self.load_tasks_and_show_list)
                self.detail_widget.backRequested.connect(self.show_list)
                
                self.detail_layout.addWidget(self.detail_widget)
                self.stacked_widget.setCurrentWidget(self.detail_page)
            else:
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    "Задача не найдена"
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось загрузить задачу:\n{e}"
            )
    
    def load_tasks_and_show_list(self):
        """Загрузить задачи и показать список."""
        self.load_tasks()
        self.show_list()
    
    def delete_task(self, task_id):
        """Удалить задачу (только если пользователь - автор)."""
        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            "Вы уверены, что хотите удалить эту задачу?\nЭто действие нельзя отменить.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        success, message = delete_task(task_id, self.current_user_id)
        
        if success:
            QMessageBox.information(self, "Успех", message)
            self.load_tasks()
        else:
            QMessageBox.critical(self, "Ошибка", message)
    
    def show_creator(self):
        """Показать страницу создания задачи."""
        self.stacked_widget.setCurrentWidget(self.creator_widget)
    
    def on_task_created(self):
        """Обработчик создания задачи."""
        self.load_tasks()
        self.stacked_widget.setCurrentWidget(self.list_page)
