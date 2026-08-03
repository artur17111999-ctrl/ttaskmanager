"""
Модуль для работы с задачами.
Импортируем компоненты из подмодулей tasks/*.
"""

try:
    from .tasks import (
        TaskCreatorWidget,
        TaskDetailView,
        TaskEditDialog,
        TaskDetailWidget,
        TasksWidget,
    )
except ImportError:
    from sticky_crm.tasks import (
        TaskCreatorWidget,
        TaskDetailView,
        TaskEditDialog,
        TaskDetailWidget,
        TasksWidget,
    )

__all__ = [
    'TaskCreatorWidget',
    'TaskDetailView',
    'TaskEditDialog',
    'TaskDetailWidget',
    'TasksWidget',
]
