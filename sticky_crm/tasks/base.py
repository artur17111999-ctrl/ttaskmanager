"""
Базовый класс и общие утилиты для виджетов задач.
"""

from PySide6.QtWidgets import QWidget, QMessageBox
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


# Константы для ролей данных (общие для всех виджетов)
TAG_COLOR_ROLE = Qt.UserRole + 1
EMPLOYEE_ID_ROLE = Qt.UserRole
TAG_ID_ROLE = Qt.UserRole + 2
STATUS_ID_ROLE = Qt.UserRole + 3
PRIORITY_ID_ROLE = Qt.UserRole + 4


class TaskBaseWidget(QWidget):
    """Базовый класс для всех виджетов задач с общими методами."""
    
    def __init__(self, current_user_id, current_user_name):
        super().__init__()
        self.current_user_id = current_user_id
        self.current_user_name = current_user_name
    
    def load_statuses_from_db(self, combo_box):
        """Загрузить список статусов из БД в ComboBox."""
        from db import get_all_statuses as db_get_all_statuses
        
        try:
            statuses = db_get_all_statuses()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось загрузить статусы:\n{e}"
            )
            return False
        
        combo_box.clear()
        
        for status in statuses:
            # status: (id, code, title, color, sort_order)
            combo_box.addItem(status[2], status[0])  # title, id
        
        return True
    
    def load_priorities_from_db(self, combo_box):
        """Загрузить список приоритетов из БД в ComboBox."""
        from db import get_all_priorities as db_get_all_priorities
        
        try:
            priorities = db_get_all_priorities()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось загрузить приоритеты:\n{e}"
            )
            return False
        
        combo_box.clear()
        
        for priority in priorities:
            # priority: (id, code, title, color, sort_order)
            combo_box.addItem(priority[2], priority[0])  # title, id
        
        return True
    
    def set_status_from_data(self, combo_box, task_data):
        """Установить текущий статус в ComboBox на основе данных задачи."""
        current_status = task_data.get('status', '')
        current_status_code = task_data.get('status_code', '')
        
        for i in range(combo_box.count()):
            status_id = combo_box.itemData(i)
            status_title = combo_box.itemText(i)
            
            # Получаем код статуса из БД для сравнения
            from db import get_all_statuses
            statuses = get_all_statuses()
            for status in statuses:
                if status[0] == status_id:
                    if status[1] == current_status_code or status[2] == current_status:
                        combo_box.setCurrentIndex(i)
                        return
    
    def set_priority_from_data(self, combo_box, task_data):
        """Установить текущий приоритет в ComboBox на основе данных задачи."""
        current_priority = task_data.get('priority', '')
        current_priority_code = task_data.get('priority_code', '')
        
        for i in range(combo_box.count()):
            priority_id = combo_box.itemData(i)
            priority_title = combo_box.itemText(i)
            
            # Получаем код приоритета из БД для сравнения
            from db import get_all_priorities
            priorities = get_all_priorities()
            for priority in priorities:
                if priority[0] == priority_id:
                    if priority[1] == current_priority_code or priority[2] == current_priority:
                        combo_box.setCurrentIndex(i)
                        return
    
    def load_tags_from_db(self, list_widget, selected_tag_names=None):
        """Загрузить список тегов из БД в ListWidget."""
        from db import get_all_tags as db_get_all_tags
        
        try:
            tags = db_get_all_tags()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось загрузить теги:\n{e}"
            )
            return False
        
        list_widget.clear()
        selected_tag_names = selected_tag_names or []
        
        for tag in tags:
            item = QListWidgetItem(f"{tag[1]}")
            item.setData(TAG_ID_ROLE, tag[0])
            item.setData(TAG_COLOR_ROLE, tag[2])  # цвет
            
            # Применяем цвет тега
            if tag[2]:
                item.setForeground(QColor(tag[2]))
            
            # Выбираем текущие теги
            if tag[1] in selected_tag_names:
                item.setSelected(True)
            
            list_widget.addItem(item)
        
        return True
    
    def create_tag(self, tag_name):
        """Создать новый тег в БД."""
        from db import create_tag as db_create_tag
        
        if not tag_name.strip():
            QMessageBox.warning(self, "Ошибка", "Введите название тега")
            return None
        
        try:
            tag_id = db_create_tag(tag_name)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось создать тег:\n{e}"
            )
            return None
        
        return tag_id
