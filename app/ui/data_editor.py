import copy
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QPlainTextEdit,
    QMessageBox, QAbstractItemView, QMenu, QApplication, QToolButton,
    QCompleter, QSplitter, QStyledItemDelegate, QDateEdit, QDateTimeEdit,
)
from PySide6.QtCore import Qt, Signal, QSize, QEvent
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeyEvent, QPalette, QTextCursor

from .spinner import SpinnerOverlay
from .console import ConsolePanel
from ..icon_manager import IconManager
from ..query_editor import SqlHighlighter
from .theme import get_syntax_colors

_MODIFIED_BG = QColor("#fde68a")
_NEW_ROW_BG = QColor("#d1fae5")
_DELETED_BG = QColor("#fecaca")
_NULL_COLOR = QColor("#9ca3af")
_DARK_FG = QColor("#1e1e2e")

_DATE_TYPES = {
    "DATE", "DATETIME", "TIMESTAMP", "DATETIME2", "SMALLDATETIME",
    "TIME", "DATETIMEOFFSET",
}

_NUMERIC_TYPES = {
    "INTEGER", "INT", "BIGINT", "SMALLINT", "TINYINT",
    "SERIAL", "BIGSERIAL", "SMALLSERIAL",
    "FLOAT", "DOUBLE", "REAL", "NUMERIC", "DECIMAL",
    "DOUBLE PRECISION",
}


class DateTimeDelegate(QStyledItemDelegate):
    def __init__(self, col_types: list[str], parent=None):
        super().__init__(parent)
        self._col_types = col_types

    def createEditor(self, parent, option, index):
        col_type = self._col_types[index.column()] if index.column() < len(self._col_types) else ""
        if col_type in ("DATE",):
            editor = QDateEdit(parent)
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd")
            editor.setSpecialValueText("NULL")
        else:
            editor = QDateTimeEdit(parent)
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
            editor.setSpecialValueText("NULL")
        return editor

    def setEditorData(self, editor, index):
        val = index.data(Qt.ItemDataRole.DisplayRole)
        if val is None or val == "NULL":
            editor.clear()
            return
        val = str(val).split('.')[0]
        col_type = self._col_types[index.column()] if index.column() < len(self._col_types) else ""
        fmt = "yyyy-MM-dd" if col_type in ("DATE",) else "yyyy-MM-dd HH:mm:ss"
        dt = editor.dateTimeFromText(val)
        if dt.isValid():
            editor.setDateTime(dt)
        else:
            editor.clear()

    def setModelData(self, editor, model, index):
        if editor.text() == "NULL":
            model.setData(index, "NULL", Qt.ItemDataRole.EditRole)
        else:
            model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)


class _SqlInput(QPlainTextEdit):
    returnPressed = Signal()

    def __init__(self, colors, placeholder="", parent=None):
        super().__init__(parent)
        self._highlighter = SqlHighlighter(self.document(), colors)
        self._completer = None
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(False)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFixedHeight(self.fontMetrics().height() + 8)
        self.setPlaceholderText(placeholder)
        font = self.font()
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

    def setCompleter(self, completer: QCompleter):
        if self._completer:
            try:
                self._completer.activated.disconnect()
            except RuntimeError:
                pass
        self._completer = completer
        if completer:
            completer.setWidget(self)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.activated.connect(self._insert_completion)
            self.textChanged.connect(self._update_completer)

    def _insert_completion(self, text: str):
        tc = self.textCursor()
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        was = self.blockSignals(True)
        tc.insertText(text)
        self.blockSignals(was)
        self.setTextCursor(tc)

    def _update_completer(self):
        if not self._completer:
            return
        tc = self.textCursor()
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        prefix = tc.selectedText()
        if not prefix or prefix.isspace():
            self._completer.popup().hide()
            return
        self._completer.setCompletionPrefix(prefix)
        if self._completer.completionCount() > 0:
            cr = self.cursorRect()
            cr.setWidth(self._completer.popup().sizeHintForColumn(0) + 20)
            self._completer.complete(cr)
        else:
            self._completer.popup().hide()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._completer and self._completer.popup().isVisible():
                idx = self._completer.popup().currentIndex()
                if idx.isValid():
                    text = idx.data(Qt.ItemDataRole.DisplayRole)
                    self._insert_completion(text)
                self._completer.popup().hide()
                return
            self.returnPressed.emit()
            return
        super().keyPressEvent(event)


class DataEditor(QWidget):
    status_message = Signal(str)
    save_logged = Signal(str, str, bool)  # sql, message, success
    show_ddl_requested = Signal(str, str)  # ddl_text, title

    def __init__(self, driver, table: str, schema: str = ""):
        super().__init__()
        self._driver = driver
        self._table = table
        self._schema = schema
        self._db_type = driver.config.type

        self._columns = []
        self._data = []
        self._original = []
        self._modified = set()
        self._new_rows = set()
        self._deleted_rows = set()
        self._pk_indices = []
        self._alignment = []
        self._col_types = []
        self._total_count = 0
        self._page = 1
        self._page_size = 500
        self._loading = False
        self._has_unsaved = False
        self._sort_column = None
        self._sort_direction = None

        self._build_ui()
        self._load_data()

    def _icon(self, name: str) -> QIcon:
        return IconManager.get_icon(name)

    def _toolbar_btn_style(self):
        text = self.palette().color(QPalette.ColorRole.Text).name()
        hover = self.palette().color(QPalette.ColorRole.AlternateBase).name()
        return f"""
            QPushButton {{
                background: transparent;
                color: {text};
                border: none;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {hover};
            }}
        """

    def _update_save_btn_style(self):
        if self._has_unsaved:
            self._save_btn.setStyleSheet("""
                QPushButton {
                    background-color: #22c55e;
                    color: white;
                    font-weight: bold;
                    border: none;
                    border-radius: 4px;
                    padding: 3px 6px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #16a34a;
                }
                QPushButton:pressed {
                    background-color: #15803d;
                }
            """)
        else:
            self._save_btn.setStyleSheet(self._toolbar_btn_style())

    def _on_show_ddl(self):
        self._spinner.show()
        QApplication.processEvents()
        try:
            ddl = self._driver.get_table_ddl(self._table, self._schema)
            self._spinner.hide()
            title = f"{self._schema + '.' if self._schema else ''}{self._table}"
            self.show_ddl_requested.emit(ddl, title)
        except Exception as e:
            self._spinner.hide()
            QMessageBox.critical(self, "Error", f"Failed to get DDL:\n{e}")

    def refresh_icons(self):
        self._refresh_btn.setIcon(self._icon("refresh"))
        self._add_row_btn.setIcon(self._icon("new_query"))
        self._save_btn.setIcon(self._icon("save"))
        self._console_btn.setIcon(self._icon("console"))
        self._prev_btn.setIcon(self._icon("chevron_left"))
        self._next_btn.setIcon(self._icon("chevron_right"))

    def _quote(self, name: str) -> str:
        if self._db_type == "mysql":
            return f"`{name}`"
        if self._db_type == "sqlserver":
            return f"[{name}]"
        return f'"{name}"'

    def _quote_val(self, val: Any) -> str:
        if val is None:
            return "NULL"
        if isinstance(val, bool):
            return "TRUE" if val else "FALSE"
        if isinstance(val, int) or isinstance(val, float):
            return str(val)
        escaped = str(val).replace("'", "''")
        if self._db_type == "mysql":
            escaped = escaped.replace("\\", "\\\\")
        return f"'{escaped}'"

    def _sqlserver_dt_quote(self, quoted: str, col_type: str) -> str:
        """Format quoted string for SQL Server datetime type with CAST."""
        if col_type in ("DATETIME",):
            if "." in quoted:
                left, _, right = quoted.rpartition(".")
                right = right.rstrip("'")[:3]
                quoted = f"{left}.{right}'"
        elif col_type == "SMALLDATETIME":
            if ":" in quoted and quoted.rfind(":") > quoted.rfind(" "):
                left, _, right = quoted.rpartition(":")
                right = right.rstrip("'")[:2]
                quoted = f"{left}:{right}'"
        return f"CAST({quoted} AS {col_type})"

    def _schema_prefix(self) -> str:
        if self._schema:
            return f"{self._quote(self._schema)}."
        return ""

    def _full_table(self) -> str:
        return f"{self._schema_prefix()}{self._quote(self._table)}"

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(2)

        self._refresh_btn = QToolButton()
        self._refresh_btn.setIcon(self._icon("refresh"))
        self._refresh_btn.setToolTip("Refresh")
        self._refresh_btn.clicked.connect(self._refresh_data)
        toolbar.addWidget(self._refresh_btn)

        self._add_row_btn = QToolButton()
        self._add_row_btn.setIcon(self._icon("new_query"))
        self._add_row_btn.setToolTip("Add Row")
        self._add_row_btn.clicked.connect(self._add_row)
        toolbar.addWidget(self._add_row_btn)

        self._save_btn = QPushButton()
        self._save_btn.setIcon(self._icon("save"))
        self._save_btn.setText(" Save Changes")
        self._save_btn.setToolTip("Save changes")
        self._save_btn.clicked.connect(self._save_changes)
        self._save_btn.setEnabled(False)
        self._update_save_btn_style()
        toolbar.addWidget(self._save_btn)

        self._show_ddl_btn = QPushButton("Show DDL")
        self._show_ddl_btn.setToolTip("View CREATE TABLE statement")
        self._show_ddl_btn.clicked.connect(self._on_show_ddl)
        self._show_ddl_btn.setStyleSheet(self._toolbar_btn_style())
        toolbar.addWidget(self._show_ddl_btn)

        toolbar.addStretch()
        self._console_btn = QToolButton()
        self._console_btn.setIcon(self._icon("console"))
        self._console_btn.setToolTip("Toggle console log")
        self._console_btn.setCheckable(True)
        self._console_btn.setChecked(False)
        self._console_btn.toggled.connect(self._toggle_console)
        toolbar.addWidget(self._console_btn)
        self._status_label = QLabel("")
        toolbar.addWidget(self._status_label)
        layout.addLayout(toolbar)

        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(2)
        filter_bar.setContentsMargins(0, 0, 8, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        colors = get_syntax_colors()

        where_container = QWidget()
        where_layout = QHBoxLayout(where_container)
        where_layout.setContentsMargins(8, 0, 8, 0)
        where_label = QLabel("WHERE")
        where_layout.addWidget(where_label)
        self._where_input = _SqlInput(colors, "column = value ...")
        self._where_input.returnPressed.connect(self._go)
        where_layout.addWidget(self._where_input)
        splitter.addWidget(where_container)

        order_container = QWidget()
        order_layout = QHBoxLayout(order_container)
        order_layout.setContentsMargins(8, 0, 8, 0)
        order_label = QLabel("ORDER BY")
        order_layout.addWidget(order_label)
        self._order_input = _SqlInput(colors, "column_name [ASC|DESC] ...")
        self._order_input.returnPressed.connect(self._go)
        order_layout.addWidget(self._order_input)
        splitter.addWidget(order_container)

        filter_bar.addWidget(splitter)

        self._go_btn = QPushButton("Go")
        self._go_btn.clicked.connect(self._go)
        filter_bar.addWidget(self._go_btn)

        layout.addLayout(filter_bar)

        self._table_widget = QTableWidget()
        self._table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_widget.customContextMenuRequested.connect(self._context_menu)
        self._table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table_widget.setAlternatingRowColors(True)
        self._table_widget.horizontalHeader().setStretchLastSection(False)
        self._table_widget.horizontalHeader().setSectionsClickable(True)
        self._table_widget.horizontalHeader().setSectionsMovable(True)
        self._table_widget.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._table_widget.setSortingEnabled(False)
        self._table_widget.verticalHeader().setDefaultSectionSize(24)
        self._table_widget.horizontalHeader().setMinimumSectionSize(120)
        self._table_widget.cellChanged.connect(self._on_cell_changed)
        self._table_widget.installEventFilter(self)

        self._bottom_splitter = QSplitter(Qt.Orientation.Vertical)
        self._bottom_splitter.addWidget(self._table_widget)

        self._console = ConsolePanel()
        self._console.setMinimumHeight(100)
        self._console.setVisible(False)
        self._bottom_splitter.addWidget(self._console)

        self._bottom_splitter.setStretchFactor(0, 1)
        self._bottom_splitter.setStretchFactor(1, 0)
        layout.addWidget(self._bottom_splitter, stretch=1)

        self._spinner = SpinnerOverlay(self)
        self._spinner.hide()

        page_bar = QHBoxLayout()
        page_bar.setSpacing(2)

        self._prev_btn = QToolButton()
        self._prev_btn.setIcon(self._icon("chevron_left"))
        self._prev_btn.setToolTip("Previous page")
        self._prev_btn.clicked.connect(self._prev_page)
        self._prev_btn.setEnabled(False)
        page_bar.addWidget(self._prev_btn)

        self._page_label = QLabel("Page 1 of 1 (0 rows)")
        page_bar.addWidget(self._page_label)

        self._next_btn = QToolButton()
        self._next_btn.setIcon(self._icon("chevron_right"))
        self._next_btn.setToolTip("Next page")
        self._next_btn.clicked.connect(self._next_page)
        self._next_btn.setEnabled(False)
        page_bar.addWidget(self._next_btn)

        page_bar.addStretch()
        layout.addLayout(page_bar)

    def eventFilter(self, obj, event):
        if obj == self._table_widget and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._table_widget.currentItem() and not self._table_widget.state() == QAbstractItemView.State.EditingState:
                    self._table_widget.editItem(self._table_widget.currentItem())
                    return True
        return super().eventFilter(obj, event)

    def _show_console(self):
        if not self._console.isVisible():
            self._console.setVisible(True)
            self._console_btn.setChecked(True)
            total = self._bottom_splitter.height()
            self._bottom_splitter.setSizes([int(total * 0.6), int(total * 0.4)])

    def _toggle_console(self, visible: bool):
        if visible:
            self._show_console()
        else:
            self._console.setVisible(False)
            self._console_btn.setChecked(False)

    @staticmethod
    def _validate_clause(text: str) -> str:
        forbidden = {";", "--", "/*", "*/", "DROP ", "ALTER ", "TRUNCATE ",
                     "EXEC ", "EXECUTE ", "INSERT ", "UPDATE ", "DELETE ", "CREATE "}
        upper = text.upper()
        for f in forbidden:
            if f in upper:
                raise ValueError(f"Forbidden keyword or character in clause: {f.strip()}")
        return text

    def _build_order_by(self) -> str:
        if self._sort_column:
            col = self._quote(self._sort_column)
            direction = self._sort_direction or "ASC"
            return f"ORDER BY {col} {direction}"
        text = self._order_input.toPlainText().strip()
        if text:
            self._validate_clause(text)
            upper = text.upper().strip()
            if not (upper.endswith(" ASC") or upper.endswith(" DESC")):
                text = f"{text} ASC"
            return f"ORDER BY {text}"
        return ""

    def _build_where_clause(self) -> str:
        text = self._where_input.toPlainText().strip()
        if text:
            self._validate_clause(text)
            if text.upper().startswith("WHERE "):
                return text
            return f"WHERE {text}"
        return ""

    def _get_pk_condition(self, row: dict) -> str:
        parts = []
        for idx in self._pk_indices:
            col = self._columns[idx]
            val = row.get(col)
            if val is None:
                parts.append(f"{self._quote(col)} IS NULL")
            else:
                quoted = self._quote_val(val)
                if self._db_type == "sqlserver" and idx < len(self._col_types) and self._col_types[idx] in _DATE_TYPES:
                    quoted = self._sqlserver_dt_quote(quoted, self._col_types[idx])
                parts.append(f"{self._quote(col)} = {quoted}")
        if parts:
            return " AND ".join(parts)
        all_parts = []
        for ci, col in enumerate(self._columns):
            val = row.get(col)
            if val is None:
                all_parts.append(f"{self._quote(col)} IS NULL")
            else:
                quoted = self._quote_val(val)
                if self._db_type == "sqlserver" and ci < len(self._col_types) and self._col_types[ci] in _DATE_TYPES:
                    quoted = self._sqlserver_dt_quote(quoted, self._col_types[ci])
                all_parts.append(f"{self._quote(col)} = {quoted}")
        return " AND ".join(all_parts)

    def _on_header_clicked(self, col_idx: int):
        col_name = self._columns[col_idx]
        if self._sort_column != col_name:
            self._sort_column = col_name
            self._sort_direction = "DESC"
        else:
            if self._sort_direction == "DESC":
                self._sort_direction = "ASC"
            else:
                self._sort_column = None
                self._sort_direction = None

        if self._sort_column:
                self._order_input.setPlainText(f"{self._sort_column} {self._sort_direction}")

        header = self._table_widget.horizontalHeader()
        if self._sort_direction == "DESC":
            header.setSortIndicatorShown(True)
            header.setSortIndicator(col_idx, Qt.SortOrder.DescendingOrder)
        elif self._sort_direction == "ASC":
            header.setSortIndicatorShown(True)
            header.setSortIndicator(col_idx, Qt.SortOrder.AscendingOrder)
        else:
            header.setSortIndicatorShown(False)

        if self._has_unsaved:
            reply = QMessageBox.warning(
                self, "Unsaved Changes",
                "Discard unsaved changes?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._page = 1
        self._load_data()

    def _load_data(self):
        self._loading = True
        self._table_widget.blockSignals(True)
        self._table_widget.clear()
        self._spinner.show()
        QApplication.processEvents()

        offset = (self._page - 1) * self._page_size
        where = self._build_where_clause()
        order_by = self._build_order_by()
        if not order_by:
            order_by = "ORDER BY 1 ASC"

        if self._db_type == "sqlserver":
            base_sql = f"SELECT * FROM {self._full_table()} {where} {order_by} OFFSET {offset} ROWS FETCH NEXT {self._page_size} ROWS ONLY"
        else:
            base_sql = f"SELECT * FROM {self._full_table()} {where} {order_by} LIMIT {self._page_size} OFFSET {offset}"

        try:
            columns, rows, _ = self._driver.execute_query(base_sql)
            self._console.add_entry(base_sql, f"{len(rows)} rows loaded", True)
            self._show_console()
        except Exception as e:
            self._spinner.hide()
            self._console.add_entry(base_sql, str(e), False)
            self._show_console()
            self._table_widget.blockSignals(False)
            self._loading = False
            self._show_error(str(e))
            return

        self._columns = columns
        self._data = [list(r) for r in rows]
        self._original = copy.deepcopy(self._data)
        self._modified.clear()
        self._new_rows.clear()
        self._deleted_rows.clear()
        self._has_unsaved = False
        self._save_btn.setEnabled(False)
        self._update_save_btn_style()

        if not columns:
            self._table_widget.setColumnCount(0)
            self._table_widget.setRowCount(0)
            self._table_widget.blockSignals(False)
            self._loading = False
            self._update_page_info()
            return

        self._table_widget.setColumnCount(len(columns))
        self._table_widget.setHorizontalHeaderLabels(columns)

        where_completer = QCompleter(columns)
        where_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        where_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._where_input.setCompleter(where_completer)

        order_completer = QCompleter(columns)
        order_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        order_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._order_input.setCompleter(order_completer)

        self._pk_indices = []
        self._alignment = [Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter] * len(columns)
        try:
            col_infos = self._driver.get_table_columns(self._table, self._schema)
            col_names = [c.name for c in col_infos]
            for i, c in enumerate(columns):
                if c in col_names:
                    idx = col_names.index(c)
                    if col_infos[idx].is_pk:
                        self._pk_indices.append(i)
                    if col_infos[idx].data_type.upper() in _NUMERIC_TYPES:
                        self._alignment[i] = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            self._col_types = [""] * len(columns)
            for i, c in enumerate(columns):
                if c in col_names:
                    self._col_types[i] = col_infos[col_names.index(c)].data_type.upper()
        except Exception:
            self._col_types = [""] * len(columns)

        self._datetime_delegate = DateTimeDelegate(self._col_types, self._table_widget)
        for i, col_type in enumerate(self._col_types):
            if col_type in _DATE_TYPES:
                self._table_widget.setItemDelegateForColumn(i, self._datetime_delegate)

        self._table_widget.setRowCount(len(rows))
        for r, row in enumerate(self._data):
            for c, val in enumerate(row):
                item = QTableWidgetItem(str(val) if val is not None else "NULL")
                if val is None:
                    item.setForeground(_NULL_COLOR)
                if c < len(self._alignment):
                    item.setTextAlignment(self._alignment[c])
                self._table_widget.setItem(r, c, item)

        header = self._table_widget.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table_widget.resizeColumnsToContents()
        for i in range(min(len(columns), 10)):
            w = header.sectionSize(i)
            if w < 120:
                header.resizeSection(i, 120)

        self._restore_sort_indicator()

        self._table_widget.blockSignals(False)
        self._loading = False
        self._spinner.hide()
        self._count_total()
        self._update_page_info()

    def _restore_sort_indicator(self):
        if not self._sort_column or self._sort_column not in self._columns:
            return
        header = self._table_widget.horizontalHeader()
        col_idx = self._columns.index(self._sort_column)
        if self._sort_direction == "DESC":
            header.setSortIndicatorShown(True)
            header.setSortIndicator(col_idx, Qt.SortOrder.DescendingOrder)
        elif self._sort_direction == "ASC":
            header.setSortIndicatorShown(True)
            header.setSortIndicator(col_idx, Qt.SortOrder.AscendingOrder)

    def _count_total(self):
        where = self._build_where_clause()
        count_sql = f"SELECT COUNT(*) FROM {self._full_table()} {where}"
        try:
            _, rows, _ = self._driver.execute_query(count_sql)
            if rows and rows[0]:
                self._total_count = int(rows[0][0])
            else:
                self._total_count = 0
        except Exception:
            self._total_count = 0

    def _update_page_info(self):
        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        displayed = len(self._data)
        self._page_label.setText(
            f"Page {self._page} of {total_pages} ({displayed} of {self._total_count} rows)"
        )
        self._prev_btn.setEnabled(self._page > 1)
        self._next_btn.setEnabled(self._page < total_pages)
        self._status_label.setText("Unsaved changes" if self._has_unsaved else "")

    def _show_error(self, error: str):
        self._table_widget.blockSignals(True)
        self._table_widget.clear()
        self._table_widget.setRowCount(1)
        self._table_widget.setColumnCount(1)
        self._table_widget.setHorizontalHeaderLabels(["Error"])
        item = QTableWidgetItem(error)
        item.setForeground(QColor("#ef4444"))
        self._table_widget.setItem(0, 0, item)
        self._table_widget.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table_widget.blockSignals(False)
        self._status_label.setText("Query failed")

    def _go(self):
        if self._has_unsaved:
            reply = QMessageBox.warning(
                self, "Unsaved Changes",
                "Discard unsaved changes and reload?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._page = 1
        self._load_data()

    def _refresh_data(self):
        self._go()

    def _add_row(self):
        self._table_widget.blockSignals(True)
        row_idx = self._table_widget.rowCount()
        self._table_widget.setRowCount(row_idx + 1)

        empty_row = [None] * len(self._columns)
        self._data.append(empty_row)
        self._original.append(None)
        self._new_rows.add(row_idx)
        self._has_unsaved = True
        self._save_btn.setEnabled(True)
        self._update_save_btn_style()

        for c in range(len(self._columns)):
            item = QTableWidgetItem("NULL")
            item.setForeground(_NULL_COLOR)
            if c < len(self._alignment):
                item.setTextAlignment(self._alignment[c])
            self._table_widget.setItem(row_idx, c, item)

        self._highlight_row(row_idx, _NEW_ROW_BG)
        self._table_widget.blockSignals(False)
        self._update_page_info()

    def _on_cell_changed(self, row: int, col: int):
        if self._loading:
            return
        if row >= len(self._data):
            return

        item = self._table_widget.item(row, col)
        if not item:
            return

        new_text = item.text()
        is_null = new_text == "NULL"

        if is_null:
            new_val = None
        else:
            new_val = new_text

        if row in self._new_rows or row in self._deleted_rows:
            if row in self._new_rows:
                self._data[row][col] = new_val
            return

        original_row = self._original[row]
        if original_row is not None and col < len(original_row):
            old_val = original_row[col]
        else:
            old_val = None

        old_text = str(old_val) if old_val is not None else "NULL"
        if new_text == old_text:
            self._modified.discard((row, col))
            item.setBackground(QColor(0, 0, 0, 0))
            item.setForeground(QColor(Qt.GlobalColor.white) if not is_null else _NULL_COLOR)
        else:
            self._modified.add((row, col))
            item.setBackground(_MODIFIED_BG)
            item.setForeground(_DARK_FG)

        self._data[row][col] = new_val
        self._has_unsaved = bool(self._modified or self._new_rows or self._deleted_rows)
        self._save_btn.setEnabled(self._has_unsaved)
        self._update_save_btn_style()
        self._update_page_info()

    def _context_menu(self, pos):
        item = self._table_widget.itemAt(pos)
        if not item:
            return
        row = item.row()

        menu = QMenu(self)

        copy_sel = QAction("Copy Selected", self)
        copy_sel.triggered.connect(self._copy_selected)
        menu.addAction(copy_sel)

        copy_cell = QAction("Copy Cell", self)
        copy_cell.triggered.connect(self._copy_cell)
        menu.addAction(copy_cell)

        copy_row = QAction("Copy Row", self)
        copy_row.triggered.connect(self._copy_row)
        menu.addAction(copy_row)

        menu.addSeparator()

        set_null = QAction("Set NULL", self)
        set_null.triggered.connect(self._set_cell_null)
        menu.addAction(set_null)

        menu.addSeparator()

        if row not in self._deleted_rows:
            delete_row = QAction("Delete Row", self)
            delete_row.triggered.connect(lambda: self._delete_row(row))
            menu.addAction(delete_row)

        if row in self._deleted_rows:
            undelete_row = QAction("Undelete Row", self)
            undelete_row.triggered.connect(lambda: self._undelete_row(row))
            menu.addAction(undelete_row)

        menu.exec(self._table_widget.mapToGlobal(pos))

    def _copy_selected(self):
        ranges = self._table_widget.selectedRanges()
        if not ranges:
            return
        parts = []
        for rng in ranges:
            for r in range(rng.topRow(), rng.bottomRow() + 1):
                row_vals = []
                for c in range(rng.leftColumn(), rng.rightColumn() + 1):
                    item = self._table_widget.item(r, c)
                    row_vals.append(item.text() if item else "")
                parts.append("\t".join(row_vals))
        QApplication.clipboard().setText("\n".join(parts))

    def _copy_cell(self):
        item = self._table_widget.currentItem()
        if item:
            QApplication.clipboard().setText(item.text())

    def _copy_row(self):
        row = self._table_widget.currentRow()
        if row >= 0:
            values = []
            for c in range(self._table_widget.columnCount()):
                item = self._table_widget.item(row, c)
                values.append(item.text() if item else "")
            QApplication.clipboard().setText("\t".join(values))

    def _set_cell_null(self):
        item = self._table_widget.currentItem()
        if item:
            self._loading = True
            item.setText("NULL")
            item.setForeground(_NULL_COLOR)
            self._loading = False
            row = self._table_widget.currentRow()
            col = self._table_widget.currentColumn()
            if row < len(self._data):
                self._on_cell_changed(row, col)

    def _delete_row(self, row: int):
        if row in self._deleted_rows:
            return
        self._deleted_rows.add(row)
        self._has_unsaved = True
        self._save_btn.setEnabled(True)
        self._update_save_btn_style()
        self._highlight_row(row, _DELETED_BG)
        for c in range(self._table_widget.columnCount()):
            item = self._table_widget.item(row, c)
            if item:
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
        self._update_page_info()

    def _undelete_row(self, row: int):
        if row not in self._deleted_rows:
            return
        self._deleted_rows.discard(row)
        self._highlight_row(row, QColor(0, 0, 0, 0))
        for c in range(self._table_widget.columnCount()):
            item = self._table_widget.item(row, c)
            if item:
                font = item.font()
                font.setStrikeOut(False)
                item.setFont(font)
                item.setForeground(QColor(Qt.GlobalColor.white))
                if (row, c) in self._modified:
                    item.setForeground(_DARK_FG)
        self._has_unsaved = bool(self._modified or self._new_rows or self._deleted_rows)
        self._save_btn.setEnabled(self._has_unsaved)
        self._update_save_btn_style()
        self._update_page_info()

    def _highlight_row(self, row: int, color: QColor):
        for c in range(self._table_widget.columnCount()):
            item = self._table_widget.item(row, c)
            if item:
                item.setBackground(color)
                item.setForeground(_DARK_FG)

    def _save_changes(self):
        if not self._has_unsaved:
            return
        if not self._pk_indices:
            reply = QMessageBox.warning(
                self, "No Primary Key",
                "This table has no primary key. Changes will use all columns as identity.\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        statements = []
        data_by_row = {}
        for r, row_data in enumerate(self._data):
            if row_data is None:
                continue
            d = {}
            for c, col_name in enumerate(self._columns):
                val = row_data[c] if c < len(row_data) else None
                d[col_name] = val
            data_by_row[r] = d

        for row_idx in sorted(self._deleted_rows):
            if row_idx in self._new_rows:
                continue
            orig_row_data = self._original[row_idx] if row_idx < len(self._original) and self._original[row_idx] else None
            if orig_row_data is None:
                continue
            orig_dict = {}
            for ci, cn in enumerate(self._columns):
                orig_dict[cn] = orig_row_data[ci] if ci < len(orig_row_data) else None
            pk_cond = self._get_pk_condition(orig_dict)
            sql = f"DELETE FROM {self._full_table()} WHERE {pk_cond}"
            statements.append(sql)

        for row_idx, col_idx in self._modified:
            if row_idx in self._deleted_rows:
                continue
            d = data_by_row.get(row_idx)
            if d is None:
                continue
            col_name = self._columns[col_idx]
            new_val = d[col_name]

            orig_row_data = self._original[row_idx] if row_idx < len(self._original) and self._original[row_idx] else None
            try:
                orig_val = orig_row_data[col_idx] if orig_row_data else None
            except (IndexError, TypeError):
                orig_val = None
            if new_val == orig_val:
                continue

            if orig_row_data:
                orig_dict = {}
                for ci, cn in enumerate(self._columns):
                    orig_dict[cn] = orig_row_data[ci] if ci < len(orig_row_data) else None
                pk_cond = self._get_pk_condition(orig_dict)
            else:
                pk_cond = self._get_pk_condition(d)

            quoted = self._quote_val(new_val)
            if self._db_type == "sqlserver" and col_idx < len(self._col_types) and self._col_types[col_idx] in _DATE_TYPES:
                quoted = self._sqlserver_dt_quote(quoted, self._col_types[col_idx])
            sql = f"UPDATE {self._full_table()} SET {self._quote(col_name)} = {quoted} WHERE {pk_cond}"
            if sql not in statements:
                statements.append(sql)

        for row_idx in sorted(self._new_rows):
            if row_idx in self._deleted_rows:
                continue
            d = data_by_row.get(row_idx)
            if d is None:
                continue
            cols = []
            vals = []
            for ci, col_name in enumerate(self._columns):
                val = d[col_name]
                if val is not None:
                    quoted = self._quote_val(val)
                    if self._db_type == "sqlserver" and ci < len(self._col_types) and self._col_types[ci] in _DATE_TYPES:
                        quoted = self._sqlserver_dt_quote(quoted, self._col_types[ci])
                    cols.append(self._quote(col_name))
                    vals.append(quoted)
            if cols:
                sql = f"INSERT INTO {self._full_table()} ({', '.join(cols)}) VALUES ({', '.join(vals)})"
                statements.append(sql)

        if not statements:
            self._has_unsaved = False
            self._save_btn.setEnabled(False)
            self._update_save_btn_style()
            self._update_page_info()
            return

        sql_summary = "; ".join(statements)
        self._spinner.show()
        QApplication.processEvents()
        try:
            self._driver.begin()
            for sql in statements:
                self._driver.execute_query(sql)
            self._driver.commit()
            msg = f"Saved {len(statements)} change(s)"
            self.save_logged.emit(sql_summary, msg, True)
            self._console.add_entry(sql_summary, msg, True)
            self._show_console()
            self.status_message.emit(msg)
        except Exception as e:
            self._spinner.hide()
            try:
                self._driver.rollback()
            except Exception:
                pass
            err = str(e)
            self.save_logged.emit(sql_summary, err, False)
            self._console.add_entry(sql_summary, err, False)
            self._show_console()
            QMessageBox.critical(self, "Save Failed", err)
            return

        self._load_data()

    def _prev_page(self):
        if self._page > 1:
            self._check_page_change(lambda: setattr(self, '_page', self._page - 1))

    def _next_page(self):
        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        if self._page < total_pages:
            self._check_page_change(lambda: setattr(self, '_page', self._page + 1))

    def _check_page_change(self, change_fn):
        if self._has_unsaved:
            reply = QMessageBox.warning(
                self, "Unsaved Changes",
                "Discard unsaved changes?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        change_fn()
        self._load_data()
