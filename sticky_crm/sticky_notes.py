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
        self.setFixedSize(340, 274)
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
        self.save_button = QPushButton('▣'); self.save_button.setObjectName('stickySave'); self.save_button.setToolTip('Сохранить'); self.save_button.clicked.connect(self.save); header.addSpacing(2); header.addWidget(self.save_button)
        self.minimize_button = QPushButton('−'); self.minimize_button.setObjectName('stickyMinimize'); self.minimize_button.setToolTip('Свернуть'); self.minimize_button.clicked.connect(self.showMinimized); header.addWidget(self.minimize_button)
        self.close_button = QPushButton('×'); self.close_button.setObjectName('stickyClose'); self.close_button.setToolTip('Закрыть'); self.close_button.clicked.connect(self.close); header.addWidget(self.close_button)
        header_frame = QFrame(); header_frame.setObjectName('stickyHeader'); header_frame.setLayout(header)
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
        layout.addWidget(footer_frame)
        self._apply_mode()
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.color.currentIndexChanged.connect(self._apply_color)
        self._apply_color()

    def _apply_color(self):
        self.setProperty('stickyColor', self.color.currentData())
        self.setProperty('stickyColorKey', {
            '#fca5a5': 'red', '#fef3a5': 'yellow', '#bbf7d0': 'green', '#d1d5db': 'grey'
        }.get(self.color.currentData(), 'yellow'))
        for button in self.color_buttons:
            button.setProperty('active', button.property('colorKey') == self.property('stickyColorKey'))
            button.style().unpolish(button); button.style().polish(button)
        self.style().unpolish(self); self.style().polish(self)

    def _cycle_mode(self):
        index = (self.mode.currentIndex() + 1) % self.mode.count()
        self.mode.setCurrentIndex(index)
        self.level_button.setText(f'📌 {index + 1}')

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

    def _mode_changed(self):
        self._apply_mode()
        if self.sticky_id is not None:
            update_sticky(self.sticky_id, self.user_id, self.title_edit.text(),
                          self.text_edit.toPlainText(), self.color.currentData(), self.mode.currentData())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 42 and self.mode.currentData().endswith('movable'):
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
    note.destroyed.connect(lambda _, n=note: OPEN_STICKIES.remove(n) if n in OPEN_STICKIES else None)
    note.show(); note.raise_(); return note


def restore_stickies(user_id):
    notes = []
    for sticky in get_user_stickies(user_id):
        note = StickyNoteWidget(user_id, sticky['source_type'], sticky['source_id'],
                                sticky['title'], sticky['text'], sticky['color'],
                                sticky['pin_mode'], sticky['id'])
        OPEN_STICKIES.append(note)
        note.destroyed.connect(lambda _, n=note: OPEN_STICKIES.remove(n) if n in OPEN_STICKIES else None)
        note.show()
        notes.append(note)
    return notes
