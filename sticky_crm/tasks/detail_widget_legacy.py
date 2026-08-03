"""
Виджет детального просмотра задачи (для обратной совместимости).
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QTextEdit, QListWidget, QListWidgetItem, QGroupBox, QFormLayout, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class TaskDetailWidget(QDialog):
    """Виджет детального просмотра задачи (для обратной совместимости)."""
    
    taskUpdated = Signal()
    
    def __init__(self, task_data, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.setWindowTitle(f"Задача №{task_data['id']}")
        self.setMinimumSize(700, 600)
        self.init_ui()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        header_label = QLabel(f"Задача №{self.task_data['id']}")
        header_label.setObjectName("taskDetailHeaderLabel")
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
        title_label = QLabel(self.task_data.get('title', 'N/A'))
        title_label.setWordWrap(True)
        title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        title_layout.addWidget(title_label)
        content_layout.addWidget(title_group)
        
        desc_group = QGroupBox("Описание")
        desc_layout = QVBoxLayout(desc_group)
        desc_text = QTextEdit()
        desc_text.setPlainText(self.task_data.get('description', 'N/A'))
        desc_text.setReadOnly(True)
        desc_text.setMinimumHeight(150)
        desc_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        desc_layout.addWidget(desc_text)
        content_layout.addWidget(desc_group)
        
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
        
        comments_group = QGroupBox("Комментарии")
        comments_layout = QVBoxLayout(comments_group)
        comments_placeholder = QLabel("Комментарии пока не реализованы")
        comments_placeholder.setAlignment(Qt.AlignCenter)
        comments_placeholder.setStyleSheet("color: gray;")
        comments_layout.addWidget(comments_placeholder)
        content_layout.addWidget(comments_group)
        
        files_group = QGroupBox("Файлы")
        files_layout = QVBoxLayout(files_group)
        files_placeholder = QLabel("Файлы пока не реализованы")
        files_placeholder.setAlignment(Qt.AlignCenter)
        files_placeholder.setStyleSheet("color: gray;")
        files_layout.addWidget(files_placeholder)
        content_layout.addWidget(files_group)
        
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
        
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.edit_btn = QPushButton("✏ Редактировать")
        self.edit_btn.setObjectName("editTaskButton")
        self.edit_btn.clicked.connect(self.edit_task)
        buttons_layout.addWidget(self.edit_btn)
        
        close_btn = QPushButton("Закрыть")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.accept)
        buttons_layout.addWidget(close_btn)
        main_layout.addLayout(buttons_layout)
    
    def edit_task(self):
        """Открыть диалог редактирования задачи."""
        from .edit_dialog import TaskEditDialog
        
        dialog = TaskEditDialog(self.task_data, self.parent())
        if dialog.exec() == QDialog.Accepted:
            self.task_data = dialog.get_updated_task_data()
            self.taskUpdated.emit()
            self.accept()
