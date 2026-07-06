import csv
import json
import io
from typing import Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QHBoxLayout, QLabel,
    QFileDialog, QMessageBox, QAbstractItemView,
    QMenu, QApplication, QComboBox, QToolButton,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QColor, QBrush, QIcon

from app.icon_manager import IconManager


class NumericTableItem(QTableWidgetItem):
    def __lt__(self, other):
        a, b = self.text(), other.text()
        if a == "NULL":
            return True
        if b == "NULL":
            return False
        try:
            return float(a) < float(b)
        except (ValueError, TypeError):
            return a < b


class ResultViewer(QWidget):
    status_message = Signal(str)
    page_changed = Signal(int, int)  # page, page_size

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns = []
        self._rows = []
        self._editable = False
        self._page = 1
        self._page_size = 200
        self._total = 0
        self._build_ui()

    def _icon(self, name: str) -> QIcon:
        return IconManager.get_icon(name)

    def refresh_icons(self):
        self._prev_btn.setIcon(self._icon("chevron_left"))
        self._next_btn.setIcon(self._icon("chevron_right"))

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        self._info_label = QLabel("Ready")
        toolbar.addWidget(self._info_label)
        toolbar.addStretch()

        self._prev_btn = QToolButton()
        self._prev_btn.setIcon(self._icon("chevron_left"))
        self._prev_btn.setToolTip("Previous page")
        self._prev_btn.clicked.connect(self._prev_page)
        self._prev_btn.setVisible(False)
        toolbar.addWidget(self._prev_btn)

        self._page_label = QLabel("")
        self._page_label.setVisible(False)
        toolbar.addWidget(self._page_label)

        self._next_btn = QToolButton()
        self._next_btn.setIcon(self._icon("chevron_right"))
        self._next_btn.setToolTip("Next page")
        self._next_btn.clicked.connect(self._next_page)
        self._next_btn.setVisible(False)
        toolbar.addWidget(self._next_btn)

        self._page_size_combo = QComboBox()
        self._page_size_combo.addItems(["50", "100", "200", "500", "1000"])
        self._page_size_combo.setCurrentText("200")
        self._page_size_combo.currentTextChanged.connect(self._on_page_size_changed)
        self._page_size_combo.setVisible(False)
        toolbar.addWidget(QLabel("Page:"))
        toolbar.addWidget(self._page_size_combo)

        self._csv_btn = QPushButton("Export CSV")
        self._csv_btn.clicked.connect(self._export_csv)
        self._csv_btn.setVisible(False)
        toolbar.addWidget(self._csv_btn)

        self._json_btn = QPushButton("Export JSON")
        self._json_btn.clicked.connect(self._export_json)
        self._json_btn.setVisible(False)
        toolbar.addWidget(self._json_btn)

        layout.addLayout(toolbar)

        self._table = QTableWidget()
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionsClickable(True)
        self._table.horizontalHeader().setSectionsMovable(True)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.cellChanged.connect(self._on_cell_changed)

        layout.addWidget(self._table)

    def show_results(self, columns: list[str], rows: list[list[Any]], message: str | None = None):
        self._columns = columns
        self._rows = rows

        self._table.setSortingEnabled(False)
        self._table.blockSignals(True)
        self._table.clear()

        if not columns and not message:
            self._table.blockSignals(False)
            self._table.setSortingEnabled(True)
            self._info_label.setText("Ready")
            self._hide_pagination()
            return

        if message:
            self._info_label.setText(message)

        if not columns:
            self._csv_btn.setVisible(False)
            self._json_btn.setVisible(False)
            self._hide_pagination()
            self._table.setRowCount(0)
            self._table.setColumnCount(0)
            self._table.blockSignals(False)
            return

        self._table.setColumnCount(len(columns))
        self._table.setHorizontalHeaderLabels(columns)
        self._table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = NumericTableItem(str(val) if val is not None else "NULL")
                if val is None:
                    item.setForeground(QColor("#9ca3af"))
                    item.setFont(item.font())
                self._table.setItem(r, c, item)

        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.resizeColumnsToContents()

        self._table.blockSignals(False)
        self._table.setSortingEnabled(True)

        rows_text = f"{len(rows)} row{'s' if len(rows) != 1 else ''}"
        cols_text = f"{len(columns)} column{'s' if len(columns) != 1 else ''}"
        if message:
            self._info_label.setText(f"{message} | {rows_text}, {cols_text}")
        else:
            self._info_label.setText(f"{rows_text}, {cols_text}")

        self._csv_btn.setVisible(True)
        self._json_btn.setVisible(True)

    def set_pagination(self, total: int, page: int, page_size: int):
        self._total = total
        self._page = page
        self._page_size = page_size
        self._update_page_ui()

    def _update_page_ui(self):
        total_pages = max(1, (self._total + self._page_size - 1) // self._page_size)
        self._page_label.setText(f"Page {self._page}/{total_pages} ({self._total} rows)")
        self._prev_btn.setEnabled(self._page > 1)
        self._next_btn.setEnabled(self._page < total_pages)
        self._prev_btn.setVisible(True)
        self._next_btn.setVisible(True)
        self._page_label.setVisible(True)
        self._page_size_combo.setVisible(True)

    def _hide_pagination(self):
        self._prev_btn.setVisible(False)
        self._next_btn.setVisible(False)
        self._page_label.setVisible(False)
        self._page_size_combo.setVisible(False)

    def _prev_page(self):
        if self._page > 1:
            self.page_changed.emit(self._page - 1, self._page_size)

    def _next_page(self):
        total_pages = max(1, (self._total + self._page_size - 1) // self._page_size)
        if self._page < total_pages:
            self.page_changed.emit(self._page + 1, self._page_size)

    def _on_page_size_changed(self, size: str):
        self._page_size = int(size)
        self._page = 1
        self.page_changed.emit(self._page, self._page_size)

    def show_error(self, error: str):
        self._table.setSortingEnabled(False)
        self._table.blockSignals(True)
        self._table.clear()
        self._table.setRowCount(1)
        self._table.setColumnCount(1)
        self._table.setHorizontalHeaderLabels(["Error"])
        item = QTableWidgetItem(error)
        item.setForeground(QColor("#ef4444"))
        self._table.setItem(0, 0, item)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.blockSignals(False)
        self._csv_btn.setVisible(False)
        self._json_btn.setVisible(False)
        self._hide_pagination()
        self._info_label.setText("Query failed")

    def clear_results(self):
        self._columns = []
        self._rows = []
        self._table.setSortingEnabled(False)
        self._table.blockSignals(True)
        self._table.clear()
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._table.blockSignals(False)
        self._info_label.setText("Ready")
        self._csv_btn.setVisible(False)
        self._json_btn.setVisible(False)
        self._hide_pagination()

    def set_editable(self, editable: bool):
        self._editable = editable

    def _on_cell_changed(self, row: int, col: int):
        if not self._editable:
            return
        item = self._table.item(row, col)
        if item:
            pass

    def _export_csv(self):
        if not self._columns:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv)")
        if not path:
            return
        if not path.endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self._columns)
                for row in self._rows:
                    writer.writerow(row)
            self.status_message.emit(f"Exported to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def _export_json(self):
        if not self._columns:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON", "", "JSON Files (*.json)")
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        try:
            data = []
            for row in self._rows:
                obj = {}
                for i, col in enumerate(self._columns):
                    obj[col] = row[i] if i < len(row) else None
                data.append(obj)
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            self.status_message.emit(f"Exported to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def _context_menu(self, pos):
        menu = QMenu(self)
        copy_sel = QAction("Copy Selected", self)
        copy_sel.triggered.connect(self._copy_selected)
        menu.addAction(copy_sel)

        copy_action = QAction("Copy Cell", self)
        copy_action.triggered.connect(self._copy_cell)
        menu.addAction(copy_action)

        copy_all = QAction("Copy Row", self)
        copy_all.triggered.connect(self._copy_row)
        menu.addAction(copy_all)

        if self._editable:
            menu.addSeparator()
            set_null = QAction("Set NULL", self)
            set_null.triggered.connect(self._set_cell_null)
            menu.addAction(set_null)

        menu.exec(self._table.mapToGlobal(pos))

    def _copy_selected(self):
        ranges = self._table.selectedRanges()
        if not ranges:
            return
        parts = []
        for rng in ranges:
            for r in range(rng.topRow(), rng.bottomRow() + 1):
                row_vals = []
                for c in range(rng.leftColumn(), rng.rightColumn() + 1):
                    item = self._table.item(r, c)
                    row_vals.append(item.text() if item else "")
                parts.append("\t".join(row_vals))
        QApplication.clipboard().setText("\n".join(parts))

    def _copy_cell(self):
        item = self._table.currentItem()
        if item:
            QApplication.clipboard().setText(item.text())

    def _copy_row(self):
        row = self._table.currentRow()
        if row >= 0:
            values = []
            for c in range(self._table.columnCount()):
                item = self._table.item(row, c)
                values.append(item.text() if item else "")
            QApplication.clipboard().setText("\t".join(values))

    def _set_cell_null(self):
        item = self._table.currentItem()
        if item:
            item.setText("NULL")
            item.setForeground(QColor("#9ca3af"))
