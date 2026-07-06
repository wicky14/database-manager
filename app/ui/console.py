from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout, QLabel, QTabWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from datetime import datetime


class ConsolePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        title = QLabel("Execution Log")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        header.addWidget(title)
        header.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self.clear_log)
        header.addWidget(clear_btn)

        layout.addLayout(header)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setWordWrap(True)
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        layout.addWidget(self._list)

    def show_panel(self):
        parent = self.parent()
        if isinstance(parent, QTabWidget):
            idx = parent.indexOf(self)
            if idx >= 0:
                parent.setCurrentIndex(idx)

    def add_entry(self, sql: str, result: str, success: bool):
        now = datetime.now().strftime("%H:%M:%S")
        icon = "✓" if success else "✗"
        text = f"[{now}] {icon} {sql}\n     → {result}"

        item = QListWidgetItem(text)
        if success:
            item.setForeground(QColor("#22c55e"))
        else:
            item.setForeground(QColor("#ef4444"))
        font = QFont("monospace")
        font.setPointSize(10)
        item.setFont(font)

        self._list.insertItem(0, item)

        self.show_panel()

    def clear_log(self):
        self._list.clear()
