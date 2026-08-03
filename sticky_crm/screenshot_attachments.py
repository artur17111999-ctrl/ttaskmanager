"""Screenshot paste support."""

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QWidget


class ScreenshotTextEdit(QTextEdit):
    screenshotsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.screenshots = []

    def insertFromMimeData(self, source):
        if source.hasImage():
            image = source.imageData()
            if isinstance(image, QPixmap):
                image = image.toImage()
            if isinstance(image, QImage) and not image.isNull():
                data = QByteArray()
                buffer = QBuffer(data)
                buffer.open(QIODevice.WriteOnly)
                image.save(buffer, "PNG")
                buffer.close()
                self.screenshots.append(bytes(data))
                self.screenshotsChanged.emit()
                return
        super().insertFromMimeData(source)

    def clear_screenshots(self):
        self.screenshots.clear()
        self.screenshotsChanged.emit()


class ScreenshotPreview(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setObjectName("screenshotPreview")
        self.label = QLabel()
        self.label.setObjectName("screenshotPreviewLabel")
        self.remove_button = QPushButton("Очистить")
        self.remove_button.setObjectName("clearScreenshotsButton")
        self.remove_button.clicked.connect(editor.clear_screenshots)
        layout.addWidget(self.label)
        layout.addWidget(self.remove_button)
        layout.addStretch()
        editor.screenshotsChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        count = len(self.editor.screenshots)
        self.label.setText(
            f"Прикреплено скриншотов: {count}"
            if count else "Вставьте скриншот: Ctrl+V"
        )
        self.remove_button.setVisible(bool(count))


def add_image_previews(layout, images, max_width=320):
    """Add thumbnails that preserve their aspect ratio and never enlarge an image."""
    for data in images:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            label = QLabel()
            label.setObjectName("screenshotAttachment")
            if pixmap.width() > max_width:
                pixmap = pixmap.scaledToWidth(max_width, Qt.SmoothTransformation)
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignLeft)
            layout.addWidget(label)
