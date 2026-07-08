from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QSplitter, QMessageBox, QWidget, QLineEdit,
)
from PySide6.QtCore import Qt, Signal


class QueryHistoryDialog(QDialog):
    history_cleared = Signal()

    def __init__(self, queries: list, parent=None, current_connection=""):
        super().__init__(parent)
        self.selected_query = ""
        self._all_queries = queries
        self._current_connection = current_connection
        self._filtered = []
        self.setWindowTitle(
            f"Query History - {current_connection}" if current_connection else "Query History"
        )
        self.setMinimumSize(650, 420)
        self.resize(700, 450)
        self._build_ui()
        self._rebuild_filtered()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search query history...")
        self._search.textChanged.connect(self._rebuild_filtered)
        layout.addWidget(self._search)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_select)
        self._list.setMinimumWidth(200)
        left_layout.addWidget(self._list)

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._clear_all)
        left_layout.addWidget(clear_btn)

        splitter.addWidget(left_panel)

        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setStyleSheet("font-family: monospace; font-size: 12px;")
        self._preview.setPlaceholderText("Select a query from the list")
        splitter.addWidget(self._preview)

        splitter.setSizes([250, 400])
        layout.addWidget(splitter)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._use_btn = QPushButton("Use Query")
        self._use_btn.clicked.connect(self._use_query)
        self._use_btn.setEnabled(False)
        btn_layout.addWidget(self._use_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _rebuild_filtered(self):
        text = self._search.text().lower()
        self._filtered = [
            q for q in self._all_queries
            if q["connection"] == self._current_connection
            and (not text or text in q["sql"].lower())
        ]
        self._populate_list()

    def _populate_list(self):
        self._list.blockSignals(True)
        self._list.clear()
        for entry in reversed(self._filtered):
            sql = entry["sql"]
            display = sql.strip().replace("\n", " ")[:60]
            if len(sql) > 60:
                display += "..."
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, sql)
            item.setToolTip(sql)
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._on_select(-1)

    def _on_select(self, row: int):
        if row < 0:
            self._preview.clear()
            self._use_btn.setEnabled(False)
            return
        item = self._list.item(row)
        if item:
            sql = item.data(Qt.ItemDataRole.UserRole)
            self._preview.setPlainText(sql)
            self._use_btn.setEnabled(True)

    def _use_query(self):
        item = self._list.currentItem()
        if item:
            self.selected_query = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def _clear_all(self):
        reply = QMessageBox.warning(
            self, "Clear History",
            "Clear all query history for this connection?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._all_queries[:] = [q for q in self._all_queries if q["connection"] != self._current_connection]
            self.history_cleared.emit()
            self._rebuild_filtered()
            self._preview.clear()
            self._use_btn.setEnabled(False)
