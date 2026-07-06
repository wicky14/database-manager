from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPainter, QColor, QFont, QPen


class SpinnerOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._text = "Loading..."
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setVisible(False)

    def set_text(self, text: str):
        self._text = text

    def showEvent(self, event):
        self._angle = 0
        self._timer.start(30)
        if self.parent():
            self.resize(self.parent().size())
            self.raise_()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _rotate(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        if not self.parent():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        cx = self.width() // 2
        cy = self.height() // 2
        radius = 18

        pen = QPen(QColor("#4a9eff"), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        painter.drawArc(cx - radius, cy - radius - 10, radius * 2, radius * 2,
                        self._angle * 16, 270 * 16)

        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(cx - 40, cy + radius + 20, 80, 20,
                         Qt.AlignmentFlag.AlignCenter, self._text)

        painter.end()
