"""
Виджет контактов и чатов в стиле Telegram.
С редактированием, удалением сообщений, статусом прочтения и бейджами непрочитанных.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QFrame,
    QPushButton, QAbstractItemView, QMessageBox,
    QDialog, QDialogButtonBox, QScrollArea, QMenu,
    QSizePolicy, QTextEdit, QStyledItemDelegate,
    QStackedWidget   # обязательно
)
from datetime import datetime   # для edited_at
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QRect, QSize
from PySide6.QtGui import QFont, QAction, QColor, QPainter, QPen
from db import (
    get_contacts_and_groups, get_or_create_personal_chat,
    create_group_chat_auto, get_chat_messages, send_message,
    edit_message, delete_message, mark_messages_as_read,
    mark_notifications_as_read, get_personal_chats, get_unread_message_counts,
    get_new_messages, delete_group_chat
)


# ------------------- Делегат для отрисовки бейджа непрочитанных -------------------
class UnreadBadgeDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        count = index.data(Qt.UserRole + 1)
        if not count or count == 0:
            return

        painter.save()
        rect = option.rect
        badge_size = 20
        margin_right = 10
        margin_top = 5
        badge_rect = QRect(
            rect.right() - badge_size - margin_right,
            rect.top() + margin_top,
            badge_size,
            badge_size
        )

        # Красный круг
        painter.setBrush(QColor("#ff4757"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(badge_rect)

        # Белый текст
        painter.setPen(Qt.white)
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        text = str(count) if count <= 99 else "99+"
        painter.drawText(badge_rect, Qt.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(40)
        return size


# ------------------- Диалог выбора участников -------------------
class GroupChatDialog(QDialog):
    def __init__(self, user_id, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.selected_ids = []
        self.setWindowTitle("Выберите участников")
        self.resize(300, 400)

        layout = QVBoxLayout(self)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск сотрудников...")
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.load_employees()
        self.search_edit.textChanged.connect(self.filter_employees)

    def load_employees(self):
        from db import get_employees
        employees = get_employees()
        self.list_widget.clear()
        for emp in employees:
            emp_id, last_name, first_name, middle_name = emp
            if emp_id == self.user_id:
                continue
            full_name = f"{last_name} {first_name}"
            if middle_name:
                full_name += f" {middle_name}"
            item = QListWidgetItem(full_name)
            item.setData(Qt.UserRole, emp_id)
            self.list_widget.addItem(item)

    def filter_employees(self, text):
        search = text.strip().lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            hidden = search not in item.text().lower()
            item.setHidden(hidden)
            if hidden and item.isSelected():
                item.setSelected(False)

    def get_selected_ids(self):
        return [item.data(Qt.UserRole) for item in self.list_widget.selectedItems()]


# ------------------- Пузырёк сообщения -------------------
class MessageBubble(QFrame):
    editRequested = Signal(int, str)
    saveEditRequested = Signal(int, str)
    deleteRequested = Signal(int)
    editFinished = Signal()

    def __init__(self, msg_data, is_own, parent=None):
        super().__init__(parent)

        self.msg_data = msg_data
        self.is_own = is_own
        self.message_id = msg_data["id"]

        self.setObjectName("messageBubble")
        self.setProperty("isOwn", "true" if is_own else "false")
        self.setFrameShape(QFrame.NoFrame)

        self.style().unpolish(self)
        self.style().polish(self)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setup_ui()

    def setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(5, 2, 5, 2)
        self.main_layout.setSpacing(0)

        self.bubble = QFrame()
        self.bubble.setObjectName("bubbleFrame")
        self.bubble.setMinimumWidth(50)
        self.bubble.setMaximumWidth(450)
        self.bubble.setProperty("isOwn", "true" if self.is_own else "false")
        self.bubble.style().unpolish(self.bubble)
        self.bubble.style().polish(self.bubble)

        bubble_layout = QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(10, 7, 10, 7)
        bubble_layout.setSpacing(3)

        if not self.is_own:
            name_label = QLabel(self.msg_data["sender_name"])
            name_label.setObjectName("senderName")
            name_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
            bubble_layout.addWidget(name_label)

        self.text_label = QLabel()
        self.text_label.setObjectName("messageText")
        self.text_label.setTextFormat(Qt.PlainText)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.text_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        self.update_text_display()
        bubble_layout.addWidget(self.text_label)
        bubble_layout.setStretch(0, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(5)

        self.time_label = QLabel(self.msg_data["time"])
        self.time_label.setObjectName("timeLabel")
        self.time_label.setFont(QFont("Segoe UI", 8))
        bottom_row.addWidget(self.time_label)

        self.edited_label = QLabel()
        self.edited_label.setObjectName("editedLabel")
        self.edited_label.setFont(QFont("Segoe UI", 8))
        self.edited_label.setVisible(bool(self.msg_data.get("edited_at")))
        self.edited_label.setText("изменено")
        bottom_row.addWidget(self.edited_label)

        bottom_row.addStretch()

        if self.is_own:
            self.status_icon = QLabel()
            self.status_icon.setObjectName("statusIcon")
            self.status_icon.setFont(QFont("Segoe UI", 9))
            self.update_status_icon()
            bottom_row.addWidget(self.status_icon)

        bubble_layout.addLayout(bottom_row)

        if self.is_own:
            self.main_layout.addStretch()
            self.main_layout.addWidget(self.bubble)
        else:
            self.main_layout.addWidget(self.bubble)
            self.main_layout.addStretch()

    def update_text_display(self):
        if self.msg_data.get("is_deleted"):
            self.text_label.setText("[Сообщение удалено]")
            self.text_label.setProperty("deleted", "true")
        else:
            self.text_label.setText(self.msg_data.get("text", ""))
            self.text_label.setProperty("deleted", "false")
        self.text_label.style().unpolish(self.text_label)
        self.text_label.style().polish(self.text_label)

    def update_status_icon(self):
        if not hasattr(self, "status_icon"):
            return
        if self.msg_data.get("is_read"):
            self.status_icon.setText("✓✓")
            self.status_icon.setProperty("read", "true")
        else:
            self.status_icon.setText("✓")
            self.status_icon.setProperty("read", "false")
        self.status_icon.style().unpolish(self.status_icon)
        self.status_icon.style().polish(self.status_icon)

    def show_context_menu(self, position):
        if not self.is_own:
            return
        menu = QMenu(self)
        edit_action = QAction("Редактировать", self)
        delete_action = QAction("Удалить", self)
        edit_action.triggered.connect(
            lambda: self.editRequested.emit(self.message_id, self.msg_data["text"])
        )
        delete_action.triggered.connect(
            lambda: self.deleteRequested.emit(self.message_id)
        )
        menu.addAction(edit_action)
        menu.addAction(delete_action)
        menu.exec(self.mapToGlobal(position))

    def enter_edit_mode(self, current_text):
        self.edit_input = QLineEdit(current_text)
        self.edit_input.setObjectName("editInput")
        layout = self.bubble.layout()
        self.text_label.hide()
        # Вставляем на место text_label (всегда index 1 для своих, и index 1 для чужих?
        # У чужих: 0 - senderName, 1 - text_label, 2 - bottom_row
        # У своих: 0 - text_label, 1 - bottom_row
        # Безопаснее заменить существующий text_label через parent layout
        index = layout.indexOf(self.text_label)
        if index >= 0:
            layout.insertWidget(index, self.edit_input)
        self.edit_input.setFocus()
        self.edit_input.returnPressed.connect(lambda: self.finish_edit(True))

    def finish_edit(self, save):
        new_text = ""
        if hasattr(self, "edit_input"):
            new_text = self.edit_input.text()
            self.bubble.layout().removeWidget(self.edit_input)
            self.edit_input.deleteLater()
            del self.edit_input
        self.text_label.show()
        if save and new_text.strip():
            self.saveEditRequested.emit(self.message_id, new_text.strip())
        self.update_text_display()
        self.editFinished.emit()

    def keyPressEvent(self, event):
        if hasattr(self, "edit_input") and event.key() == Qt.Key_Escape:
            self.finish_edit(False)
            return
        super().keyPressEvent(event)


# ------------------- Область сообщений (прокручиваемый контейнер) -------------------
class ChatMessagesArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setObjectName("messageArea")
        self.setStyleSheet("")

        container = QWidget()
        container.setObjectName("scrollContainer")
        self.messages_layout = QVBoxLayout(container)
        self.messages_layout.setAlignment(Qt.AlignTop)
        self.messages_layout.setSpacing(5)
        self.messages_layout.setContentsMargins(10, 10, 10, 10)
        self.setWidget(container)

    def clear_messages(self):
        while self.messages_layout.count():
            child = self.messages_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def add_message(self, msg_widget):
        self.messages_layout.addWidget(msg_widget)


# ------------------- Основной виджет контактов и чата -------------------
class ContactsWidget(QWidget):
    def __init__(self, current_user_id, parent=None):
        super().__init__(parent)
        self.current_user_id = current_user_id
        self.current_chat_id = None
        self.current_chat_name = ""
        self.current_chat_type = None
        self.last_message_id = 0
        self.current_contact_id = None
        self._suppress_selection = False
        self._editing = False
        self.current_search_text = ""

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_messages)
        self.timer.start(3000)

        self.init_ui()
        self.load_contacts()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Левая панель (контакты)
        left_panel = QFrame()
        left_panel.setObjectName("contactsLeftPanel")
        left_panel.setFixedWidth(300)

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        title = QLabel("Контакты")
        title.setObjectName("contactsTitle")
        left_layout.addWidget(title)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск...")
        self.search_input.setObjectName("contactsSearch")
        self.search_input.textChanged.connect(self.on_search)
        left_layout.addWidget(self.search_input)

        self.contact_list = QListWidget()
        self.contact_list.setItemDelegate(UnreadBadgeDelegate(self))
        self.contact_list.setObjectName("contactsList")
        self.contact_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.contact_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.contact_list.customContextMenuRequested.connect(self.show_contact_context_menu)
        self.contact_list.currentItemChanged.connect(self.on_current_changed)
        left_layout.addWidget(self.contact_list)

        self.create_group_btn = QPushButton("Создать групповой чат")
        self.create_group_btn.setObjectName("createGroupBtn")
        self.create_group_btn.clicked.connect(self.create_group_chat)
        left_layout.addWidget(self.create_group_btn)

        # Правая панель (чат) — сохраняем в self.chat_area для скрытия
        self.chat_area = QFrame()
        self.chat_area.setObjectName("chatPanel")
        chat_layout = QVBoxLayout(self.chat_area)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self.chat_header = QLabel("Выберите чат")
        self.chat_header.setObjectName("chatHeader")
        chat_layout.addWidget(self.chat_header)

        # Делаем контейнер для кэшированных областей
        self.chat_stack = QStackedWidget()
        self.chat_stack.setObjectName("chatStack")
        chat_layout.addWidget(self.chat_stack)

        # Кэш областей: chat_id -> ChatMessagesArea
        self.chat_areas = {}

        input_frame = QFrame()
        input_frame.setObjectName("inputFrame")
        input_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 5, 10, 5)
        input_layout.setSpacing(8)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Сообщение...")
        self.message_input.setObjectName("messageInput")
        self.message_input.setMinimumHeight(38)
        self.message_input.setMaximumHeight(90)
        self.message_input.installEventFilter(self)
        self.send_btn = QPushButton("Отправить")
        self.send_btn.setMinimumHeight(45)
        self.send_btn.setEnabled(False)
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.clicked.connect(self.send_message_action)
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_btn)
        chat_layout.addWidget(input_frame)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.chat_area, 1)

    def _get_chat_area(self, chat_id):
        """Получить или создать область сообщений для чата."""
        if chat_id not in self.chat_areas:
            area = ChatMessagesArea()
            self.chat_areas[chat_id] = area
            self.chat_stack.addWidget(area)
        return self.chat_areas[chat_id]

    def pause_timer(self):
        self.timer.stop()
        self._editing = True

    def resume_timer(self):
        self._editing = False
        self.timer.start(3000)

    def load_contacts(self, search_text=""):
        self.current_search_text = search_text
        contacts = get_contacts_and_groups(self.current_user_id, search_text if search_text else None)
        personal_chats = get_personal_chats(self.current_user_id)
        unread_counts = get_unread_message_counts(self.current_user_id)

        # Разделяем контакты на категории для сортировки
        self_items = []
        employee_items = []
        group_items = []
        
        for c in contacts:
            if c['type'] == 'self':
                chat_id = c['chat_id']
                unread = unread_counts.get(chat_id, 0) if chat_id else 0
                item_data = {'prefix': '⭐ ', 'name': c['name'], 'data': c, 'unread': unread, 'created_by': None}
                self_items.append(item_data)
            elif c['type'] == 'employee':
                prefix = "👤 "
                chat_id = personal_chats.get(c['id'])
                unread = unread_counts.get(chat_id, 0) if chat_id else 0
                item_data = {'prefix': prefix, 'name': c['name'], 'data': c, 'unread': unread, 'created_by': None}
                employee_items.append(item_data)
            elif c['type'] == 'group':
                prefix = "👥 "
                chat_id = c['chat_id']
                unread = unread_counts.get(chat_id, 0) if chat_id else 0
                created_by = c.get('created_by')
                item_data = {'prefix': prefix, 'name': c['name'], 'data': c, 'unread': unread, 'created_by': created_by}
                group_items.append(item_data)
        
        # Сортировка внутри каждой категории: сначала с непрочитанными (по имени), затем без (по имени)
        def sort_key(item):
            has_unread = 1 if item['unread'] > 0 else 0
            return (-has_unread, item['name'].lower())
        
        self_items.sort(key=sort_key)
        employee_items.sort(key=sort_key)
        group_items.sort(key=sort_key)
        
        # Объединяем: сначала "Избранное", затем сотрудники, затем группы
        all_items = self_items + employee_items + group_items
        
        self.contact_list.clear()
        for item_data in all_items:
            item = QListWidgetItem(item_data['prefix'] + item_data['name'])
            item.setData(Qt.UserRole, item_data['data'])
            item.setData(Qt.UserRole + 1, item_data['unread'])
            # Для групповых чатов сохраняем created_by для проверки прав удаления
            if item_data['data']['type'] == 'group' and item_data['created_by'] is not None:
                item.setData(Qt.UserRole + 2, item_data['created_by'])
            self.contact_list.addItem(item)

        self.highlight_current_chat()

    def on_search(self, text):
        self.load_contacts(text.strip())

    def on_current_changed(self, current, previous):
        if self._suppress_selection or current is None:
            return
        data = current.data(Qt.UserRole)
        if data is None:
            return
        if data['type'] == 'self':
            # Чат с самим собой (Избранное)
            chat_id = data['chat_id']
            if chat_id:
                self.open_chat(chat_id, data['name'], 'self')
        elif data['type'] == 'employee':
            emp_id = data['id']
            if emp_id == self.current_user_id:
                return
            chat_id = get_or_create_personal_chat(self.current_user_id, emp_id)
            if chat_id:
                self.current_contact_id = emp_id
                self.open_chat(chat_id, data['name'], 'personal')
        elif data['type'] == 'group':
            self.open_chat(data['chat_id'], data['name'], 'group')

    def open_chat(self, chat_id, name, chat_type):
        if self.current_chat_id == chat_id:
            return

        mark_notifications_as_read(self.current_user_id, chat_id)
        mark_messages_as_read(chat_id, self.current_user_id)

        # Очищаем поле ввода при переключении чата
        self.message_input.clear()

        self.current_chat_id = chat_id
        self.current_chat_name = name
        self.current_chat_type = chat_type
        self.chat_header.setText(name)
        self.send_btn.setEnabled(True)

        # Получаем или создаём область
        area = self._get_chat_area(chat_id)

        # Если область уже существует, просто показываем её (сообщения уже есть)
        if area.messages_layout.count() > 0:
            self.chat_stack.setCurrentWidget(area)
            self.highlight_current_chat()
            # Обновляем last_message_id для кэшированной области
            messages = get_chat_messages(self.current_chat_id)
            if messages:
                self.last_message_id = messages[-1]['id']
            else:
                self.last_message_id = 0
            return

        # Первый раз – загружаем сообщения
        self._load_messages_into_area(area, chat_id)
        self.chat_stack.setCurrentWidget(area)
        self.highlight_current_chat()

    def _load_messages_into_area(self, area, chat_id):
        messages = get_chat_messages(chat_id)
        for msg in messages:
            is_own = (msg['sender_id'] == self.current_user_id)
            bubble = MessageBubble(msg, is_own)
            bubble.editRequested.connect(self.on_edit_request)
            bubble.saveEditRequested.connect(self.on_edit_message)
            bubble.deleteRequested.connect(self.on_delete_request)
            bubble.editFinished.connect(self.resume_timer)
            area.add_message(bubble)
        if messages:
            self.last_message_id = messages[-1]['id']
        QTimer.singleShot(10, lambda: area.verticalScrollBar().setValue(
            area.verticalScrollBar().maximum()
        ))

    def highlight_current_chat(self):
        if self.current_chat_id is None:
            self.contact_list.clearSelection()
            return
        for i in range(self.contact_list.count()):
            item = self.contact_list.item(i)
            data = item.data(Qt.UserRole)
            if not data:
                continue
            if data['type'] == 'group' and data.get('chat_id') == self.current_chat_id:
                self._suppress_selection = True
                self.contact_list.setCurrentItem(item)
                self._suppress_selection = False
                return
            elif data['type'] == 'employee':
                # Для личного чата сравниваем ID сотрудника с current_contact_id
                if self.current_chat_type == 'personal' and data['id'] == self.current_contact_id:
                    self._suppress_selection = True
                    self.contact_list.setCurrentItem(item)
                    self._suppress_selection = False
                    return
        self.contact_list.clearSelection()

    def load_messages(self):
        """Загрузка всех сообщений без мерцания."""
        if self.current_chat_id is None:
            return

        messages = get_chat_messages(self.current_chat_id)

        # Замораживаем обновление области сообщений
        self.messages_area.setUpdatesEnabled(False)

        # Очищаем существующие сообщения
        self.messages_area.clear_messages()

        # Добавляем новые сообщения
        for msg in messages:
            is_own = (msg['sender_id'] == self.current_user_id)
            bubble = MessageBubble(msg, is_own)
            bubble.editRequested.connect(self.on_edit_request)
            bubble.saveEditRequested.connect(self.on_edit_message)
            bubble.deleteRequested.connect(self.on_delete_request)
            bubble.editFinished.connect(self.resume_timer)
            self.messages_area.add_message(bubble)

        # Размораживаем обновление — все изменения применятся одним кадром
        self.messages_area.setUpdatesEnabled(True)

        if messages:
            self.last_message_id = messages[-1]['id']

        # Прокрутка вниз
        QTimer.singleShot(10, lambda: self.messages_area.verticalScrollBar().setValue(
            self.messages_area.verticalScrollBar().maximum()
        ))

    def eventFilter(self, obj, event):
        if obj == self.message_input:
            if event.type() == QEvent.Type.KeyPress:
                if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    if event.modifiers() & Qt.ShiftModifier:
                        return False
                    self.send_message_action()
                    return True
        return super().eventFilter(obj, event)

    def send_message_action(self):
        if self.current_chat_id is None:
            return
        text = self.message_input.toPlainText().strip()
        if not text:
            return

        if send_message(self.current_chat_id, self.current_user_id, text):
            self.message_input.clear()
            mark_messages_as_read(self.current_chat_id, self.current_user_id)

            area = self.chat_stack.currentWidget()
            if not area:
                return

            # Получаем последнее отправленное (правильная сортировка!)
            # В db.py get_chat_messages должен использовать ORDER BY created_at DESC LIMIT 1,
            # либо берём последний элемент из полного списка.
            # Здесь делаем запрос с LIMIT 1 и DESC
            new_messages = get_chat_messages(self.current_chat_id, limit=1, order_desc=True)
            if new_messages:
                msg = new_messages[0]
                is_own = (msg['sender_id'] == self.current_user_id)
                bubble = MessageBubble(msg, is_own)
                bubble.editRequested.connect(self.on_edit_request)
                bubble.saveEditRequested.connect(self.on_edit_message)
                bubble.deleteRequested.connect(self.on_delete_request)
                bubble.editFinished.connect(self.resume_timer)
                area.add_message(bubble)
                self.last_message_id = msg['id']

                scrollbar = area.verticalScrollBar()
                QTimer.singleShot(50, lambda: scrollbar.setValue(scrollbar.maximum()))

            self.update_unread_badges()

    def _update_existing_bubbles(self, area, messages):
        """Обновить статусы видимых сообщений."""
        msg_dict = {m['id']: m for m in messages}
        for i in range(area.messages_layout.count()):
            item = area.messages_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, MessageBubble) and w.message_id in msg_dict:
                    updated = msg_dict[w.message_id]
                    w.msg_data['is_read'] = updated['is_read']
                    w.msg_data['is_deleted'] = updated['is_deleted']
                    w.msg_data['text'] = updated['text']
                    w.msg_data['edited_at'] = updated['edited_at']
                    w.update_text_display()
                    if hasattr(w, 'update_status_icon'):
                        w.update_status_icon()
                    if hasattr(w, 'edited_label'):
                        w.edited_label.setVisible(bool(updated.get('edited_at')))

    def refresh_messages(self):
        if self._editing or self.current_chat_id is None:
            return

        area = self.chat_stack.currentWidget()
        if not area:
            return

        # Получаем только новые сообщения (ID > last_message_id)
        # Для этого доработаем db.py, добавив get_new_messages(chat_id, last_id)
        new_messages = get_new_messages(self.current_chat_id, self.last_message_id)
        if not new_messages:
            return

        for msg in new_messages:
            is_own = (msg['sender_id'] == self.current_user_id)
            bubble = MessageBubble(msg, is_own)
            bubble.editRequested.connect(self.on_edit_request)
            bubble.saveEditRequested.connect(self.on_edit_message)
            bubble.deleteRequested.connect(self.on_delete_request)
            bubble.editFinished.connect(self.resume_timer)
            area.add_message(bubble)
            self.last_message_id = msg['id']

        # Прокрутка вниз, если были добавлены
        scrollbar = area.verticalScrollBar()
        if scrollbar.value() >= scrollbar.maximum() - 10:
            QTimer.singleShot(50, lambda: scrollbar.setValue(scrollbar.maximum()))

        # Обновление статусов существующих сообщений (прочитано/удалено)
        self._update_existing_bubbles(area, new_messages)

        self.update_unread_badges()

    def update_unread_badges(self):
        unread_counts = get_unread_message_counts(self.current_user_id)
        personal_chats = get_personal_chats(self.current_user_id)
        for i in range(self.contact_list.count()):
            item = self.contact_list.item(i)
            data = item.data(Qt.UserRole)
            if not data:
                continue
            chat_id = None
            if data['type'] == 'employee':
                chat_id = personal_chats.get(data['id'])
            elif data['type'] == 'group':
                chat_id = data.get('chat_id')
            if chat_id:
                count = unread_counts.get(chat_id, 0)
                item.setData(Qt.UserRole + 1, count)
        self.contact_list.viewport().update()

    def on_edit_request(self, message_id, current_text):
        bubble = self.find_message_bubble(message_id)
        if bubble:
            self.pause_timer()
            bubble.enter_edit_mode(current_text)

    def on_delete_request(self, message_id):
        if delete_message(message_id):
            bubble = self.find_message_bubble(message_id)
            if bubble:
                area = self.chat_stack.currentWidget()
                if area:
                    area.messages_layout.removeWidget(bubble)
                bubble.deleteLater()

    def on_edit_message(self, message_id, new_text):
        if edit_message(message_id, new_text):
            bubble = self.find_message_bubble(message_id)
            if bubble:
                bubble.msg_data["text"] = new_text
                bubble.msg_data["edited_at"] = datetime.now().strftime("%H:%M")  # фикс
                bubble.update_text_display()
                if hasattr(bubble, "edited_label"):
                    bubble.edited_label.setVisible(True)

    def find_message_bubble(self, message_id):
        area = self.chat_stack.currentWidget()
        if not area:
            return None
        for i in range(area.messages_layout.count()):
            item = area.messages_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, MessageBubble) and w.message_id == message_id:
                    return w
        return None

    def create_group_chat(self):
        dialog = GroupChatDialog(self.current_user_id, self)
        if dialog.exec() == QDialog.Accepted:
            selected_ids = dialog.get_selected_ids()
            if not selected_ids:
                QMessageBox.warning(self, "Предупреждение", "Не выбрано ни одного участника.")
                return
            member_ids = [self.current_user_id] + selected_ids
            result = create_group_chat_auto(self.current_user_id, member_ids)
            if result:
                chat_id, auto_name = result
                self.open_chat(chat_id, auto_name, 'group')
                self.load_contacts()
            else:
                QMessageBox.critical(self, "Ошибка", "Не удалось создать групповой чат.")

    def show_contact_context_menu(self, position):
        """Контекстное меню для списка контактов (правая кнопка мыши)."""
        item = self.contact_list.itemAt(position)
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not data or data['type'] != 'group':
            return
        
        # Проверяем, является ли текущий пользователь создателем группы
        created_by = item.data(Qt.UserRole + 2)
        if created_by != self.current_user_id:
            return
        
        menu = QMenu(self)
        delete_action = QAction("Удалить групповой чат", self)
        delete_action.triggered.connect(lambda: self.delete_group_chat_action(data['chat_id'], item))
        menu.addAction(delete_action)
        menu.exec(self.contact_list.mapToGlobal(position))

    def delete_group_chat_action(self, chat_id, item):
        """Удаление группового чата."""
        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Вы уверены, что хотите удалить групповой чат?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if delete_group_chat(chat_id, self.current_user_id):
                # Удаляем элемент из списка
                row = self.contact_list.row(item)
                if row >= 0:
                    self.contact_list.takeItem(row)
                # Если удалили текущий чат, сбрасываем
                if self.current_chat_id == chat_id:
                    self.current_chat_id = None
                    self.current_chat_name = ""
                    self.current_chat_type = None
                    self.chat_header.setText("Выберите чат")
                    self.send_btn.setEnabled(False)
                # Очищаем кэш области сообщений
                if chat_id in self.chat_areas:
                    area = self.chat_areas[chat_id]
                    self.chat_stack.removeWidget(area)
                    area.deleteLater()
                    del self.chat_areas[chat_id]
                QMessageBox.information(self, "Успешно", "Групповой чат удалён.")
            else:
                QMessageBox.critical(self, "Ошибка", "Не удалось удалить групповой чат.")

    def open_chat_by_id(self, chat_id):
        """Открыть чат по ID (используется для перехода из уведомлений)."""
        for i in range(self.contact_list.count()):
            item = self.contact_list.item(i)
            data = item.data(Qt.UserRole)
            if data and ((data['type'] == 'group' and data.get('chat_id') == chat_id) or
                         (data['type'] == 'employee' and data.get('chat_id') == chat_id)):
                self.contact_list.setCurrentItem(item)
                return