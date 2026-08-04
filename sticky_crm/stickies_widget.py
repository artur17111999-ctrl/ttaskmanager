from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from db import delete_sticky, get_stickies_overview, set_sticky_state, update_sticky
from sticky_notes import OPEN_STICKIES, apply_sticky_record, get_open_sticky


COLORS = [
    ('Красный', '#fca5a5'), ('Жёлтый', '#fef3a5'),
    ('Зелёный', '#bbf7d0'), ('Серый', '#d1d5db'),
]
PIN_MODES = [
    ('1 · обычный, подвижный', 'bottom_movable'),
    ('2 · обычный, закреплённый', 'bottom_locked'),
    ('3 · поверх окон, подвижный', 'top_movable'),
    ('4 · поверх окон, закреплённый', 'top_locked'),
]


class StickiesWidget(QWidget):
    openTaskRequested = Signal(int)
    openMessageRequested = Signal(int, int)

    def __init__(self, current_user_id, parent=None):
        super().__init__(parent)
        self.current_user_id = current_user_id
        self.settings = QSettings('StickyCRM', 'StickiesList')
        self.records = []
        self._build_ui()
        self._restore_settings()
        self.reload()

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(20, 18, 20, 20); root.setSpacing(12)
        filters = QHBoxLayout(); filters.setSpacing(8)
        self.search = QLineEdit(); self.search.setObjectName('stickiesSearch'); self.search.setPlaceholderText('Поиск по тексту стикера...')
        self.source_filter = QComboBox(); self.source_filter.addItem('Все источники', 'all'); self.source_filter.addItem('Задачи', 'task'); self.source_filter.addItem('Сообщения', 'message')
        self.visibility_filter = QComboBox(); self.visibility_filter.addItem('Видимые', 'visible'); self.visibility_filter.addItem('Скрытые', 'hidden'); self.visibility_filter.addItem('Архив', 'archived'); self.visibility_filter.addItem('Все', 'all')
        self.group_filter = QComboBox(); self.group_filter.addItem('Группировать по источнику', True); self.group_filter.addItem('Без группировки', False)
        self.sort_filter = QComboBox(); self.sort_filter.addItem('Изменены недавно', 'updated_desc'); self.sort_filter.addItem('Сначала новые', 'created_desc'); self.sort_filter.addItem('Сначала старые', 'created_asc'); self.sort_filter.addItem('По пину', 'pin')
        refresh = QPushButton('Обновить'); refresh.setObjectName('stickiesRefresh'); refresh.clicked.connect(self.reload)
        for widget in (self.search, self.source_filter, self.visibility_filter, self.group_filter, self.sort_filter):
            filters.addWidget(widget)
        filters.addWidget(refresh); root.addLayout(filters)
        self.search.textChanged.connect(self._filters_changed)
        for combo in (self.source_filter, self.visibility_filter, self.group_filter, self.sort_filter): combo.currentIndexChanged.connect(self._filters_changed)

        self.scroll = QScrollArea(); self.scroll.setObjectName('stickiesScroll'); self.scroll.setWidgetResizable(True); self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.container = QWidget(); self.container.setObjectName('stickiesContainer')
        self.cards_layout = QVBoxLayout(self.container); self.cards_layout.setContentsMargins(0, 0, 0, 0); self.cards_layout.setSpacing(9)
        self.scroll.setWidget(self.container); root.addWidget(self.scroll, 1)

    def _restore_settings(self):
        self.search.setText(self.settings.value('search', '', str))
        for combo, key in ((self.source_filter, 'source'), (self.visibility_filter, 'visibility'), (self.sort_filter, 'sort')):
            index = combo.findData(self.settings.value(key, combo.itemData(0)))
            combo.setCurrentIndex(max(0, index))
        grouped = self.settings.value('grouped', True, bool)
        self.group_filter.setCurrentIndex(max(0, self.group_filter.findData(grouped)))

    def _filters_changed(self):
        self.settings.setValue('search', self.search.text())
        self.settings.setValue('source', self.source_filter.currentData())
        self.settings.setValue('visibility', self.visibility_filter.currentData())
        self.settings.setValue('grouped', self.group_filter.currentData())
        self.settings.setValue('sort', self.sort_filter.currentData())
        self.render()

    def reload(self):
        self.records = get_stickies_overview(self.current_user_id)
        self.render()

    def _filtered(self):
        query = self.search.text().strip().lower(); source = self.source_filter.currentData(); visibility = self.visibility_filter.currentData()
        rows = []
        for record in self.records:
            if source != 'all' and record['source_type'] != source: continue
            state = 'archived' if record['is_archived'] else ('hidden' if record['is_hidden'] else 'visible')
            if visibility != 'all' and state != visibility: continue
            haystack = ' '.join(str(record.get(key) or '') for key in ('title', 'text', 'task_title', 'message_text')).lower()
            if query and query not in haystack: continue
            rows.append(record)
        sort = self.sort_filter.currentData()
        if sort == 'created_desc': rows.sort(key=lambda r: r['created_at'], reverse=True)
        elif sort == 'created_asc': rows.sort(key=lambda r: r['created_at'])
        elif sort == 'pin': rows.sort(key=lambda r: PIN_MODES.index(next(item for item in PIN_MODES if item[1] == r['pin_mode'])))
        else: rows.sort(key=lambda r: r['updated_at'], reverse=True)
        return rows

    def _clear(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def render(self):
        self._clear(); rows = self._filtered()
        if not rows:
            empty = QLabel('Стики не найдены'); empty.setObjectName('stickiesEmpty'); empty.setAlignment(Qt.AlignCenter); self.cards_layout.addWidget(empty); self.cards_layout.addStretch(); return
        if self.group_filter.currentData():
            for source_type, heading in (('task', 'Из задач'), ('message', 'Из сообщений'), ('other', 'Другие')):
                group = [r for r in rows if (r['source_type'] == source_type if source_type != 'other' else r['source_type'] not in ('task', 'message'))]
                if not group: continue
                label = QLabel(heading); label.setObjectName('stickiesGroupTitle'); self.cards_layout.addWidget(label)
                for record in group: self.cards_layout.addWidget(self._create_card(record))
        else:
            for record in rows: self.cards_layout.addWidget(self._create_card(record))
        self.cards_layout.addStretch()

    def _create_card(self, record):
        card = QFrame(); card.setObjectName('stickyListCard'); card.setProperty('sourceType', record['source_type'])
        layout = QVBoxLayout(card); layout.setContentsMargins(14, 12, 14, 12); layout.setSpacing(8)
        top = QHBoxLayout()
        source_text, source_status = self._source_summary(record)
        source = QPushButton(source_text); source.setObjectName('stickySourceLink'); source.setToolTip(source_status); source.clicked.connect(lambda: self._open_source(record)); top.addWidget(source, 1)
        status = QLabel(source_status); status.setObjectName('stickySourceStatus'); top.addWidget(status)
        dates = QLabel(f"Создан: {record['created_at']:%d.%m.%Y %H:%M}  ·  Изменён: {record['updated_at']:%d.%m.%Y %H:%M}"); dates.setObjectName('stickyDates'); top.addWidget(dates)
        layout.addLayout(top)

        text = QTextEdit(record['text']); text.setObjectName('stickyListText'); text.setFixedHeight(72); layout.addWidget(text)
        text_timer = QTimer(card); text_timer.setSingleShot(True); text_timer.setInterval(650)
        text_timer.timeout.connect(lambda r=record, e=text: self._save_record(r, text=e.toPlainText()))
        text.textChanged.connect(text_timer.start)

        controls = QHBoxLayout(); controls.setSpacing(8)
        color = QComboBox(); color.setObjectName('stickyListColor')
        for label, value in COLORS: color.addItem(label, value)
        color.setCurrentIndex(max(0, color.findData(record['color']))); color.currentIndexChanged.connect(lambda _, r=record, c=color: self._save_record(r, color=c.currentData())); controls.addWidget(color)
        pin = QComboBox(); pin.setObjectName('stickyListPin')
        for label, value in PIN_MODES: pin.addItem(label, value)
        pin.setCurrentIndex(max(0, pin.findData(record['pin_mode']))); pin.currentIndexChanged.connect(lambda _, r=record, p=pin: self._save_record(r, pin=p.currentData())); controls.addWidget(pin)
        controls.addStretch()
        if record['is_hidden'] or record['is_archived']:
            restore = QPushButton('Восстановить'); restore.setObjectName('stickyRestore'); restore.clicked.connect(lambda: self._restore(record)); controls.addWidget(restore)
        else:
            hide = QPushButton('Скрыть'); hide.setObjectName('stickyHide'); hide.clicked.connect(lambda: self._set_state(record, hidden=True)); controls.addWidget(hide)
        if not record['is_archived']:
            archive = QPushButton('Архивировать'); archive.setObjectName('stickyArchive'); archive.clicked.connect(lambda: self._set_state(record, archived=True, hidden=False)); controls.addWidget(archive)
        delete = QPushButton('Удалить навсегда'); delete.setObjectName('stickyDelete'); delete.clicked.connect(lambda: self._delete(record)); controls.addWidget(delete)
        layout.addLayout(controls); return card

    def _source_summary(self, record):
        if record['source_type'] == 'task':
            if not record['task_title']: return f"Задача #{record['source_id']}", 'Задача удалена'
            return f"Задача #{record['source_id']}: {record['task_title']}", record['task_status'] or 'Без статуса'
        if record['source_type'] == 'message':
            if record['message_text'] is None: return f"Сообщение #{record['source_id']}", 'Сообщение не найдено'
            preview = record['message_text'].replace('\n', ' ')[:90]
            return f"Сообщение #{record['source_id']}: {preview}", 'Сообщение удалено' if record['message_deleted'] else 'Сообщение доступно'
        return f"Источник {record['source_type']} #{record['source_id']}", 'Источник недоступен для перехода'

    def _save_record(self, record, text=None, color=None, pin=None):
        if text is not None: record['text'] = text
        if color is not None: record['color'] = color
        if pin is not None: record['pin_mode'] = pin
        geometry = (record['pos_x'], record['pos_y'], record['width'], record['height'])
        update_sticky(record['id'], self.current_user_id, record['title'], record['text'], record['color'], record['pin_mode'], geometry)
        note = get_open_sticky(record['id'])
        if note:
            if text is not None and note.text_edit.toPlainText() != text: note.text_edit.setPlainText(text)
            if color is not None: note.color.setCurrentIndex(note.color.findData(color))
            if pin is not None: note.mode.setCurrentIndex(note.mode.findData(pin))

    def _set_state(self, record, hidden=None, archived=None):
        if set_sticky_state(record['id'], self.current_user_id, hidden=hidden, archived=archived):
            note = get_open_sticky(record['id'])
            if note: note.hide()
            self.reload()

    def _restore(self, record):
        if set_sticky_state(record['id'], self.current_user_id, hidden=False, archived=False):
            record['is_hidden'] = False; record['is_archived'] = False
            apply_sticky_record(record); self.reload()

    def _delete(self, record):
        answer = QMessageBox.question(self, 'Удаление стика', 'Удалить этот стик навсегда? Отменить действие будет невозможно.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes: return
        note = get_open_sticky(record['id'])
        if note:
            note._save_timer.stop(); OPEN_STICKIES.remove(note) if note in OPEN_STICKIES else None; note.deleteLater()
        if delete_sticky(record['id'], self.current_user_id): self.reload()

    def _open_source(self, record):
        if record['source_type'] == 'task' and record['task_title']:
            self.openTaskRequested.emit(record['source_id'])
        elif record['source_type'] == 'message' and record['chat_id']:
            self.openMessageRequested.emit(record['chat_id'], record['source_id'])
