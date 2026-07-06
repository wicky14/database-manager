from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QLineEdit, QComboBox,
    QPlainTextEdit, QCheckBox, QMessageBox, QAbstractItemView, QMenu,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont

_DELETED_BG = QColor("#fecaca")
_NEW_BG = QColor("#d1fae5")


COMMON_TYPES = [
    "INTEGER", "BIGINT", "SMALLINT", "TINYINT",
    "DECIMAL", "NUMERIC", "REAL", "FLOAT", "DOUBLE PRECISION",
    "VARCHAR(255)", "VARCHAR(100)", "VARCHAR(50)",
    "CHAR", "TEXT", "BOOLEAN",
    "DATE", "TIME", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE",
    "BLOB", "BYTEA", "UUID", "JSON", "JSONB",
    "SERIAL", "BIGSERIAL",
]


class EditTableDialog(QDialog):
    table_changed = Signal()

    def __init__(self, driver, table: str, schema: str = ""):
        super().__init__()
        self._driver = driver
        self._table = table
        self._schema = schema
        self._db_type = driver.config.type

        self._columns = []
        self._deleted_rows = set()
        self._new_rows = set()

        self.setWindowTitle(f"Edit Table: {table}")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)
        self._build_ui()
        self._load_columns()

    def _quote(self, name: str) -> str:
        if self._db_type == "mysql":
            return f"`{name}`"
        if self._db_type == "sqlserver":
            return f"[{name}]"
        return f'"{name}"'

    def _schema_prefix(self) -> str:
        if self._schema:
            return f"{self._quote(self._schema)}."
        return ""

    def _full_table(self) -> str:
        return f"{self._schema_prefix()}{self._quote(self._table)}"

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(QLabel("Schema:"))
        schema_label = QLabel(self._schema or "public")
        schema_label.setStyleSheet("font-weight: bold;")
        header.addWidget(schema_label)
        header.addSpacing(20)
        header.addWidget(QLabel("Table:"))
        table_label = QLabel(self._table)
        table_label.setStyleSheet("font-weight: bold;")
        header.addWidget(table_label)
        header.addStretch()
        layout.addLayout(header)

        self._table_widget = QTableWidget()
        self._table_widget.setColumnCount(5)
        self._table_widget.setHorizontalHeaderLabels(["Name", "Type", "Nullable", "Default", "PK"])
        self._table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_widget.customContextMenuRequested.connect(self._context_menu)
        self._table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table_widget.horizontalHeader().setSectionsMovable(True)
        self._table_widget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table_widget.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self._table_widget.cellChanged.connect(self._preview_sql)
        self._table_widget.verticalHeader().setDefaultSectionSize(28)
        layout.addWidget(self._table_widget)

        self._add_btn = QPushButton("+ Add Column")
        self._add_btn.clicked.connect(self._add_column)
        layout.addWidget(self._add_btn)

        layout.addWidget(QLabel("Preview SQL:"))

        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMaximumHeight(120)
        self._preview.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(self._preview)

        self._backup_cb = QCheckBox("Backup table before executing (recommended)")
        self._backup_cb.setChecked(True)
        layout.addWidget(self._backup_cb)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()

        self._execute_btn = QPushButton("Execute Changes")
        self._execute_btn.clicked.connect(self._execute_changes)
        btn_layout.addWidget(self._execute_btn)
        layout.addLayout(btn_layout)

    def _get_type_widget(self, current_type: str = "INTEGER") -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(COMMON_TYPES)
        idx = combo.findText(current_type, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentText(current_type)
        combo.currentTextChanged.connect(lambda: self._preview_sql())
        return combo

    def _load_columns(self):
        try:
            col_infos = self._driver.get_table_columns(self._table, self._schema)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load columns: {e}")
            self.reject()
            return

        self._table_widget.blockSignals(True)
        self._table_widget.setRowCount(len(col_infos))

        for r, ci in enumerate(col_infos):
            name_item = QTableWidgetItem(ci.name)
            self._table_widget.setItem(r, 0, name_item)

            type_combo = self._get_type_widget(ci.data_type)
            self._table_widget.setCellWidget(r, 1, type_combo)

            null_item = QTableWidgetItem()
            null_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            null_item.setCheckState(
                Qt.CheckState.Checked if ci.nullable else Qt.CheckState.Unchecked
            )
            self._table_widget.setItem(r, 2, null_item)

            default_item = QTableWidgetItem(str(ci.default) if ci.default is not None else "")
            self._table_widget.setItem(r, 3, default_item)

            pk_item = QTableWidgetItem()
            pk_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            pk_item.setCheckState(
                Qt.CheckState.Checked if ci.is_pk else Qt.CheckState.Unchecked
            )
            self._table_widget.setItem(r, 4, pk_item)

        self._table_widget.blockSignals(False)

    def _add_column(self):
        self._table_widget.blockSignals(True)
        row = self._table_widget.rowCount()
        self._table_widget.setRowCount(row + 1)
        self._new_rows.add(row)

        self._table_widget.setItem(row, 0, QTableWidgetItem(""))

        type_combo = self._get_type_widget("INTEGER")
        self._table_widget.setCellWidget(row, 1, type_combo)

        null_item = QTableWidgetItem()
        null_item.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        )
        null_item.setCheckState(Qt.CheckState.Checked)
        self._table_widget.setItem(row, 2, null_item)

        self._table_widget.setItem(row, 3, QTableWidgetItem(""))

        pk_item = QTableWidgetItem()
        pk_item.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        )
        pk_item.setCheckState(Qt.CheckState.Unchecked)
        self._table_widget.setItem(row, 4, pk_item)

        self._table_widget.blockSignals(False)
        self._preview_sql()

    def _context_menu(self, pos):
        item = self._table_widget.itemAt(pos)
        if not item:
            return
        row = item.row()
        if row < 0 or row >= self._table_widget.rowCount():
            return

        menu = QMenu(self)
        if row not in self._deleted_rows:
            delete_action = QAction("Delete Column", self)
            delete_action.triggered.connect(lambda: self._delete_column(row))
            menu.addAction(delete_action)

        if row in self._deleted_rows:
            undelete_action = QAction("Undelete Column", self)
            undelete_action.triggered.connect(lambda: self._undelete_column(row))
            menu.addAction(undelete_action)

        menu.exec(self._table_widget.mapToGlobal(pos))

    def _delete_column(self, row: int):
        if row in self._deleted_rows:
            return
        self._deleted_rows.add(row)
        for c in range(self._table_widget.columnCount()):
            cell_item = self._table_widget.item(row, c)
            if cell_item:
                cell_item.setBackground(_DELETED_BG)
                font = cell_item.font()
                font.setStrikeOut(True)
                cell_item.setFont(font)
        self._preview_sql()

    def _undelete_column(self, row: int):
        if row not in self._deleted_rows:
            return
        self._deleted_rows.discard(row)
        for c in range(self._table_widget.columnCount()):
            cell_item = self._table_widget.item(row, c)
            if cell_item:
                cell_item.setBackground(QColor(0, 0, 0, 0))
                font = cell_item.font()
                font.setStrikeOut(False)
                cell_item.setFont(font)
        self._preview_sql()

    def _get_column_data(self) -> list[dict]:
        result = []
        for r in range(self._table_widget.rowCount()):
            name_item = self._table_widget.item(r, 0)
            name = name_item.text().strip() if name_item else ""

            type_widget = self._table_widget.cellWidget(r, 1)
            col_type = type_widget.currentText().strip() if type_widget else "INTEGER"

            null_item = self._table_widget.item(r, 2)
            nullable = null_item.checkState() == Qt.CheckState.Checked if null_item else True

            default_item = self._table_widget.item(r, 3)
            default = default_item.text().strip() if default_item else ""

            pk_item = self._table_widget.item(r, 4)
            is_pk = pk_item.checkState() == Qt.CheckState.Checked if pk_item else False

            result.append({
                "name": name,
                "type": col_type,
                "nullable": nullable,
                "default": default,
                "is_pk": is_pk,
                "row": r,
                "is_new": r in self._new_rows,
                "is_deleted": r in self._deleted_rows,
            })
        return result

    def _preview_sql(self):
        cols = self._get_column_data()
        statements = []

        for col in cols:
            if col["is_deleted"] and not col["is_new"]:
                statements.append(
                    f"ALTER TABLE {self._full_table()} DROP COLUMN {self._quote(col['name'])};"
                )

        for col in cols:
            if not col["is_deleted"] and col["is_new"]:
                nullable = " NOT NULL" if not col["nullable"] else ""
                default_clause = f" DEFAULT {col['default']}" if col["default"] else ""
                statements.append(
                    f"ALTER TABLE {self._full_table()} ADD COLUMN "
                    f"{self._quote(col['name'])} {col['type']}{nullable}{default_clause};"
                )

        self._preview.setPlainText("\n".join(statements) if statements else "-- No changes")

    def _execute_changes(self):
        cols = self._get_column_data()

        for col in cols:
            if col["is_deleted"] and not col["is_new"]:
                if col["is_pk"]:
                    QMessageBox.warning(
                        self, "Cannot Drop PK",
                        f"Cannot drop primary key column '{col['name']}'."
                    )
                    return

                reply = QMessageBox.warning(
                    self, "Drop Column",
                    f"DROP COLUMN '{col['name']}'\n\n"
                    "Data will be lost permanently.\n"
                    "Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

        # validate names
        names = [col["name"] for col in cols if not col["is_deleted"]]
        if len(names) != len(set(names)):
            QMessageBox.warning(self, "Duplicate Names", "Column names must be unique.")
            return

        if not names:
            QMessageBox.warning(self, "No Columns", "Table must have at least one column.")
            return

        for col in cols:
            if not col["is_deleted"] and not col["name"]:
                QMessageBox.warning(self, "Empty Name", "All columns must have a name.")
                return

        statements = []
        if self._backup_cb.isChecked():
            backup_name = f"{self._table}_backup"
            statements.append(
                f"CREATE TABLE {self._schema_prefix()}{self._quote(backup_name)} AS SELECT * FROM {self._full_table()};"
            )

        for col in cols:
            if col["is_deleted"] and not col["is_new"]:
                statements.append(
                    f"ALTER TABLE {self._full_table()} DROP COLUMN {self._quote(col['name'])};"
                )

        for col in cols:
            if not col["is_deleted"] and col["is_new"]:
                nullable = " NOT NULL" if not col["nullable"] else ""
                default_clause = f" DEFAULT {col['default']}" if col["default"] else ""
                statements.append(
                    f"ALTER TABLE {self._full_table()} ADD COLUMN "
                    f"{self._quote(col['name'])} {col['type']}{nullable}{default_clause};"
                )

        if not statements:
            QMessageBox.information(self, "No Changes", "No changes to execute.")
            return

        reply = QMessageBox.warning(
            self, "Confirm Changes",
            f"Execute {len(statements)} statement(s)?\n\n"
            + ("Backup will be created.\n" if self._backup_cb.isChecked() else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._driver.execute_query("BEGIN")
            for sql in statements:
                self._driver.execute_query(sql)
            self._driver.execute_query("COMMIT")
            QMessageBox.information(
                self, "Success",
                f"Table '{self._table}' updated successfully."
                + ("\n\nBackup table created." if self._backup_cb.isChecked() else "")
            )
            self.table_changed.emit()
            self.accept()
        except Exception as e:
            try:
                self._driver.execute_query("ROLLBACK")
            except Exception:
                pass
            QMessageBox.critical(self, "Error", f"Failed to execute changes:\n{e}")
