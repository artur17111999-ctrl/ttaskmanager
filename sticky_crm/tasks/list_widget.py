"""
Основной виджет списка задач.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QStackedWidget, QLineEdit, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt, QDate, Signal
from PySide6.QtGui import QColor, QCursor

from .creator import TaskCreatorWidget
from .detail_view import TaskDetailView


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
        
        self.stacked_widget = QStackedWidget()
        
        self.list_page = QWidget()
        list_layout = QVBoxLayout(self.list_page)
        list_layout.setContentsMargins(20, 20, 20, 20)
        list_layout.setSpacing(15)
        
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
        
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)
        
        search_label = QLabel("🔎")
        filter_layout.addWidget(search_label)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск...")
        self.search_edit.setMaximumWidth(200)
        self.search_edit.textChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.search_edit)
        
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
        
        filter_layout.addWidget(QLabel("Приоритет:"))
        self.priority_filter = QComboBox()
        self.priority_filter.addItem("Все", None)
        self.priority_filter.addItem("Низкий", "Низкий")
        self.priority_filter.addItem("Средний", "Средний")
        self.priority_filter.addItem("Критичный", "Критичный")
        self.priority_filter.addItem("Блокер", "Блокер")
        self.priority_filter.currentIndexChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.priority_filter)
        
        filter_layout.addWidget(QLabel("Исполнитель:"))
        self.executor_filter = QComboBox()
        self.executor_filter.addItem("Все", None)
        try:
            from db import get_all_employees_for_selector
            employees = get_all_employees_for_selector()
            for emp in employees:
                self.executor_filter.addItem(emp['name'], emp['id'])
        except:
            pass
        self.executor_filter.currentIndexChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.executor_filter)
        
        filter_layout.addStretch()
        
        self.my_tasks_btn = QPushButton("Мои задачи")
        self.my_tasks_btn.setCheckable(True)
        self.my_tasks_btn.clicked.connect(self.toggle_my_tasks)
        filter_layout.addWidget(self.my_tasks_btn)
        
        refresh_btn = QPushButton("🔄 Обновить")
        refresh_btn.clicked.connect(lambda: self.load_tasks())
        filter_layout.addWidget(refresh_btn)
        
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
        
        self.creator_widget = TaskCreatorWidget(self.current_user_id, self.current_user_name)
        self.creator_widget.taskCreated.connect(self.on_task_created)
        self.creator_widget.backRequested.connect(self.show_list)
        self.stacked_widget.addWidget(self.creator_widget)
        
        self.detail_widget = None
        
        main_layout.addWidget(self.stacked_widget)
        
        self.filter_params = {
            'status': None,
            'priority': None,
            'executor_id': None,
            'search': '',
            'my_tasks_only': False
        }
        self.sort_params = ('created_at', 'DESC')
    
    def show_list(self):
        self.stacked_widget.setCurrentWidget(self.list_page)
        self.load_tasks()
    
    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
    
    def load_tasks(self):
        from db import get_tasks as db_get_tasks
        
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
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить задачи:\n{e}")
            return
        
        if not tasks:
            empty_label = QLabel("Нет задач")
            empty_label.setObjectName("emptyTasksLabel")
            empty_label.setAlignment(Qt.AlignCenter)
            self.tasks_layout.insertWidget(0, empty_label)
            return
        
        from datetime import date
        today = date.today()
        
        for task in tasks:
            task_card = self.create_task_card(task, today)
            self.tasks_layout.insertWidget(self.tasks_layout.count() - 1, task_card)
    
    def apply_filters(self):
        status_data = self.status_filter.currentData()
        self.filter_params['status'] = status_data
        
        priority_data = self.priority_filter.currentData()
        self.filter_params['priority'] = priority_data
        
        if not self.filter_params.get('my_tasks_only'):
            executor_data = self.executor_filter.currentData()
            self.filter_params['executor_id'] = executor_data
        else:
            self.filter_params['executor_id'] = None
        
        self.filter_params['search'] = self.search_edit.text().strip()
        self.load_tasks()
    
    def toggle_my_tasks(self):
        checked = self.my_tasks_btn.isChecked()
        self.my_tasks_btn.setText(
            "Все задачи" if checked else "Мои задачи"
        )
        self.filter_params['my_tasks_only'] = checked
        if checked:
            self.filter_params['executor_id'] = None
            self.executor_filter.setCurrentIndex(0)
        self.apply_filters()
    
    def change_sort(self):
        self.sort_params = self.sort_combo.currentData()
        self.load_tasks()
    
    def create_task_card(self, task_data, today=None):
        from datetime import date
        
        if today is None:
            today = date.today()
        
        card = QFrame()
        card.setObjectName("taskCard")
        
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
        layout.setSpacing(7)
        layout.setContentsMargins(16, 13, 16, 13)
        
        header_layout = QHBoxLayout()
        
        task_id_label = QLabel(f"#{task_data['id']}")
        task_id_label.setObjectName("taskIdLabel")
        task_id_label.setStyleSheet("font-weight: bold; color: #666;")
        header_layout.addWidget(task_id_label)
        
        title_label = QLabel(task_data.get('title', 'Без названия'))
        title_label.setObjectName("taskTitleLabel")
        header_layout.addWidget(title_label)
        
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
        header_layout.addStretch()
        
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
        
        desc = task_data.get('description') or "Нет описания"
        if len(desc) > 150:
            desc = desc[:150] + "..."
        
        desc_label = QLabel(desc)
        desc_label.setObjectName("taskDescriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setVisible(False)
        layout.addWidget(desc_label)
        
        info_layout = QHBoxLayout()
        
        executor_name = task_data.get('executor_name', 'Не назначен')
        executor_label = QLabel(f"👤 {executor_name}")
        executor_label.setObjectName("executorInfoLabel")
        info_layout.addWidget(executor_label)
        
        if task_data.get('deadline'):
            deadline_label = QLabel(f"📅 {task_data['deadline']}")
            deadline_label.setObjectName("deadlineInfoLabel")
            
            if is_overdue:
                overdue_label = QLabel("🔴 Просрочено")
                overdue_label.setStyleSheet("color: red; font-weight: bold;")
                info_layout.addWidget(deadline_label)
                info_layout.addWidget(overdue_label)
            else:
                info_layout.addWidget(deadline_label)
        
        tags = task_data.get('tags') or []
        if tags:
            tags_label = QLabel("  ".join(f"#{tag['name']}" for tag in tags[:3]))
            tags_label.setObjectName("taskTagsLabel")
            info_layout.addWidget(tags_label)

        info_layout.addStretch()
        
        author_name = task_data.get('author_name', 'Неизвестно')
        author_label = QLabel(f"Автор: {author_name}")
        author_label.setObjectName("authorInfoLabel")
        author_label.setVisible(False)
        info_layout.addWidget(author_label)
        
        if task_data.get('author_id') == self.current_user_id:
            delete_btn = QPushButton("Удалить")
            delete_btn.setObjectName("deleteTaskButton")
            delete_btn.setToolTip("Удалить задачу")
            delete_btn.clicked.connect(lambda checked, tid=task_data['id']: self.delete_task(tid))
            info_layout.addWidget(delete_btn)
        
        layout.addLayout(info_layout)
        
        card.mousePressEvent = lambda e: self.open_task(task_data['id'])
        card.setCursor(QCursor(Qt.PointingHandCursor))
        
        return card
    
    def open_task(self, task_id):
        self.detail_widget = TaskDetailView(task_id, self.current_user_id, self.current_user_name)
        self.detail_widget.taskUpdated.connect(self.on_task_updated)
        self.detail_widget.backRequested.connect(self.show_list)
        
        self.stacked_widget.addWidget(self.detail_widget)
        self.stacked_widget.setCurrentWidget(self.detail_widget)
    
    def on_task_updated(self):
        self.load_tasks()
        self.show_list()
    
    def delete_task(self, task_id):
        from db import delete_task
        
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
        self.stacked_widget.setCurrentWidget(self.creator_widget)
    
    def on_task_created(self):
        self.load_tasks()
        self.stacked_widget.setCurrentWidget(self.list_page)
