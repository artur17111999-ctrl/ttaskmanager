"""Telegram-style contacts and chat widget."""

from datetime import datetime

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QStyledItemDelegate, QVBoxLayout,
    QWidget,
)

from db import (
    create_group_chat_auto, delete_draft, delete_group_chat, delete_message,
    edit_message, forward_messages, get_chat_messages, get_contacts_and_groups,
    get_draft, get_message_attachments, get_new_messages, get_or_create_personal_chat,
    get_personal_chats, get_pinned_chats, get_unread_message_counts,
    mark_messages_as_read, mark_notifications_as_read, pin_chat, save_draft,
    search_chat_messages, send_message, unpin_chat,
)
from screenshot_attachments import ScreenshotPreview, ScreenshotTextEdit, add_image_previews
from sticky_notes import open_sticky


class UnreadBadgeDelegate(QStyledItemDelegate):
    """Paint the unread counter without mixing it into a contact name."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        count = index.data(Qt.UserRole + 1) or 0
        if count <= 0:
            return
        text = str(count) if count < 100 else "99+"
        painter.save()
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        width = max(20, painter.fontMetrics().horizontalAdvance(text) + 12)
        rect = option.rect.adjusted(option.rect.width() - width - 12, 10, -12, -10)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#3390ec"))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setPen(Qt.white)
        painter.drawText(rect, Qt.AlignCenter, text)
        painter.restore()


class ChoiceDialog(QDialog):
    """Searchable employee/chat picker used for groups and forwarding."""

    def __init__(self, title, placeholder, multi, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(380, 460)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder)
        self.list = QListWidget()
        self.list.setSelectionMode(
            QAbstractItemView.MultiSelection if multi else QAbstractItemView.SingleSelection
        )
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(self.search)
        layout.addWidget(self.list)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self._filter)
        if not multi:
            self.list.itemDoubleClicked.connect(lambda _: self.accept())

    def _filter(self, query):
        query = query.strip().casefold()
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setHidden(bool(query and query not in item.text().casefold()))


class GroupChatDialog(ChoiceDialog):
    def __init__(self, user_id, parent=None):
        super().__init__("Новая группа", "Поиск сотрудников…", True, parent)
        from db import get_employees

        for employee_id, last_name, first_name, middle_name in get_employees():
            if employee_id == user_id:
                continue
            item = QListWidgetItem("👤 " + " ".join(filter(None, (last_name, first_name, middle_name))))
            item.setData(Qt.UserRole, employee_id)
            self.list.addItem(item)

    def selected_ids(self):
        return [item.data(Qt.UserRole) for item in self.list.selectedItems()]


class ForwardChatDialog(ChoiceDialog):
    def __init__(self, user_id, source_chat_id, parent=None):
        super().__init__("Переслать сообщения", "Поиск чатов…", False, parent)
        contacts = get_contacts_and_groups(user_id)
        personal_chats = get_personal_chats(user_id)
        for contact in contacts:
            chat_id = contact.get("chat_id")
            if contact["type"] == "employee":
                chat_id = personal_chats.get(contact["id"])
            if not chat_id or chat_id == source_chat_id:
                continue
            icon = "👥" if contact["type"] == "group" else "⭐" if contact["type"] == "self" else "👤"
            item = QListWidgetItem(f"{icon} {contact['name']}")
            item.setData(Qt.UserRole, chat_id)
            self.list.addItem(item)

    def selected_chat_id(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None


class MessageBubble(QFrame):
    editRequested = Signal(int, str)
    deleteRequested = Signal(int)
    selectionChanged = Signal(int, bool)
    stickyRequested = Signal(int, str)

    def __init__(self, message, own, parent=None):
        super().__init__(parent)
        self.message = message
        self.message_id = message["id"]
        self.own = own
        self.selected = False
        self.setObjectName("messageBubble")
        self.setProperty("selected", "false")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 2, 8, 2)
        self.card = QFrame(objectName="bubbleFrame")
        self.card.setProperty("isOwn", "true" if own else "false")
        self.card.setMaximumWidth(520)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12, 8, 12, 7)
        card_layout.setSpacing(4)

        if not own:
            self.sender_label = QLabel(message.get("sender_name", ""), objectName="senderName")
            card_layout.addWidget(self.sender_label)
        if message.get("is_forwarded"):
            self.forwarded_label = QLabel(
                f"↪ Переслано от {message.get('forwarded_from') or 'неизвестного отправителя'}",
                objectName="forwardedLabel",
            )
            card_layout.addWidget(self.forwarded_label)

        self.body = QLabel(objectName="messageText")
        self.body.setTextFormat(Qt.PlainText)
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        card_layout.addWidget(self.body)
        add_image_previews(card_layout, message.get("images", []))

        meta = QHBoxLayout()
        self.edited = QLabel("изменено", objectName="editedLabel")
        self.time = QLabel(message.get("time", ""), objectName="timeLabel")
        meta.addStretch()
        meta.addWidget(self.edited)
        meta.addWidget(self.time)
        if own:
            self.status_label = QLabel(objectName="statusIcon")
            meta.addWidget(self.status_label)
        card_layout.addLayout(meta)
        if own:
            outer.addStretch(1)
            outer.addWidget(self.card)
        else:
            outer.addWidget(self.card)
            outer.addStretch(1)
        self.refresh(message)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    def refresh(self, message):
        self.message = message
        self.body.setText(message.get("text") or "")
        self.body.setProperty("deleted", "false")
        self.edited.setVisible(bool(message.get("edited_at")))
        if self.own and hasattr(self, "status"):
            self.status_label.setText("✓✓" if message.get("is_read") else "✓")
            self.status_label.setProperty("read", "true" if message.get("is_read") else "false")
        for widget in (self.body, self.card, getattr(self, "status_label", None)):
            if widget:
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def _show_menu(self, _position):
        menu = QMenu(self)
        if self.own:
            edit = menu.addAction("Редактировать")
            edit.triggered.connect(lambda: self.editRequested.emit(self.message_id, self.message.get("text") or ""))
            remove = menu.addAction("Удалить")
            remove.triggered.connect(lambda: self.deleteRequested.emit(self.message_id))
            menu.addSeparator()
        choose = menu.addAction("Снять выделение" if self.selected else "Выделить")
        choose.triggered.connect(self.toggle_selected)
        menu.addSeparator()
        sticky = menu.addAction("Создать стик")
        sticky.triggered.connect(lambda: self.stickyRequested.emit(self.message_id, self.message.get("text") or ""))
        menu.exec(self.mapToGlobal(_position))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and (self.property("selectionMode") or event.modifiers() & Qt.ControlModifier):
            self.toggle_selected()
            event.accept()
            return
        super().mousePressEvent(event)

    def toggle_selected(self):
        self.selected = not self.selected
        self.setProperty("selected", "true" if self.selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.selectionChanged.emit(self.message_id, self.selected)

    def set_selection_mode(self, enabled):
        self.setProperty("selectionMode", enabled)
        for widget in (self.card, self.body, getattr(self, "sender_label", None), getattr(self, "forwarded_label", None)):
            if widget:
                widget.setAttribute(Qt.WA_TransparentForMouseEvents, enabled)


class ChatMessagesArea(QScrollArea):
    selectionCountChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setObjectName("messageArea")
        self.selected_ids = set()
        self.bubbles = {}
        container = QWidget(objectName="scrollContainer")
        self.layout = QVBoxLayout(container)
        self.layout.setAlignment(Qt.AlignTop)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(4)
        self.setWidget(container)
        self._last_date = None

    def replace_messages(self, messages, user_id, connect_bubble):
        self.clear()
        for message in messages:
            self.append(message, user_id, connect_bubble)

    def clear(self):
        self.selected_ids.clear()
        self.bubbles.clear()
        self._last_date = None
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.selectionCountChanged.emit(0)

    def append(self, message, user_id, connect_bubble):
        if message["id"] in self.bubbles:
            self.bubbles[message["id"]].refresh(message)
            return
        message_date = self._message_date(message)
        if message_date is not None and message_date != self._last_date:
            self._add_date_separator(message_date)
            self._last_date = message_date
        bubble = MessageBubble(message, message["sender_id"] == user_id)
        connect_bubble(bubble)
        bubble.selectionChanged.connect(self._selection_changed)
        self.bubbles[bubble.message_id] = bubble
        self.layout.addWidget(bubble)

    @staticmethod
    def _message_date(message):
        created_at = message.get("created_at")
        if hasattr(created_at, "date"):
            return created_at.date()
        return None

    def _add_date_separator(self, message_date):
        label = QLabel(objectName="dateSeparator")
        if message_date == datetime.now().date():
            text = "Сегодня"
        elif message_date:
            text = message_date.strftime("%d.%m.%Y")
        else:
            text = ""
        label.setText(text)
        label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(label)

    def update(self, messages, user_id, connect_bubble):
        current_ids = {message["id"] for message in messages}
        for message in messages:
            if message["id"] in self.bubbles:
                self.bubbles[message["id"]].refresh(message)
            else:
                self.append(message, user_id, connect_bubble)
        # A hard deletion should not leave an orphaned bubble.
        for message_id in set(self.bubbles) - current_ids:
            bubble = self.bubbles.pop(message_id)
            self.layout.removeWidget(bubble)
            bubble.deleteLater()

    def _selection_changed(self, message_id, selected):
        if selected:
            self.selected_ids.add(message_id)
        else:
            self.selected_ids.discard(message_id)
        self.selectionCountChanged.emit(len(self.selected_ids))
        selection_mode = bool(self.selected_ids)
        for bubble in self.bubbles.values():
            bubble.set_selection_mode(selection_mode)

    def clear_selection(self):
        for bubble in list(self.bubbles.values()):
            if bubble.selected:
                bubble.toggle_selected()


class ContactsWidget(QWidget):
    """A compact, state-safe chat view backed by the existing database API."""

    REFRESH_INTERVAL_MS = 2500

    def __init__(self, current_user_id, parent=None):
        super().__init__(parent)
        self.current_user_id = current_user_id
        self.current_chat_id = None
        self.current_contact_id = None
        self.current_chat_type = None
        self.last_message_id = 0
        self._suppress_selection = False
        self._editing_bubble = None
        self._message_filter = ""
        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.timeout.connect(self._hide_typing_indicator)
        self._peer_typing_timer = QTimer(self)
        self._peer_typing_timer.setSingleShot(True)
        self._peer_typing_timer.timeout.connect(self._hide_peer_typing_indicator)
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(self.REFRESH_INTERVAL_MS)
        self.load_contacts()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame(objectName="contactsLeftPanel")
        sidebar.setFixedWidth(320)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 14, 12, 12)
        title_row = QHBoxLayout()
        title = QLabel("Чаты", objectName="contactsTitle")
        self.new_group = QPushButton("＋", objectName="createGroupBtn", toolTip="Создать группу")
        self.new_group.setFixedSize(36, 36)
        self.new_group.clicked.connect(self.create_group_chat)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self.new_group)
        self.search = QLineEdit(objectName="contactsSearch", placeholderText="Поиск")
        self.search.textChanged.connect(self.load_contacts)
        self.contacts = QListWidget(objectName="contactsList")
        self.contacts.setItemDelegate(UnreadBadgeDelegate(self.contacts))
        self.contacts.setSelectionMode(QAbstractItemView.SingleSelection)
        self.contacts.currentItemChanged.connect(self._contact_selected)
        self.contacts.setContextMenuPolicy(Qt.CustomContextMenu)
        self.contacts.customContextMenuRequested.connect(self._contact_menu)
        side_layout.addLayout(title_row)
        side_layout.addWidget(self.search)
        side_layout.addWidget(self.contacts)

        panel = QFrame(objectName="chatPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        header = QFrame(objectName="chatHeaderPanel")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 10, 14, 10)
        self.header = QLabel("Выберите чат", objectName="chatHeader")
        self.peer_typing_label = QLabel("", objectName="peerTypingIndicator")
        self.peer_typing_label.setVisible(False)
        self.message_search = QLineEdit(placeholderText="Поиск по сообщениям...", objectName="messageSearch")
        self.message_search.setClearButtonEnabled(True)
        self.message_search.textChanged.connect(self.search_messages)
        self.selection_label = QLabel(objectName="selectedCountLabel")
        self.forward_button = QPushButton("Переслать", objectName="forwardSelectedBtn")
        self.delete_button = QPushButton("Удалить", objectName="deleteSelectedBtn")
        self.forward_button.clicked.connect(self.forward_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        header_layout.addWidget(self.header)
        header_layout.addWidget(self.message_search, 1)
        header_layout.addStretch()
        header_layout.addWidget(self.selection_label)
        header_layout.addWidget(self.forward_button)
        header_layout.addWidget(self.delete_button)
        self.area = ChatMessagesArea()
        self.area.selectionCountChanged.connect(self._selection_changed)
        typing_frame = QFrame(objectName="typingStatusFrame")
        typing_layout = QHBoxLayout(typing_frame)
        typing_layout.setContentsMargins(12, 4, 12, 4)
        typing_layout.setSpacing(0)
        self.typing_label = QLabel("", objectName="typingIndicator")
        self.typing_label.setVisible(False)
        typing_layout.addWidget(self.typing_label)
        typing_layout.addStretch()
        composer = QFrame(objectName="inputFrame")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(12, 8, 12, 8)
        composer_layout.setSpacing(8)
        self.input = ScreenshotTextEdit()
        self.input.setObjectName("messageInput")
        self.input.setPlaceholderText("Сообщение")
        self.input.setMinimumHeight(44)
        self.input.setMaximumHeight(110)
        self.input.installEventFilter(self)
        self.input.textChanged.connect(self._sync_draft)
        self.input.textChanged.connect(self._handle_typing)
        self.send_button = QPushButton("➤", objectName="sendBtn", toolTip="Отправить")
        self.send_button.setFixedSize(44, 44)
        self.send_button.clicked.connect(self.send)
        self.preview = ScreenshotPreview(self.input)
        composer_layout.addWidget(self.input)
        composer_layout.addWidget(self.send_button)
        panel_layout.addWidget(header)
        panel_layout.addWidget(self.area, 1)
        panel_layout.addWidget(self.preview)
        panel_layout.addWidget(typing_frame)
        panel_layout.addWidget(composer)
        layout.addWidget(sidebar)
        layout.addWidget(panel, 1)
        self._selection_changed(0)
        self._set_chat_enabled(False)

    def _set_chat_enabled(self, enabled):
        self.input.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        self.message_search.setEnabled(enabled)

    def load_contacts(self, _unused=None):
        query = self.search.text().strip()
        contacts = get_contacts_and_groups(self.current_user_id, query or None)
        chats = get_personal_chats(self.current_user_id)
        unread = get_unread_message_counts(self.current_user_id)
        pinned_chats = get_pinned_chats(self.current_user_id)
        records = []
        for contact in contacts:
            chat_id = contact.get("chat_id") if contact["type"] != "employee" else chats.get(contact["id"])
            icon = "⭐" if contact["type"] == "self" else "👥" if contact["type"] == "group" else "👤"
            records.append((contact, chat_id, unread.get(chat_id, 0), icon, chat_id in pinned_chats))
        records.sort(key=lambda row: (-bool(row[4]), -bool(row[2]), row[0]["name"].casefold()))
        self._suppress_selection = True
        self.contacts.clear()
        for contact, chat_id, count, icon, pinned in records:
            marker = "📌 " if pinned else ""
            item = QListWidgetItem(f"{marker}{icon}  {contact['name']}")
            item.setData(Qt.UserRole, contact)
            item.setData(Qt.UserRole + 1, count)
            item.setData(Qt.UserRole + 2, chat_id)
            item.setData(Qt.UserRole + 3, pinned)
            self.contacts.addItem(item)
        self._suppress_selection = False
        self._highlight_current()

    def _contact_selected(self, item, _previous):
        if self._suppress_selection or not item:
            return
        contact = item.data(Qt.UserRole)
        chat_id = item.data(Qt.UserRole + 2)
        if contact["type"] == "employee":
            chat_id = get_or_create_personal_chat(self.current_user_id, contact["id"])
        if chat_id:
            self.open_chat(chat_id, contact["name"], contact["type"], contact.get("id"))

    def open_chat(self, chat_id, name, chat_type, contact_id=None):
        if self.current_chat_id == chat_id:
            return
        self._finish_edit(save=False)
        self.current_chat_id = chat_id
        self.current_chat_type = chat_type
        self.current_contact_id = contact_id
        self.header.setText(name)
        self._message_filter = ""
        self._hide_typing_indicator()
        self.message_search.blockSignals(True)
        self.message_search.clear()
        self.message_search.blockSignals(False)
        self.input.blockSignals(True)
        self.input.clear()
        self.input.clear_screenshots()
        self.input.blockSignals(False)
        self._set_chat_enabled(True)
        mark_notifications_as_read(self.current_user_id, chat_id)
        mark_messages_as_read(chat_id, self.current_user_id)
        draft_text = get_draft(self.current_user_id, chat_id)
        self.input.blockSignals(True)
        self.input.setPlainText(draft_text)
        self.input.blockSignals(False)
        messages = self._prepare_messages(get_chat_messages(chat_id, limit=500))
        self.area.replace_messages(messages, self.current_user_id, self._connect_bubble)
        self.last_message_id = max((message["id"] for message in messages), default=0)
        self._scroll_bottom()
        self._mark_contact_read(chat_id)

    def _mark_contact_read(self, chat_id):
        """Update the visible unread badge without reloading all contacts from the DB."""
        current_item = self.contacts.currentItem()
        for row in range(self.contacts.count()):
            item = self.contacts.item(row)
            if item == current_item or item.data(Qt.UserRole + 2) == chat_id:
                item.setData(Qt.UserRole + 2, chat_id)
                item.setData(Qt.UserRole + 1, 0)
                self.contacts.viewport().update()
                return

    def _connect_bubble(self, bubble):
        bubble.editRequested.connect(self._start_edit)
        bubble.deleteRequested.connect(self.delete_one)
        bubble.stickyRequested.connect(self._create_message_sticky)

    def _create_message_sticky(self, message_id, text):
        open_sticky(self, self.current_user_id, 'message', message_id, 'Сообщение', text)

    def refresh(self):
        if not self.current_chat_id or self._editing_bubble or self._message_filter:
            return
        was_at_bottom = self._at_bottom()
        new_messages = get_new_messages(self.current_chat_id, self.last_message_id)
        if new_messages:
            new_messages = self._prepare_messages(new_messages)
            for message in new_messages:
                self.area.append(message, self.current_user_id, self._connect_bubble)
            self.last_message_id = max(self.last_message_id, *(message["id"] for message in new_messages))
            mark_messages_as_read(self.current_chat_id, self.current_user_id)
            if was_at_bottom:
                self._scroll_bottom()
            self.load_contacts()

    def _prepare_messages(self, messages):
        """Attach all screenshots with one query instead of one query per bubble."""
        attachments = get_message_attachments([message["id"] for message in messages])
        for message in messages:
            message["images"] = attachments.get(message["id"], [])
        return messages

    def _reload_messages(self):
        if self._message_filter:
            messages = search_chat_messages(self.current_chat_id, self._message_filter, limit=500)
        else:
            messages = get_chat_messages(self.current_chat_id, limit=500)
        messages = self._prepare_messages(messages)
        self.area.replace_messages(messages, self.current_user_id, self._connect_bubble)
        if not self._message_filter:
            self.last_message_id = max((message["id"] for message in messages), default=0)
        self._scroll_bottom()

    def search_messages(self, query):
        if not self.current_chat_id:
            return
        self._message_filter = query.strip()
        self._reload_messages()

    def eventFilter(self, watched, event):
        if watched is self.input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
                self.send()
                return True
        return super().eventFilter(watched, event)

    def _sync_draft(self):
        if not self.current_chat_id:
            return
        text = self.input.toPlainText()
        if text.strip():
            save_draft(self.current_user_id, self.current_chat_id, text)
        else:
            delete_draft(self.current_user_id, self.current_chat_id)

    def _handle_typing(self):
        if not self.current_chat_id:
            return
        if self.input.toPlainText().strip():
            self.typing_label.setText("Вы печатаете…")
            self.typing_label.setVisible(True)
            self._typing_timer.start(1600)
        else:
            self._hide_typing_indicator()

    def _hide_typing_indicator(self):
        self.typing_label.setVisible(False)
        self.typing_label.setText("")

    def show_peer_typing(self, name=None):
        if not self.current_chat_id:
            return
        if self.current_chat_type == "group":
            message = "Кто-то печатает…"
        elif name:
            message = f"{name} печатает…"
        else:
            message = "Собеседник печатает…"
        self.peer_typing_label.setText(message)
        self.peer_typing_label.setVisible(True)
        self._peer_typing_timer.start(1800)

    def _hide_peer_typing_indicator(self):
        self.peer_typing_label.setVisible(False)
        self.peer_typing_label.setText("")

    def send(self):
        if not self.current_chat_id:
            return
        text = self.input.toPlainText().strip()
        images = list(self.input.screenshots)
        if not text and not images:
            return
        if send_message(self.current_chat_id, self.current_user_id, text, images):
            self._hide_typing_indicator()
            self._hide_peer_typing_indicator()
            self.input.blockSignals(True)
            self.input.clear()
            self.input.clear_screenshots()
            self.input.blockSignals(False)
            delete_draft(self.current_user_id, self.current_chat_id)
            self.refresh()
            self._scroll_bottom()
        else:
            QMessageBox.warning(self, "Не удалось отправить", "Проверьте подключение к базе данных и повторите попытку.")

    def _start_edit(self, message_id, text):
        self._finish_edit(save=False)
        bubble = self.area.bubbles.get(message_id)
        if not bubble:
            return
        self._editing_bubble = bubble
        editor = QLineEdit(text, objectName="editInput")
        layout = bubble.card.layout()
        body_index = layout.indexOf(bubble.body)
        bubble.body.hide()
        layout.insertWidget(body_index, editor)
        editor.setFocus()
        editor.returnPressed.connect(lambda: self._finish_edit(save=True))
        editor.editingFinished.connect(lambda: self._finish_edit(save=True))
        bubble.editor = editor

    def _finish_edit(self, save):
        bubble = self._editing_bubble
        if not bubble:
            return
        self._editing_bubble = None
        editor = getattr(bubble, "editor", None)
        if not editor:
            return
        text = editor.text().strip()
        bubble.card.layout().removeWidget(editor)
        editor.deleteLater()
        del bubble.editor
        bubble.body.show()
        if save and text and text != bubble.message.get("text"):
            if edit_message(bubble.message_id, text, self.current_user_id):
                bubble.message["text"] = text
                bubble.message["edited_at"] = datetime.now().strftime("%H:%M")
                bubble.refresh(bubble.message)

    def delete_one(self, message_id):
        if QMessageBox.question(self, "Удалить сообщение", "Сообщение будет удалено для всех участников.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if delete_message(message_id, self.current_user_id):
            self._reload_messages()
            self.load_contacts()

    def _selection_changed(self, count):
        show = count > 0
        self.selection_label.setVisible(show)
        self.forward_button.setVisible(show)
        self.delete_button.setVisible(show)
        self.selection_label.setText(f"Выбрано: {count}")
        # Only the author can remove a message; forwarding is available for all.
        own_count = sum(self.area.bubbles[mid].own for mid in self.area.selected_ids if mid in self.area.bubbles)
        self.delete_button.setEnabled(own_count > 0)

    def delete_selected(self):
        ids = [mid for mid in self.area.selected_ids if self.area.bubbles.get(mid) and self.area.bubbles[mid].own]
        if not ids:
            return
        if QMessageBox.question(self, "Удалить сообщения", f"Удалить сообщений: {len(ids)}?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        for message_id in ids:
            delete_message(message_id, self.current_user_id)
        self.area.clear_selection()
        self._reload_messages()
        self.load_contacts()

    def forward_selected(self):
        ids = sorted(self.area.selected_ids)
        if not ids:
            return
        dialog = ForwardChatDialog(self.current_user_id, self.current_chat_id, self)
        if dialog.exec() != QDialog.Accepted:
            return
        target = dialog.selected_chat_id()
        if not target:
            return
        payload = []
        for message_id in ids:
            bubble = self.area.bubbles.get(message_id)
            if bubble and not bubble.message.get("is_deleted"):
                payload.append({"id": message_id, "text": bubble.message.get("text", ""), "sender_name": bubble.message.get("sender_name", ""), "time": bubble.message.get("time", "")})
        if payload and forward_messages(target, self.current_user_id, payload):
            self.area.clear_selection()
        elif payload:
            QMessageBox.warning(self, "Не удалось переслать", "Сообщения не были отправлены.")

    def create_group_chat(self):
        dialog = GroupChatDialog(self.current_user_id, self)
        if dialog.exec() != QDialog.Accepted:
            return
        members = dialog.selected_ids()
        if not members:
            QMessageBox.information(self, "Новая группа", "Выберите хотя бы одного участника.")
            return
        result = create_group_chat_auto(self.current_user_id, [self.current_user_id, *members])
        if result and result[0]:
            chat_id, name = result
            self.load_contacts()
            self.open_chat(chat_id, name, "group")

    def _contact_menu(self, position):
        item = self.contacts.itemAt(position)
        if not item:
            return
        contact = item.data(Qt.UserRole)
        chat_id = item.data(Qt.UserRole + 2)
        if not chat_id:
            return
        menu = QMenu(self)
        pinned = bool(item.data(Qt.UserRole + 3))
        pin_action = menu.addAction("Открепить чат" if pinned else "Закрепить чат")
        pin_action.triggered.connect(lambda: self._toggle_pin(chat_id, pinned))
        if contact.get("type") == "group" and contact.get("created_by") == self.current_user_id:
            menu.addSeparator()
        action = menu.addAction("Удалить группу")
        action.triggered.connect(lambda: self._delete_group(contact["chat_id"]))
        action.setVisible(contact.get("type") == "group" and contact.get("created_by") == self.current_user_id)
        menu.exec(self.contacts.viewport().mapToGlobal(position))

    def _toggle_pin(self, chat_id, pinned):
        changed = unpin_chat(self.current_user_id, chat_id) if pinned else pin_chat(self.current_user_id, chat_id)
        if changed:
            self.load_contacts()

    def _delete_group(self, chat_id):
        if QMessageBox.question(self, "Удалить группу", "Группа и её сообщения будут удалены без возможности восстановления.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if delete_group_chat(chat_id, self.current_user_id):
            if self.current_chat_id == chat_id:
                self.current_chat_id = None
                self.header.setText("Выберите чат")
                self.area.clear()
                self._set_chat_enabled(False)
            self.load_contacts()

    def _highlight_current(self):
        if not self.current_chat_id:
            return
        for row in range(self.contacts.count()):
            item = self.contacts.item(row)
            if item.data(Qt.UserRole + 2) == self.current_chat_id:
                self._suppress_selection = True
                self.contacts.setCurrentItem(item)
                self._suppress_selection = False
                return

    def open_chat_by_id(self, chat_id):
        """Open a chat selected from an application notification."""
        for row in range(self.contacts.count()):
            item = self.contacts.item(row)
            if item.data(Qt.UserRole + 2) == chat_id:
                self.contacts.setCurrentItem(item)
                return
        # A personal chat can be absent from a filtered list only; reset search and retry.
        if self.search.text():
            self.search.clear()
            self.open_chat_by_id(chat_id)

    def open_message_by_id(self, chat_id, message_id):
        """Open the source chat and bring a linked message into view."""
        self.open_chat_by_id(chat_id)

        def reveal():
            bubble = self.area.bubbles.get(message_id)
            if not bubble:
                return
            self.area.ensureWidgetVisible(bubble, 20, 40)
            bubble.setProperty('sourceTarget', True)
            bubble.style().unpolish(bubble); bubble.style().polish(bubble)
            QTimer.singleShot(1800, lambda: self._clear_source_target(bubble))

        QTimer.singleShot(0, reveal)

    @staticmethod
    def _clear_source_target(bubble):
        if bubble:
            bubble.setProperty('sourceTarget', False)
            bubble.style().unpolish(bubble); bubble.style().polish(bubble)

    def _at_bottom(self):
        bar = self.area.verticalScrollBar()
        return bar.value() >= bar.maximum() - 24

    def _scroll_bottom(self):
        QTimer.singleShot(0, lambda: self.area.verticalScrollBar().setValue(self.area.verticalScrollBar().maximum()))
