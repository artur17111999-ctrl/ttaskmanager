from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QStyle, QTextEdit, QVBoxLayout

from db import create_sticky, update_sticky, get_user_stickies

OPEN_STICKIES = []


class StickyNoteWidget(QFrame):
    """A persistent desktop note with four explicit top/bottom and movable/locked modes."""
    MODES = [('bottom_movable', 'Позади окон · перемещать'), ('bottom_locked', 'Позади окон · зафиксировать'),
             ('top_movable', 'Поверх окон · перемещать'), ('top_locked', 'Поверх окон · зафиксировать')]

    def __init__(self, user_id, source_type, source_id, title='', text='', color='#fef3a5', pin_mode='bottom_movable', sticky_id=None, geometry=None, parent=None):
        super().__init__(parent)
        self.user_id, self.source_type, self.source_id, self.sticky_id = user_id, source_type, source_id, sticky_id
        self._drag_pos = None
        self._resize_edges = None
        self._resize_start_geometry = None
        self._ready = False
        self._save_timer = QTimer(self); self._save_timer.setSingleShot(True); self._save_timer.setInterval(700); self._save_timer.timeout.connect(self.save)
        self._icon_timer = QTimer(self); self._icon_timer.setSingleShot(True); self._icon_timer.timeout.connect(self._restore_save_icon)
        self.setWindowTitle('Стик')
        self.setObjectName('stickyNote')
        self.setMinimumSize(300, 220)
        if geometry and geometry[0] is not None and geometry[1] is not None:
            self.setGeometry(*geometry)
        else:
            self.resize(340, 274)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 6, 0)
        header.setSpacing(4)
        self.title_edit = QLineEdit(title)
        self.title_edit.setObjectName('stickyTitle')
        self.title_edit.setReadOnly(True)
        self.title_edit.setPlaceholderText('Заголовок')
        self.mode = QComboBox()
        self.mode.setObjectName('stickyMode')
        for value, label in self.MODES: self.mode.addItem(label, value)
        self.mode.setCurrentIndex(max(0, self.mode.findData(pin_mode)))
        self.mode.setVisible(False)
        header.addWidget(self.title_edit, 1); header.addWidget(self.mode)
        self.save_button = QPushButton(); self.save_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton)); self.save_button.setObjectName('stickySave'); self.save_button.setToolTip('Сохранить'); self.save_button.clicked.connect(self.save); header.addSpacing(2); header.addWidget(self.save_button)
        self.minimize_button = QPushButton(); self.minimize_button.setIcon(self.style().standardIcon(QStyle.SP_TitleBarMinButton)); self.minimize_button.setObjectName('stickyMinimize'); self.minimize_button.setToolTip('Свернуть'); self.minimize_button.clicked.connect(self.showMinimized); header.addWidget(self.minimize_button)
        self.close_button = QPushButton(); self.close_button.setIcon(self.style().standardIcon(QStyle.SP_TitleBarCloseButton)); self.close_button.setObjectName('stickyClose'); self.close_button.setToolTip('Закрыть'); self.close_button.clicked.connect(self.close); header.addWidget(self.close_button)
        for button in (self.save_button, self.minimize_button, self.close_button):
            button.setIconSize(QSize(18, 18))
        header_frame = QFrame(); header_frame.setObjectName('stickyHeader'); header_frame.setLayout(header)
        self.header_frame = header_frame
        self.header_frame.installEventFilter(self)
        self.title_edit.installEventFilter(self)
        layout.addWidget(header_frame)
        source_label = QLabel(f"Источник: {source_type} #{source_id}")
        source_label.setObjectName('stickySource')
        layout.addWidget(source_label)
        self.text_edit = QTextEdit(text)
        self.text_edit.setObjectName('stickyText')
        layout.addWidget(self.text_edit, 1)
        self.color = QComboBox()
        for value, label in [('#fca5a5','Красный'),('#fef3a5','Жёлтый'),('#bbf7d0','Зелёный'),('#d1d5db','Серый')]: self.color.addItem(label, value)
        self.color.setCurrentIndex(max(0, self.color.findData(color)))
        self.color.setObjectName('stickyColor')
        self.color.setFixedWidth(1)
        self.color.setVisible(False)
        buttons = QHBoxLayout(); buttons.setContentsMargins(6, 0, 6, 0)
        self.color_buttons = []
        for key, value in [('red', '#fca5a5'), ('yellow', '#fef3a5'), ('green', '#bbf7d0'), ('grey', '#d1d5db')]:
            button = QPushButton(); button.setObjectName('color_' + key); button.setProperty('colorKey', key); button.setFixedSize(22, 22)
            button.clicked.connect(lambda _, v=value: self.color.setCurrentIndex(self.color.findData(v)))
            buttons.addWidget(button); self.color_buttons.append(button)
        buttons.addStretch()
        self.level_button = QPushButton(f'📌 {self.mode.currentIndex() + 1}'); self.level_button.setObjectName('stickyLevel'); self.level_button.clicked.connect(self._cycle_mode); buttons.addWidget(self.level_button)
        footer_frame = QFrame(); footer_frame.setObjectName('stickyFooter'); footer_frame.setLayout(buttons)
        self.footer_frame = footer_frame
        layout.addWidget(footer_frame)
        self._apply_mode()
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.color.currentIndexChanged.connect(self._apply_color)
        self._apply_color()
        self.text_edit.textChanged.connect(self._schedule_save)
        for widget in (self, self.header_frame, self.title_edit, self.text_edit, self.footer_frame):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)
        self._ready = True

    def _apply_color(self):
        self.setProperty('stickyColor', self.color.currentData())
        self.setProperty('stickyColorKey', {
            '#fca5a5': 'red', '#fef3a5': 'yellow', '#bbf7d0': 'green', '#d1d5db': 'grey'
        }.get(self.color.currentData(), 'yellow'))
        for button in self.color_buttons:
            button.setProperty('active', button.property('colorKey') == self.property('stickyColorKey'))
            button.style().unpolish(button); button.style().polish(button)
        self.style().unpolish(self); self.style().polish(self)
        self._schedule_save()

    def _cycle_mode(self):
        index = (self.mode.currentIndex() + 1) % self.mode.count()
        self.mode.setCurrentIndex(index)
        self.level_button.setText(f'📌 {index + 1}')

    def _apply_mode(self):
        mode = self.mode.currentData()
        flags = Qt.Tool
        if mode.startswith('top'):
            flags |= Qt.WindowStaysOnTopHint
        position = self.pos()
        self.setWindowFlags(flags | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setEnabled(True)
        self.move(position)
        self.show()

    def save(self):
        geometry = (self.x(), self.y(), self.width(), self.height())
        values = (self.title_edit.text(), self.text_edit.toPlainText(), self.color.currentData(), self.mode.currentData(), geometry)
        if self.sticky_id is None:
            self.sticky_id = create_sticky(self.user_id, self.source_type, self.source_id, *values)
        else:
            update_sticky(self.sticky_id, self.user_id, *values)
        if self.sticky_id is not None:
            self.save_button.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
            self._icon_timer.start(900)

    def _restore_save_icon(self):
        self.save_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))

    def _schedule_save(self):
        if self._ready:
            self._save_timer.start()

    def _mode_changed(self):
        self._apply_mode()
        if self.sticky_id is not None:
            self._schedule_save()

    def _resize_edges_at(self, position):
        margin = 6
        edges = []
        if position.x() <= margin: edges.append('left')
        elif position.x() >= self.width() - margin: edges.append('right')
        if position.y() <= margin: edges.append('top')
        elif position.y() >= self.height() - margin: edges.append('bottom')
        return tuple(edges)

    def _update_resize_cursor(self, edges):
        cursors = {
            ('left',): Qt.SizeHorCursor, ('right',): Qt.SizeHorCursor,
            ('top',): Qt.SizeVerCursor, ('bottom',): Qt.SizeVerCursor,
            ('left', 'top'): Qt.SizeFDiagCursor, ('right', 'bottom'): Qt.SizeFDiagCursor,
            ('right', 'top'): Qt.SizeBDiagCursor, ('left', 'bottom'): Qt.SizeBDiagCursor,
        }
        self.setCursor(cursors.get(edges, Qt.ArrowCursor))

    def _resize_from_global(self, global_position):
        geometry = self._resize_start_geometry
        delta = global_position - self._resize_start_pos
        left, top, right, bottom = geometry.left(), geometry.top(), geometry.right(), geometry.bottom()
        if 'left' in self._resize_edges: left += delta.x()
        if 'right' in self._resize_edges: right += delta.x()
        if 'top' in self._resize_edges: top += delta.y()
        if 'bottom' in self._resize_edges: bottom += delta.y()
        minimum = self.minimumSize()
        if right - left + 1 < minimum.width():
            left = right - minimum.width() + 1 if 'left' in self._resize_edges else left
            right = left + minimum.width() - 1 if 'right' in self._resize_edges else right
        if bottom - top + 1 < minimum.height():
            top = bottom - minimum.height() + 1 if 'top' in self._resize_edges else top
            bottom = top + minimum.height() - 1 if 'bottom' in self._resize_edges else bottom
        self.setGeometry(left, top, right - left + 1, bottom - top + 1)

    def eventFilter(self, watched, event):
        if not hasattr(self, 'text_edit') or not hasattr(self, 'footer_frame'):
            return super().eventFilter(watched, event)
        if watched in (self, self.header_frame, self.title_edit, self.text_edit, self.footer_frame):
            position = self.mapFromGlobal(event.globalPosition().toPoint()) if hasattr(event, 'globalPosition') else None
            if event.type() == QEvent.MouseMove and self._resize_edges:
                self._resize_from_global(event.globalPosition().toPoint())
                return True
            if position is not None and event.type() == QEvent.MouseMove:
                self._update_resize_cursor(self._resize_edges_at(position))
            if position is not None and event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                edges = self._resize_edges_at(position)
                if edges:
                    self._resize_edges = edges
                    self._resize_start_geometry = self.geometry()
                    self._resize_start_pos = event.globalPosition().toPoint()
                    return True
            if event.type() == QEvent.MouseButtonRelease and self._resize_edges:
                self._resize_edges = None
                self._resize_start_geometry = None
                self._schedule_save()
                return True
        if watched in (self.header_frame, self.title_edit) and self.mode.currentData().endswith('movable'):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft(); return True
            if event.type() == QEvent.MouseMove and self._drag_pos is not None:
                self.move(event.globalPosition().toPoint() - self._drag_pos); return True
            if event.type() == QEvent.MouseButtonRelease:
                self._drag_pos = None; self._schedule_save(); return True
        return super().eventFilter(watched, event)

    def moveEvent(self, event):
        super().moveEvent(event); self._schedule_save()

    def resizeEvent(self, event):
        super().resizeEvent(event); self._schedule_save()

    def closeEvent(self, event):
        self._save_timer.stop(); self.save()
        if self in OPEN_STICKIES: OPEN_STICKIES.remove(self)
        event.accept()


def open_sticky(parent, user_id, source_type, source_id, title, text, color='#fef3a5'):
    # Notes are independent desktop windows and must survive hiding the main window.
    note = StickyNoteWidget(user_id, source_type, source_id, title, text, color)
    OPEN_STICKIES.append(note)
    note.destroyed.connect(lambda _, n=note: OPEN_STICKIES.remove(n) if n in OPEN_STICKIES else None)
    note.show(); note.raise_(); return note


def restore_stickies(user_id):
    notes = []
    for sticky in get_user_stickies(user_id):
        note = StickyNoteWidget(user_id, sticky['source_type'], sticky['source_id'],
                                sticky['title'], sticky['text'], sticky['color'],
                                sticky['pin_mode'], sticky['id'],
                                (sticky['pos_x'], sticky['pos_y'], sticky['width'], sticky['height']))
        OPEN_STICKIES.append(note)
        note.destroyed.connect(lambda _, n=note: OPEN_STICKIES.remove(n) if n in OPEN_STICKIES else None)
        note.show()
        notes.append(note)
    return notes
