"""
Модуль для работы с задачами.
Разбиение большого tasks_widget.py на отдельные компоненты.
"""

from .creator import TaskCreatorWidget
from .detail_view import TaskDetailView
from .edit_dialog import TaskEditDialog
from .detail_widget_legacy import TaskDetailWidget
from .list_widget import TasksWidget

__all__ = [
    'TaskCreatorWidget',
    'TaskDetailView',
    'TaskEditDialog',
    'TaskDetailWidget',
    'TasksWidget',
]
