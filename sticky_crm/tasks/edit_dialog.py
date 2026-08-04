"""
Диалог редактирования задачи.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QTextEdit, QLineEdit, QComboBox, QDateEdit, QListWidget, QListWidgetItem,
    QMessageBox, QFormLayout, QGroupBox
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor

from .base import EMPLOYEE_ID_ROLE, TAG_ID_ROLE, TAG_COLOR_ROLE


class TaskEditDialog(QDialog):
    """Диалог редактирования задачи."""
    
    def __init__(self, task_data, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.updated_data = dict(task_data)
        self.setWindowTitle(f"Редактирование задачи №{task_data['id']}")
        self.setMinimumSize(700, 600)
        self.init_ui()
        self.load_employees()
        self.load_statuses()
        self.load_priorities()
        self.load_tags()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        header_label = QLabel(f"Редактирование задачи №{self.task_data['id']}")
        header_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(header_label)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)
        
        title_group = QGroupBox("Название")
        title_layout = QVBoxLayout(title_group)
        self.title_edit = QLineEdit(self.task_data.get('title', ''))
        self.title_edit.setPlaceholderText("Введите название задачи")
        title_layout.addWidget(self.title_edit)
        content_layout.addWidget(title_group)
        
        short_desc_group = QGroupBox("Краткое описание для стикера")
        short_desc_layout = QVBoxLayout(short_desc_group)
        self.short_description_edit = QLineEdit(self.task_data.get('short_description', ''))
        self.short_description_edit.setPlaceholderText("Введите краткое описание для стикера")
        short_desc_layout.addWidget(self.short_description_edit)
        content_layout.addWidget(short_desc_group)
        
        desc_group = QGroupBox("Описание")
        desc_layout = QVBoxLayout(desc_group)
        self.description_edit = QTextEdit()
        self.description_edit.setPlainText(self.task_data.get('description', ''))
        self.description_edit.setPlaceholderText("Введите подробное описание задачи")
        self.description_edit.setMinimumHeight(150)
        desc_layout.addWidget(self.description_edit)
        content_layout.addWidget(desc_group)
        
        info_group = QGroupBox("Параметры задачи")
        info_layout = QFormLayout(info_group)
        
        self.executor_combo = QComboBox()
        info_layout.addRow("Исполнитель:", self.executor_combo)
        
        self.status_combo = QComboBox()
        self.status_combo.setObjectName("statusCombo")
        info_layout.addRow("Статус:", self.status_combo)
        
        self.priority_combo = QComboBox()
        self.priority_combo.setObjectName("priorityCombo")
        info_layout.addRow("Приоритет:", self.priority_combo)
        
        self.deadline_edit = QDateEdit()
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setMinimumDate(QDate.currentDate().addDays(-365))
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
        
        observers_group = QGroupBox("Наблюдатели")
        observers_layout = QVBoxLayout(observers_group)
        self.observers_list = QListWidget()
        self.observers_list.setSelectionMode(QListWidget.NoSelection)
        observers_layout.addWidget(self.observers_list)
        content_layout.addWidget(observers_group)
        
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
        from db import get_all_employees_for_selector as db_get_all_employees_for_selector
        
        try:
            employees = db_get_all_employees_for_selector()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить сотрудников:\n{e}")
            return
        
        self.executor_combo.clear()
        self.observers_list.clear()
        
        current_executor_name = self.task_data.get('executor_name', '')
        executor_index = -1
        
        for i, emp in enumerate(employees):
            self.executor_combo.addItem(emp['name'], emp['id'])
            if emp['name'] == current_executor_name:
                executor_index = i
            
            item = QListWidgetItem(emp['name'])
            item.setData(EMPLOYEE_ID_ROLE, emp['id'])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.observers_list.addItem(item)
        
        if executor_index >= 0:
            self.executor_combo.setCurrentIndex(executor_index)
        
        current_observers = self.task_data.get('observers', [])
        for i in range(self.observers_list.count()):
            item = self.observers_list.item(i)
            if item.text() in current_observers:
                item.setCheckState(Qt.Checked)
    
    def load_statuses(self):
        """Загрузить список статусов из БД и установить текущий."""
        from db import get_all_statuses as db_get_all_statuses
        
        try:
            statuses = db_get_all_statuses()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить статусы:\n{e}")
            return
        
        self.status_combo.clear()
        
        current_status = self.task_data.get('status', '')
        current_status_code = self.task_data.get('status_code', '')
        selected_index = -1
        
        for i, status in enumerate(statuses):
            self.status_combo.addItem(status[2], status[0])
            if status[1] == current_status_code or status[2] == current_status:
                selected_index = i
        
        if selected_index >= 0:
            self.status_combo.setCurrentIndex(selected_index)
    
    def load_priorities(self):
        """Загрузить список приоритетов из БД и установить текущий."""
        from db import get_all_priorities as db_get_all_priorities
        
        try:
            priorities = db_get_all_priorities()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить приоритеты:\n{e}")
            return
        
        self.priority_combo.clear()
        
        current_priority = self.task_data.get('priority', '')
        current_priority_code = self.task_data.get('priority_code', '')
        selected_index = -1
        
        for i, priority in enumerate(priorities):
            self.priority_combo.addItem(priority[2], priority[0])
            if priority[1] == current_priority_code or priority[2] == current_priority:
                selected_index = i
        
        if selected_index >= 0:
            self.priority_combo.setCurrentIndex(selected_index)
    
    def load_tags(self):
        """Загрузить теги из БД и выбрать текущие."""
        from db import get_all_tags as db_get_all_tags
        
        try:
            tags = db_get_all_tags()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить теги:\n{e}")
            return
        
        self.tags_list.clear()
        
        current_tags = [tag['name'] for tag in self.task_data.get('tags', [])]
        
        for tag in tags:
            item = QListWidgetItem(f"{tag[1]}")
            item.setData(TAG_ID_ROLE, tag[0])
            item.setData(TAG_COLOR_ROLE, tag[2])
            
            if tag[2]:
                item.setForeground(QColor(tag[2]))
            
            if tag[1] in current_tags:
                item.setSelected(True)
            
            self.tags_list.addItem(item)
    
    def create_new_tag(self):
        """Создать новый тег."""
        from db import create_tag as db_create_tag
        
        tag_name = self.new_tag_edit.text().strip()
        if not tag_name:
            QMessageBox.warning(self, "Ошибка", "Введите название тега")
            return
        
        try:
            tag_id = db_create_tag(tag_name)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать тег:\n{e}")
            return
        
        if tag_id:
            item = QListWidgetItem(tag_name)
            item.setData(TAG_ID_ROLE, tag_id)
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
            QMessageBox.warning(self, "Ошибка", "Описание слишком короткое (минимум 10 символов)")
            return
        
        executor_id = self.executor_combo.currentData()
        if not executor_id:
            QMessageBox.warning(self, "Ошибка", "Выберите исполнителя")
            return
        
        status_id = self.status_combo.currentData()
        priority_id = self.priority_combo.currentData()
        deadline = self.deadline_edit.date().toString("yyyy-MM-dd")
        
        observers_ids = []
        for i in range(self.observers_list.count()):
            item = self.observers_list.item(i)
            if item.checkState() == Qt.Checked:
                observers_ids.append(item.data(EMPLOYEE_ID_ROLE))
        
        selected_tag_ids = []
        for item in self.tags_list.selectedItems():
            selected_tag_ids.append(item.data(TAG_ID_ROLE))
        
        from db import update_task
        
        try:
            success = update_task(
                task_id=self.task_data['id'],
                title=title,
                short_description=self.short_description_edit.text().strip(),
                description=description,
                executor_id=executor_id,
                status=None,
                priority=None,
                deadline=deadline,
                observers_ids=observers_ids,
                tag_ids=selected_tag_ids,
                status_id=status_id,
                priority_id=priority_id
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось обновить задачу:\n{e}")
            return
        
        if success:
            self.updated_data.update({
                'title': title,
                'description': description,
                'executor_name': self.executor_combo.currentText(),
                'status': self.status_combo.currentText(),
                'status_code': self.status_combo.currentData(),
                'priority': self.priority_combo.currentText(),
                'priority_code': self.priority_combo.currentData(),
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
