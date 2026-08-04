from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QTextEdit, QVBoxLayout, QWidget

from db import create_sticky, update_sticky, get_user_stickies

OPEN_STICKIES = []


class StickyNoteWidget(QFrame):
    """A persistent desktop note with four explicit top/bottom and movable/locked modes."""
    MODES = [('bottom_movable', 'Позади окон · перемещать'), ('bottom_locked', 'Позади окон · зафиксировать'),
             ('top_movable', 'Поверх окон · перемещать'), ('top_locked', 'Поверх окон · зафиксировать')]

    def __init__(self, user_id, source_type, source_id, title='', text='', color='#fef3a5', pin_mode='bottom_movable', sticky_id=None, parent=None):
        super().__init__(parent)
        self.user_id, self.source_type, self.source_id, self.sticky_id = user_id, source_type, source_id, sticky_id
        self._drag_pos = None
        self.setWindowTitle('Стик')
        self.setObjectName('stickyNote')
        self.setMinimumSize(260, 220)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title_edit = QLineEdit(title)
        self.title_edit.setPlaceholderText('Заголовок')
        self.mode = QComboBox()
        for value, label in self.MODES: self.mode.addItem(label, value)
        self.mode.setCurrentIndex(max(0, self.mode.findData(pin_mode)))
        header.addWidget(self.title_edit, 1); header.addWidget(self.mode)
        layout.addLayout(header)
        source_label = QLabel(f"Источник: {source_type} #{source_id}")
        source_label.setObjectName('stickySource')
        layout.addWidget(source_label)
        self.text_edit = QTextEdit(text)
        layout.addWidget(self.text_edit, 1)
        self.color = QComboBox()
        for value, label in [('#fca5a5','Красный'),('#fef3a5','Жёлтый'),('#bbf7d0','Зелёный'),('#d1d5db','Серый')]: self.color.addItem(label, value)
        self.color.setCurrentIndex(max(0, self.color.findData(color)))
        buttons = QHBoxLayout(); buttons.addWidget(self.color)
        save = QPushButton('Сохранить'); save.clicked.connect(self.save); buttons.addWidget(save)
        close = QPushButton('Закрыть'); close.clicked.connect(self.close); buttons.addWidget(close)
        layout.addLayout(buttons)
        self._apply_mode()
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.color.currentIndexChanged.connect(lambda: self.setStyleSheet(f"QFrame#stickyNote {{ background: {self.color.currentData()}; }}"))
        self.setStyleSheet(f"QFrame#stickyNote {{ background: {color}; border: 1px solid #6b7280; }}")

    def _apply_mode(self):
        mode = self.mode.currentData()
        flags = Qt.Tool | (Qt.WindowStaysOnTopHint if mode.startswith('top') else Qt.WindowStaysOnBottomHint)
        self.setWindowFlags(flags | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setEnabled(True)
        self.show()

    def save(self):
        values = (self.title_edit.text(), self.text_edit.toPlainText(), self.color.currentData(), self.mode.currentData())
        if self.sticky_id is None:
            self.sticky_id = create_sticky(self.user_id, self.source_type, self.source_id, *values)
        else:
            update_sticky(self.sticky_id, self.user_id, *values)
        self._apply_mode()

    def _mode_changed(self):
        self._apply_mode()
        if self.sticky_id is not None:
            update_sticky(self.sticky_id, self.user_id, self.title_edit.text(),
                          self.text_edit.toPlainText(), self.color.currentData(), self.mode.currentData())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.mode.currentData().endswith('movable'):
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft(); event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None: self.move(event.globalPosition().toPoint() - self._drag_pos); event.accept(); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None; super().mouseReleaseEvent(event)


def open_sticky(parent, user_id, source_type, source_id, title, text, color='#fef3a5'):
    # Notes are independent desktop windows and must survive hiding the main window.
    note = StickyNoteWidget(user_id, source_type, source_id, title, text, color)
    OPEN_STICKIES.append(note)
    note.show(); note.raise_(); return note


def restore_stickies(user_id):
    notes = []
    for sticky in get_user_stickies(user_id):
        note = StickyNoteWidget(user_id, sticky['source_type'], sticky['source_id'],
                                sticky['title'], sticky['text'], sticky['color'],
                                sticky['pin_mode'], sticky['id'])
        OPEN_STICKIES.append(note)
        note.show()
        notes.append(note)
    return notes
