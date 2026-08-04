"""
Виджет детального просмотра задачи с комментариями.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QTextEdit, QLineEdit, QComboBox, QDateEdit, QListWidget, QListWidgetItem,
    QMessageBox, QFormLayout, QGroupBox, QFrame, QSizePolicy, QMenu, QApplication, QDialog, QCompleter, QInputDialog
)
from PySide6.QtCore import Qt, QDate, Signal
from PySide6.QtGui import QColor, QClipboard

from screenshot_attachments import ScreenshotTextEdit, ScreenshotPreview, add_image_previews
from .base import EMPLOYEE_ID_ROLE, TAG_ID_ROLE, TAG_COLOR_ROLE
from sticky_notes import open_sticky


class TaskDetailView(QWidget):
    """Виджет детального просмотра задачи."""
    
    taskUpdated = Signal()
    backRequested = Signal()
    
    def __init__(self, task_id, current_user_id, current_user_name):
        super().__init__()
        self.task_id = task_id
        self.current_user_id = current_user_id
        self.current_user_name = current_user_name
        self.task_data = None
        self.init_ui()
        self.load_task_data()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        header_layout = QHBoxLayout()
        back_btn = QPushButton("← Назад")
        back_btn.setObjectName("backButton")
        header_layout.addWidget(back_btn)
        back_btn.clicked.connect(self.go_back)
        header_layout.addStretch()
        
        self.header_label = QLabel("Задача")
        self.header_label.setObjectName("taskHeaderLabel")
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()
        
        empty_spacer = QLabel("")
        empty_spacer.setMinimumWidth(100)
        header_layout.addWidget(empty_spacer)
        main_layout.addLayout(header_layout)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)
        
        title_group = QGroupBox("Название")
        title_layout = QVBoxLayout(title_group)
        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("titleEdit")
        self.title_edit.setPlaceholderText("Введите название задачи")
        title_layout.addWidget(self.title_edit)
        content_layout.addWidget(title_group)
        
        short_desc_group = QGroupBox("Краткое описание для стикера")
        short_desc_layout = QVBoxLayout(short_desc_group)
        self.short_description_edit = QLineEdit()
        self.short_description_edit.setObjectName("shortDescriptionEdit")
        self.short_description_edit.setPlaceholderText("Введите краткое описание для стикера")
        short_desc_layout.addWidget(self.short_description_edit)
        self.short_sticky_button = QPushButton("Создать стик")
        self.short_sticky_button.clicked.connect(self.create_short_description_sticky)
        short_desc_layout.addWidget(self.short_sticky_button)
        content_layout.addWidget(short_desc_group)

        desc_group = QGroupBox("Описание")
        desc_layout = QVBoxLayout(desc_group)
        self.desc_text = ScreenshotTextEdit()
        self.desc_text.setObjectName("descriptionEdit")
        self.desc_text.setPlaceholderText("Введите подробное описание задачи")
        self.desc_text.setMinimumHeight(150)
        self.desc_text.setTextInteractionFlags(Qt.TextEditorInteraction)
        desc_layout.addWidget(self.desc_text)
        desc_layout.addWidget(ScreenshotPreview(self.desc_text))
        self.task_images_widget = QWidget()
        self.task_images_layout = QVBoxLayout(self.task_images_widget)
        self.task_images_layout.setContentsMargins(0, 8, 0, 0)
        self.task_images_layout.setSpacing(6)
        self.task_images_label = QLabel("Прикреплённые скриншоты")
        self.task_images_label.setObjectName("attachmentSectionLabel")
        self.task_images_layout.addWidget(self.task_images_label)
        desc_layout.addWidget(self.task_images_widget)
        content_layout.addWidget(desc_group)
        
        info_group = QGroupBox("Информация")
        info_layout = QFormLayout(info_group)
        
        self.author_label_val = QLabel("")
        info_layout.addRow("Автор:", self.author_label_val)
        
        self.executor_combo = QComboBox()
        self.executor_combo.setObjectName("executorCombo")
        self.executor_combo.setEditable(True)
        self.executor_combo.setInsertPolicy(QComboBox.NoInsert)
        self.executor_combo.lineEdit().setPlaceholderText("Начните вводить ФИО")
        info_layout.addRow("Исполнитель:", self.executor_combo)
        
        self.status_combo = QComboBox()
        self.status_combo.setObjectName("statusCombo")
        info_layout.addRow("Статус:", self.status_combo)
        
        self.priority_combo = QComboBox()
        self.priority_combo.setObjectName("priorityCombo")
        info_layout.addRow("Приоритет:", self.priority_combo)
        
        self.deadline_edit = QDateEdit()
        self.deadline_edit.setObjectName("deadlineEdit")
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setMinimumDate(QDate.currentDate().addDays(-365))
        info_layout.addRow("Дедлайн:", self.deadline_edit)
        
        self.created_at_label_val = QLabel("")
        info_layout.addRow("Создана:", self.created_at_label_val)
        content_layout.addWidget(info_group)
        
        self.observers_group = QGroupBox("Наблюдатели")
        observers_layout = QVBoxLayout(self.observers_group)
        self.observers_list = QListWidget()
        self.observers_list.setMaximumHeight(100)
        self.observers_search = QLineEdit()
        self.observers_search.setObjectName("selectionSearchEdit")
        self.observers_search.setPlaceholderText("Поиск по ФИО наблюдателя")
        self.observers_search.textChanged.connect(self.filter_observers)
        observers_layout.addWidget(self.observers_search)
        observers_layout.addWidget(self.observers_list)
        content_layout.addWidget(self.observers_group)
        
        self.tags_group = QGroupBox("Теги")
        tags_layout = QVBoxLayout(self.tags_group)
        self.tags_list = QListWidget()
        self.tags_list.setSelectionMode(QListWidget.NoSelection)
        self.tags_list.setMaximumHeight(100)
        self.tags_search = QLineEdit()
        self.tags_search.setObjectName("selectionSearchEdit")
        self.tags_search.setPlaceholderText("Поиск тегов")
        self.tags_search.textChanged.connect(self.filter_tags)
        tags_layout.addWidget(self.tags_search)
        tags_layout.addWidget(self.tags_list)
        
        tags_buttons_layout = QHBoxLayout()
        self.new_tag_edit = QLineEdit()
        self.new_tag_edit.setObjectName("newTagEdit")
        self.new_tag_edit.setPlaceholderText("Новый тег")
        tags_buttons_layout.addWidget(self.new_tag_edit)
        
        create_tag_btn = QPushButton("➕")
        create_tag_btn.setObjectName("createTagButton")
        create_tag_btn.setMaximumWidth(40)
        create_tag_btn.clicked.connect(self.create_new_tag)
        tags_buttons_layout.addWidget(create_tag_btn)
        tags_layout.addLayout(tags_buttons_layout)
        content_layout.addWidget(self.tags_group)
        
        comment_input_group = QGroupBox("Добавить комментарий")
        comment_input_group.setObjectName("commentInputGroup")
        comment_input_layout = QVBoxLayout(comment_input_group)
        comment_input_layout.setContentsMargins(10, 10, 10, 10)
        
        comment_bottom = QHBoxLayout()
        self.comment_edit = ScreenshotTextEdit()
        self.comment_edit.setObjectName("commentEdit")
        self.comment_edit.setPlaceholderText("Написать комментарий...")
        self.comment_edit.setMinimumHeight(70)
        comment_bottom.addWidget(self.comment_edit, stretch=1)
        
        send_comment_btn = QPushButton("Отправить")
        send_comment_btn.setObjectName("sendCommentButton")
        send_comment_btn.clicked.connect(self.send_comment)
        comment_bottom.addWidget(send_comment_btn)
        comment_input_layout.addWidget(ScreenshotPreview(self.comment_edit))
        comment_input_layout.addLayout(comment_bottom)
        content_layout.addWidget(comment_input_group)
        
        comments_group = QGroupBox("Комментарии")
        comments_group.setObjectName("commentsGroup")
        comments_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        comments_layout = QVBoxLayout(comments_group)
        comments_layout.setContentsMargins(10, 10, 10, 10)
        comments_layout.setSpacing(10)
        
        self.comments_container = QWidget()
        self.comments_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.comments_container_layout = QVBoxLayout(self.comments_container)
        self.comments_container_layout.setContentsMargins(0, 0, 0, 0)
        self.comments_container_layout.setSpacing(8)
        comments_layout.addWidget(self.comments_container, 1)
        content_layout.addWidget(comments_group, stretch=1)
        
        content_layout.addStretch()
        self.scroll_area.setWidget(content_widget)
        main_layout.addWidget(self.scroll_area)
        
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.save_btn = QPushButton("Сохранить")
        self.save_btn.setObjectName("saveTaskButton")
        self.save_btn.clicked.connect(self.save_task)
        buttons_layout.addWidget(self.save_btn)
        
        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.setObjectName("deleteTaskButton")
        self.delete_btn.clicked.connect(self.confirm_delete)
        buttons_layout.addWidget(self.delete_btn)
        main_layout.addLayout(buttons_layout)
    
    def load_task_data(self):
        from db import get_task_detail
        
        try:
            detail = get_task_detail(self.task_id)
            if detail:
                self.task_data = detail
                self.update_ui()
            else:
                QMessageBox.warning(self, "Ошибка", "Задача не найдена")
                self.go_back()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить задачу:\n{e}")
    
    def update_ui(self):
        if not self.task_data:
            return
        
        self.header_label.setText(f"Задача №{self.task_data['id']}")
        self.title_edit.setText(self.task_data.get('title', 'N/A'))
        self.short_description_edit.setText(self.task_data.get('short_description', ''))
        self.desc_text.setPlainText(self.task_data.get('description', 'N/A'))
        self.author_label_val.setText(self.task_data.get('author_name', 'N/A'))
        
        self.load_employees()
        self.load_statuses()
        self.load_priorities()
        
        deadline_val = self.task_data.get('deadline')
        if deadline_val:
            try:
                if isinstance(deadline_val, str):
                    deadline_date = QDate.fromString(deadline_val, "yyyy-MM-dd")
                else:
                    deadline_date = QDate(deadline_val.year, deadline_val.month, deadline_val.day)
                self.deadline_edit.setDate(deadline_date)
            except:
                self.deadline_edit.setDate(QDate.currentDate())
        else:
            self.deadline_edit.setDate(QDate.currentDate())
        
        self.created_at_label_val.setText(
            str(self.task_data.get('created_at', 'N/A'))[:19] 
            if self.task_data.get('created_at') else 'N/A'
        )
        
        self.load_tags()
        self.load_task_images()
        self.load_comments()
        
        is_author = self.task_data.get('author_id') == self.current_user_id
        self.delete_btn.setVisible(is_author)

    def load_task_images(self):
        """Show screenshots pasted when the task was created."""
        from db import get_image_attachments

        while self.task_images_layout.count() > 1:
            layout_item = self.task_images_layout.takeAt(1)
            widget = layout_item.widget()
            if widget is not None:
                widget.deleteLater()
        try:
            images = get_image_attachments('task', self.task_id)
        except Exception as error:
            print(f"Не удалось загрузить скриншоты задачи: {error}")
            images = []
        self.task_images_widget.setVisible(bool(images))
        if images:
            add_image_previews(self.task_images_layout, images)

    def go_back(self):
        """Return to the task list."""
        self.backRequested.emit()

    def load_employees(self):
        from db import get_all_employees_for_selector
        try:
            employees = get_all_employees_for_selector()
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить сотрудников:\n{error}")
            return

        self.executor_combo.clear()
        completer = QCompleter(self.executor_combo.model(), self.executor_combo)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.executor_combo.setCompleter(completer)
        self.observers_list.clear()
        executor_name = self.task_data.get('executor_name', '')
        observer_names = set(self.task_data.get('observers', []))
        for index, employee in enumerate(employees):
            self.executor_combo.addItem(employee['name'], employee['id'])
            if employee['name'] == executor_name:
                self.executor_combo.setCurrentIndex(index)
            item = QListWidgetItem(employee['name'])
            item.setData(EMPLOYEE_ID_ROLE, employee['id'])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if employee['name'] in observer_names else Qt.Unchecked)
            self.observers_list.addItem(item)

    def filter_observers(self, text):
        query = text.strip().casefold()
        for index in range(self.observers_list.count()):
            item = self.observers_list.item(index)
            item.setHidden(bool(query) and query not in item.text().casefold())

    def load_statuses(self):
        from db import get_all_statuses
        try:
            statuses = get_all_statuses()
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить статусы:\n{error}")
            return

        self.status_combo.clear()
        for index, status in enumerate(statuses):
            self.status_combo.addItem(status[2], status[0])
            if status[1] == self.task_data.get('status_code') or status[2] == self.task_data.get('status'):
                self.status_combo.setCurrentIndex(index)

    def load_priorities(self):
        from db import get_all_priorities
        try:
            priorities = get_all_priorities()
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить приоритеты:\n{error}")
            return

        self.priority_combo.clear()
        for index, priority in enumerate(priorities):
            self.priority_combo.addItem(priority[2], priority[0])
            if priority[1] == self.task_data.get('priority_code') or priority[2] == self.task_data.get('priority'):
                self.priority_combo.setCurrentIndex(index)

    def load_tags(self):
        from db import get_all_tags
        try:
            tags = get_all_tags()
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить теги:\n{error}")
            return

        selected_names = {tag['name'] for tag in self.task_data.get('tags', [])}
        self.tags_list.clear()
        for tag_id, name, color in tags:
            item = QListWidgetItem(name)
            item.setData(TAG_ID_ROLE, tag_id)
            item.setData(TAG_COLOR_ROLE, color)
            if color:
                item.setForeground(QColor(color))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in selected_names else Qt.Unchecked)
            self.tags_list.addItem(item)

    def filter_tags(self, text):
        query = text.strip().casefold()
        for index in range(self.tags_list.count()):
            item = self.tags_list.item(index)
            item.setHidden(bool(query) and query not in item.text().casefold())

    def create_new_tag(self):
        from db import create_tag
        name = self.new_tag_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название тега")
            return
        try:
            tag_id = create_tag(name)
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать тег:\n{error}")
            return
        if not tag_id:
            QMessageBox.warning(self, "Ошибка", "Не удалось создать тег")
            return

        item = QListWidgetItem(name)
        item.setData(TAG_ID_ROLE, tag_id)
        item.setData(TAG_COLOR_ROLE, "#808080")
        item.setForeground(QColor("#808080"))
        self.tags_list.addItem(item)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.new_tag_edit.clear()

    def load_comments(self):
        from db import get_task_comments, get_image_attachments
        while self.comments_container_layout.count():
            layout_item = self.comments_container_layout.takeAt(0)
            widget = layout_item.widget()
            if widget is not None:
                widget.deleteLater()
        try:
            comments = get_task_comments(self.task_id)
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить комментарии:\n{error}")
            return

        if not comments:
            empty_label = QLabel("Комментариев пока нет")
            empty_label.setAlignment(Qt.AlignCenter)
            self.comments_container_layout.addWidget(empty_label)
            return
        for comment in comments:
            card = QFrame()
            card.setObjectName("commentCard")
            card.setContextMenuPolicy(Qt.CustomContextMenu)
            card.customContextMenuRequested.connect(lambda _pos, item=comment, widget=card: self._comment_menu(widget, item))
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            author_label = QLabel(f"{comment['author_name']} · {comment['created_at']}")
            author_label.setObjectName("commentAuthorLabel")
            text_label = QLabel(comment['text'])
            text_label.setWordWrap(True)
            text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            text_label.setContextMenuPolicy(Qt.CustomContextMenu)
            text_label.customContextMenuRequested.connect(lambda _pos, item=comment, widget=card: self._comment_menu(widget, item))
            card_layout.addWidget(author_label)
            card_layout.addWidget(text_label)
            if comment['author_id'] == self.current_user_id:
                actions = QHBoxLayout()
                edit_button = QPushButton("Редактировать")
                delete_button = QPushButton("Удалить")
                edit_button.setObjectName("commentActionButton")
                delete_button.setObjectName("commentDeleteButton")
                edit_button.clicked.connect(lambda checked=False, item=comment: self.edit_comment(item))
                delete_button.clicked.connect(lambda checked=False, item=comment: self.delete_comment(item))
                actions.addStretch()
                actions.addWidget(edit_button)
                actions.addWidget(delete_button)
                card_layout.addLayout(actions)
            add_image_previews(card_layout, get_image_attachments('comment', comment['id']))
            self.comments_container_layout.addWidget(card)

    def _comment_menu(self, widget, comment):
        menu = QMenu(widget)
        action = menu.addAction("Создать стик")
        action.triggered.connect(lambda: open_sticky(self, self.current_user_id, 'comment', comment['id'], 'Комментарий', comment['text']))
        menu.exec(widget.mapToGlobal(widget.rect().center()))

    def create_short_description_sticky(self):
        text = self.short_description_edit.text().strip()
        if not text or not self.task_data:
            QMessageBox.information(self, "Стик", "Сначала укажите краткое описание задачи")
            return
        status = str(self.task_data.get('status') or '').casefold()
        color = '#bbf7d0' if 'заверш' in status or 'done' in status else '#fca5a5' if 'просроч' in status or 'cancel' in status else '#fef3a5'
        open_sticky(self, self.current_user_id, 'task', self.task_id, self.title_edit.text().strip(), text, color)

    def send_comment(self):
        from db import add_task_comment
        text = self.comment_edit.toPlainText().strip()
        images = self.comment_edit.screenshots
        if not text and not images:
            QMessageBox.warning(self, "Ошибка", "Введите текст комментария")
            return
        try:
            success = add_task_comment(self.task_id, self.current_user_id, text, images)
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить комментарий:\n{error}")
            return
        if not success:
            QMessageBox.critical(self, "Ошибка", "Не удалось добавить комментарий")
            return
        self.comment_edit.clear()
        self.comment_edit.clear_screenshots()
        self.load_comments()

    def edit_comment(self, comment):
        from db import update_task_comment
        text, accepted = QInputDialog.getMultiLineText(self, "Редактирование комментария", "Комментарий:", comment['text'])
        text = text.strip()
        if not accepted or not text:
            return
        if update_task_comment(comment['id'], self.current_user_id, text):
            self.load_comments()
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось изменить комментарий")

    def delete_comment(self, comment):
        from db import delete_task_comment
        answer = QMessageBox.question(self, "Удаление комментария", "Удалить этот комментарий?")
        if answer != QMessageBox.Yes:
            return
        if delete_task_comment(comment['id'], self.current_user_id):
            self.load_comments()
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось удалить комментарий")

    def save_task(self):
        from db import update_task
        title = self.title_edit.text().strip()
        description = self.desc_text.toPlainText().strip()
        images = self.desc_text.screenshots
        executor_id = self.executor_combo.currentData()
        if not title:
            QMessageBox.warning(self, "Ошибка", "Введите название задачи")
            return
        if len(description) < 10:
            QMessageBox.warning(self, "Ошибка", "Описание должно содержать не менее 10 символов")
            return
        if executor_id is None:
            QMessageBox.warning(self, "Ошибка", "Выберите исполнителя")
            return

        observer_ids = [
            self.observers_list.item(index).data(EMPLOYEE_ID_ROLE)
            for index in range(self.observers_list.count())
            if self.observers_list.item(index).checkState() == Qt.Checked
        ]
        tag_ids = [self.tags_list.item(index).data(TAG_ID_ROLE)
                   for index in range(self.tags_list.count())
                   if self.tags_list.item(index).checkState() == Qt.Checked]
        try:
            success = update_task(
                task_id=self.task_id, title=title, short_description=self.short_description_edit.text().strip(), description=description,
                executor_id=executor_id, status=None, priority=None,
                deadline=self.deadline_edit.date().toString("yyyy-MM-dd"),
                observers_ids=observer_ids, tag_ids=tag_ids,
                status_id=self.status_combo.currentData(),
                priority_id=self.priority_combo.currentData(),
            )
            if success and images:
                from db import add_image_attachments
                success = add_image_attachments('task', self.task_id, images)
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось обновить задачу:\n{error}")
            return
        if not success:
            QMessageBox.critical(self, "Ошибка", "Не удалось обновить задачу")
            return
        QMessageBox.information(self, "Успех", "Задача успешно обновлена")
        self.taskUpdated.emit()

    def confirm_delete(self):
        from db import delete_task
        if self.task_data.get('author_id') != self.current_user_id:
            QMessageBox.warning(self, "Ошибка", "Удалить задачу может только её автор")
            return
        answer = QMessageBox.question(
            self, "Удаление задачи", "Удалить задачу без возможности восстановления?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            success, message = delete_task(self.task_id, self.current_user_id)
        except Exception as error:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить задачу:\n{error}")
            return
        if not success:
            QMessageBox.critical(self, "Ошибка", message)
            return
        QMessageBox.information(self, "Успех", message)
        self.taskUpdated.emit()
