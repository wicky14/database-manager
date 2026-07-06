from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QTabWidget, QWidget, QVBoxLayout,
    QToolBar, QMenuBar, QStatusBar, QMessageBox, QApplication,
    QFileDialog, QInputDialog, QCheckBox, QLabel,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
from PySide6.QtGui import QAction, QIcon, QKeySequence

import json
import re
import warnings
from pathlib import Path

from .schema_browser import SchemaBrowser
from .query_editor import QueryEditor
from .result_viewer import ResultViewer
from .ui.connection_dialog import ConnectionDialog
from .ui.data_editor import DataEditor
from .ui.edit_table_dialog import EditTableDialog
from .ui.query_history_dialog import QueryHistoryDialog
from .ui.console import ConsolePanel
from .ui.spinner import SpinnerOverlay
from .connection_manager import (
    load_connections, add_connection, delete_connection,
)
from .db_drivers import DRIVERS
from .db_drivers.base import ConnectionConfig
from .icon_manager import IconManager

RESOURCE_DIR = Path(__file__).parent / "resources"
HISTORY_FILE = Path.home() / ".config" / "database-manager" / "query_history.json"

DB_TYPE_NAMES = {
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "sqlserver": "SQL Server",
}


class QueryThread(QThread):
    finished = Signal(list, list, str)
    error = Signal(str)

    def __init__(self, driver, sql):
        super().__init__()
        self._driver = driver
        self._sql = sql

    def run(self):
        try:
            columns, rows, message = self._driver.execute_query(self._sql)
            self.finished.emit(columns, rows, message)
        except Exception as e:
            self.error.emit(str(e))


class LoadSourceThread(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, driver, obj_name: str, schema_or_type: str, source_type: str):
        super().__init__()
        self._driver = driver
        self._obj_name = obj_name
        self._schema_or_type = schema_or_type
        self._source_type = source_type

    def run(self):
        try:
            if self._source_type == "view":
                source = self._driver.get_view_source(self._obj_name, self._schema_or_type)
            elif self._source_type == "trigger":
                source = self._driver.get_trigger_source(self._obj_name)
            else:
                source = self._driver.get_routine_source(self._obj_name, self._schema_or_type)
            self.finished.emit(source)
        except Exception as e:
            self.error.emit(str(e))


class ConnectionThread(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, driver_cls, config):
        super().__init__()
        self._driver_cls = driver_cls
        self._config = config
        self.driver = None

    def run(self):
        try:
            driver = self._driver_cls(self._config)
            driver.connect()
            driver.get_schema_cache()
            self.driver = driver
            self.finished.emit(driver)
        except Exception as e:
            self.error.emit(str(e))


_SQLITE_THREAD_WARN = (
    "Use the correct database connection.\n"
    "Current connection cannot be used for this query.\n"
    "Please reconnect or restart the application."
)


def is_paginatable(sql: str) -> bool:
    s = sql.strip().lstrip()
    if not s.upper().startswith("SELECT"):
        return False
    if "SELECT INTO" in s.upper()[:50]:
        return False
    if len(split_sql_statements(sql)) > 1:
        return False
    return True


def build_count_sql(sql: str) -> str:
    sql = sql.strip().rstrip(";").strip()
    return f"SELECT COUNT(*) AS _total FROM ({sql}) AS _cnt"


def build_page_sql(sql: str, db_type: str, page: int, page_size: int) -> str:
    sql = sql.strip().rstrip(";").strip()
    offset = (page - 1) * page_size
    limit = page_size
    if db_type == "sqlserver":
        return f"SELECT * FROM ({sql}) AS _p ORDER BY (SELECT NULL) OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
    return f"{sql} LIMIT {limit} OFFSET {offset}"


def split_sql_statements(sql: str) -> list[str]:
    sql = sql.strip()
    if not sql:
        return []
    sql = re.sub(r"^\s*--\s*$", "", sql, flags=re.MULTILINE)
    s = re.sub(r"\n\s*\n", ";", sql)
    stmts = []
    current = []
    in_string = False
    string_char = None
    for ch in s:
        if in_string:
            current.append(ch)
            if ch == string_char:
                in_string = False
        elif ch in ("'", '"'):
            in_string = True
            string_char = ch
            current.append(ch)
        elif ch == ";":
            stmts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    remaining = "".join(current).strip()
    if remaining:
        stmts.append(remaining)
    return [s for s in stmts if s]


class PaginatedQueryThread(QThread):
    finished = Signal(list, list, str, int)  # columns, rows, message, total
    error = Signal(str)

    def __init__(self, driver, sql, db_type, page, page_size):
        super().__init__()
        self._driver = driver
        self._original_sql = sql
        self._db_type = db_type
        self._page = page
        self._page_size = page_size

    def run(self):
        try:
            count_sql = build_count_sql(self._original_sql)
            data_sql = build_page_sql(self._original_sql, self._db_type, self._page, self._page_size)

            _, count_rows, _ = self._driver.execute_query(count_sql)
            total = int(count_rows[0][0]) if count_rows else 0

            columns, rows, message = self._driver.execute_query(data_sql)
            self.finished.emit(columns, rows, message, total)
        except Exception as e:
            self.error.emit(str(e))


class MultiQueryThread(QThread):
    finished = Signal(list, list)  # results: [(columns, rows, sql)], logs: [(display, detail, ok)]
    error = Signal(str)

    def __init__(self, driver, statements, db_type):
        super().__init__()
        self._driver = driver
        self._statements = statements
        self._db_type = db_type

    def run(self):
        results = []
        logs = []
        for stmt in self._statements:
            try:
                cols, rows, msg = self._driver.execute_query(stmt)
                results.append((cols, rows, stmt))
                display = stmt.strip()[:120]
                if cols:
                    logs.append((display, f"{len(rows)} rows returned", True))
                else:
                    logs.append((display, msg or "Query executed", True))
            except Exception as e:
                self.error.emit(str(e))
                return
        self.finished.emit(results, logs)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._driver = None
        self._active_connection_index = -1
        self._query_thread = None
        self._current_db_type = ""
        self._query_history = []
        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._load_saved_connections()
        self._load_query_history()
        self._restore_tabs()

    def _load_icon(self, name: str) -> QIcon:
        return IconManager.get_icon(name)

    def _build_ui(self):
        self.setWindowTitle("Database Manager")
        self.resize(900, 600)
        self.setMinimumSize(640, 480)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._schema = SchemaBrowser()
        self._schema.setMinimumWidth(220)
        self._schema.setMaximumWidth(400)
        self._schema.select_top_requested.connect(self._on_select_top)
        self._schema.select_all_requested.connect(self._on_select_all)
        self._schema.count_requested.connect(self._on_count_rows)
        self._schema.describe_requested.connect(self._on_describe)
        self._schema.indexes_requested.connect(self._on_indexes)
        self._schema.export_csv_requested.connect(self._on_export_csv)
        self._schema.export_json_requested.connect(self._on_export_json)
        self._schema.drop_requested.connect(self._on_drop)
        self._schema.new_query_requested.connect(self._new_query_tab)
        self._schema.refresh_requested.connect(self._refresh_schema)
        self._schema.connect_requested.connect(self._on_connect_requested)
        self._schema.edit_data_requested.connect(self._on_edit_data)
        self._schema.edit_table_requested.connect(self._on_edit_table)
        self._schema.edit_view_requested.connect(self._on_edit_view)
        self._schema.edit_routine_requested.connect(self._on_edit_routine)
        self._schema.edit_trigger_requested.connect(self._on_edit_trigger)
        self._schema.truncate_table_requested.connect(self._on_truncate_table)
        splitter.addWidget(self._schema)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.setMovable(True)
        right_layout.addWidget(self._tabs)

        splitter.addWidget(right_panel)
        splitter.setSizes([260, 940])

        self.setCentralWidget(splitter)
        self.statusBar().showMessage("Ready")

        self._new_query_tab()

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        new_conn = QAction("New Connection...", self)
        new_conn.setShortcut(QKeySequence("Ctrl+Shift+N"))
        new_conn.triggered.connect(self._new_connection)
        file_menu.addAction(new_conn)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        query_menu = menubar.addMenu("&Query")
        run_action = QAction("Run Query", self)
        run_action.setShortcut(QKeySequence("F5"))
        run_action.triggered.connect(self._run_current_query)
        query_menu.addAction(run_action)

        fmt_action = QAction("Format SQL", self)
        fmt_action.setShortcut(QKeySequence("Ctrl+Shift+F"))
        fmt_action.triggered.connect(self._format_current_query)
        query_menu.addAction(fmt_action)

        view_menu = menubar.addMenu("&View")

        toggle_sidebar = QAction("Toggle Sidebar", self)
        toggle_sidebar.setShortcut(QKeySequence("Ctrl+B"))
        toggle_sidebar.triggered.connect(self._toggle_sidebar)
        view_menu.addAction(toggle_sidebar)

        view_menu.addSeparator()

        self._dark_mode_action = QAction("Dark Mode", self)
        self._dark_mode_action.setCheckable(True)
        self._dark_mode_action.setChecked(True)
        self._dark_mode_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(self._dark_mode_action)

        help_menu = menubar.addMenu("&Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_toolbar(self):
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))

        self._toolbar_actions = []

        new_conn_action = toolbar.addAction(self._load_icon("connection"), "New Connection")
        new_conn_action.triggered.connect(self._new_connection)
        self._toolbar_actions.append((new_conn_action, "connection"))
        toolbar.addSeparator()

        new_query_action = toolbar.addAction(self._load_icon("new_query"), "New Query")
        new_query_action.setShortcut(QKeySequence("Ctrl+N"))
        new_query_action.triggered.connect(self._new_query_tab)
        toolbar.addAction(new_query_action)
        self._toolbar_actions.append((new_query_action, "new_query"))

        run_action = toolbar.addAction(self._load_icon("run"), "Run Query (F5)")
        run_action.triggered.connect(self._run_current_query)
        toolbar.addAction(run_action)
        self._toolbar_actions.append((run_action, "run"))

        stop_action = toolbar.addAction(self._load_icon("stop"), "Stop")
        stop_action.triggered.connect(self._stop_query)
        toolbar.addAction(stop_action)
        self._toolbar_actions.append((stop_action, "stop"))

        toolbar.addSeparator()

        refresh_action = toolbar.addAction(self._load_icon("refresh"), "Refresh Schema")
        refresh_action.triggered.connect(self._refresh_schema)
        toolbar.addAction(refresh_action)
        self._toolbar_actions.append((refresh_action, "refresh"))

        toolbar.addSeparator()

        history_action = toolbar.addAction(self._load_icon("history"), "Query History")
        history_action.triggered.connect(self._show_query_history)
        toolbar.addAction(history_action)
        self._toolbar_actions.append((history_action, "history"))

    def _new_connection(self):
        dialog = ConnectionDialog(self)
        if dialog.exec() == ConnectionDialog.DialogCode.Accepted:
            config = dialog.result_config
            if config:
                add_connection(config)
                self._connect_to(config, len(load_connections()) - 1)
                self._refresh_saved_connections()

    def _on_connect_requested(self, idx, config):
        if self._driver:
            try:
                self._driver.disconnect()
            except Exception:
                pass
        self._connect_to(config, idx)

    def _refresh_saved_connections(self):
        try:
            conns = load_connections()
            self._schema.set_saved_connections(conns)
        except Exception:
            pass

    def _connect_to(self, config: ConnectionConfig, index: int):
        driver_cls = DRIVERS.get(config.type)
        if not driver_cls:
            QMessageBox.critical(self, "Error", f"Unknown database type: {config.type}")
            return

        self.statusBar().showMessage(f"Connecting to {config.name}...")

        self._spinner = SpinnerOverlay(self)
        self._spinner.show()
        QApplication.processEvents()

        self._conn_thread = ConnectionThread(driver_cls, config)
        self._conn_thread.finished.connect(
            lambda driver: self._on_connected(driver, config, index))
        self._conn_thread.error.connect(
            lambda err: self._on_connect_error(err, config))
        self._conn_thread.start()

    def _on_connected(self, driver, config, index):
        self._spinner.hide()
        self._driver = driver
        self._active_connection_index = index
        self._current_db_type = config.type

        db_name = DB_TYPE_NAMES.get(config.type, config.type)
        self.setWindowTitle(f"Database Manager - {config.name} ({db_name})")
        self.statusBar().showMessage(f"Connected to {config.name}")

        self._schema.set_connection(driver, config.name)
        self._update_editor_schema()

    def _on_connect_error(self, error, config):
        self._spinner.hide()
        QMessageBox.critical(self, "Connection Failed",
                             f"Could not connect to {config.name}:\n{error}")
        self.statusBar().showMessage("Connection failed")

    def _update_editor_schema(self):
        if not self._driver:
            return
        try:
            cache = self._driver.get_schema_cache()
            tables = [t.name for t in cache.tables]
            views = [v.name for v in cache.views]
            routines = [r.name for r in cache.routines]

            columns_map = {}
            for t in cache.tables:
                cols = cache.columns.get(t.name, [])
                columns_map[t.name] = [c.name for c in cols]

            for i in range(self._tabs.count()):
                editor = self._tabs.widget(i).findChild(QueryEditor)
                if editor:
                    editor.set_schema(tables, views, routines, columns_map)
        except Exception:
            pass

    def _load_saved_connections(self):
        try:
            conns = load_connections()
            self._schema.set_saved_connections(conns)
        except Exception:
            return

    def _quote_object(self, name: str) -> str:
        if not name:
            return name
        if self._current_db_type == "sqlserver":
            return f"[{name}]"
        return f'"{name}"'

    def _on_select_top(self, table: str, schema: str, obj_type: str):
        quoted = self._quote_object(table)
        schema_prefix = f"{self._quote_object(schema)}." if schema else ""
        if self._current_db_type == "sqlserver":
            self._open_query_tab(f"SELECT TOP 100 *\nFROM {schema_prefix}{quoted}")
        else:
            self._open_query_tab(f"SELECT *\nFROM {schema_prefix}{quoted}\nLIMIT 100")

    def _on_select_all(self, table: str, schema: str, obj_type: str):
        quoted = self._quote_object(table)
        schema_prefix = f"{self._quote_object(schema)}." if schema else ""
        self._open_query_tab(f"SELECT *\nFROM {schema_prefix}{quoted}")

    def _on_count_rows(self, table: str, schema: str, obj_type: str):
        quoted = self._quote_object(table)
        schema_prefix = f"{self._quote_object(schema)}." if schema else ""
        self._run_sql_direct(f"SELECT COUNT(*) as cnt FROM {schema_prefix}{quoted}")

    def _on_describe(self, table: str, schema: str, obj_type: str):
        db_type = self._current_db_type
        if db_type == "postgresql":
            quoted = f'"{table}"'
            schema_prefix = f'"{schema}".' if schema else ""
            self._run_sql_direct(
                f"SELECT column_name, data_type, is_nullable, column_default "
                f"FROM information_schema.columns "
                f"WHERE table_name = '{table}'"
            )
        elif db_type == "mysql":
            self._run_sql_direct(f"DESCRIBE `{table}`")
        elif db_type == "sqlite":
            self._run_sql_direct(f"PRAGMA table_info('{table}')")
        elif db_type == "sqlserver":
            self._run_sql_direct(
                f"SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT "
                f"FROM INFORMATION_SCHEMA.COLUMNS "
                f"WHERE TABLE_NAME = '{table}'"
            )

    def _on_indexes(self, table: str, schema: str, obj_type: str):
        if not self._driver:
            return
        try:
            indexes = self._driver.get_indexes(table, schema)
            if not indexes:
                QMessageBox.information(self, "Indexes", f"No indexes found for {table}")
                return
            columns = ["Name", "Columns", "Unique", "Primary"]
            rows = []
            for idx in indexes:
                rows.append([
                    idx["name"],
                    ", ".join(idx["columns"]),
                    "Yes" if idx["unique"] else "No",
                    "Yes" if idx["primary"] else "No",
                ])
            self._show_custom_results(columns, rows, f"Indexes for {table}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_export_csv(self, table: str, schema: str, obj_type: str):
        self._on_select_all(table, schema, obj_type)

    def _on_export_json(self, table: str, schema: str, obj_type: str):
        self._on_select_all(table, schema, obj_type)

    def _on_drop(self, table: str, schema: str, obj_type: str):
        reply = QMessageBox.warning(
            self, "Confirm Drop",
            f"Are you sure you want to DROP {obj_type} '{table}'?\n\nThis cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            quoted = self._quote_object(table)
            self._run_sql_direct(f"DROP {obj_type.upper()} {quoted}")

    def _on_edit_data(self, table: str, schema: str, title: str = ""):
        if not self._driver:
            QMessageBox.warning(self, "Not Connected", "Please connect to a database first.")
            return
        try:
            data_editor = DataEditor(self._driver, table, schema)
            data_editor.status_message.connect(self.statusBar().showMessage)
            tab_title = title or f"{schema + '.' if schema else ''}{table} -- Editing"
            self._tabs.addTab(data_editor, tab_title)
            self._tabs.setCurrentWidget(data_editor)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_edit_table(self, table: str, schema: str):
        if not self._driver:
            QMessageBox.warning(self, "Not Connected", "Please connect to a database first.")
            return
        try:
            dialog = EditTableDialog(self._driver, table, schema)
            dialog.table_changed.connect(self._refresh_schema)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_edit_view(self, view: str, schema: str):
        if not self._driver:
            QMessageBox.warning(self, "Not Connected", "Please connect to a database first.")
            return

        self._open_query_tab("-- Loading view source...")

        widget = self._tabs.currentWidget()
        editor = widget.findChild(QueryEditor)
        console = widget.findChild(ConsolePanel)

        self._load_thread = LoadSourceThread(self._driver, view, schema, "view")
        self._load_thread.finished.connect(
            lambda source: self._on_view_loaded(editor, console, view, schema, source)
        )
        self._load_thread.error.connect(
            lambda err: self._on_edit_source_error(editor, console, view, err)
        )
        self._load_thread.start()

    def _on_view_loaded(self, editor, console, view, schema, source):
        quoted = self._quote_object(view)
        schema_prefix = f"{self._quote_object(schema)}." if schema else ""
        if self._current_db_type == "sqlserver":
            sql = f"{source}\nGO\n\n-- SELECT TOP 100 *\nSELECT TOP 100 *\nFROM {schema_prefix}{quoted}"
        else:
            sql = f"{source}\n\n-- SELECT *\nSELECT *\nFROM {schema_prefix}{quoted}\nLIMIT 100"
        editor.setPlainText(sql)
        editor.setReadOnly(False)
        display = f"{schema + '.' if schema else ''}{view}"
        log_msg = f"View source loaded ({len(source)} chars)"
        if console:
            console.add_entry(display, log_msg, True)

    def _on_edit_source_error(self, editor, console, name, error):
        editor.setPlainText(f"-- Error loading source: {error}")
        if console:
            console.add_entry(name, str(error), False)

    def _on_edit_routine(self, routine: str, routine_type: str):
        if not self._driver:
            QMessageBox.warning(self, "Not Connected", "Please connect to a database first.")
            return

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)

        editor = QueryEditor()
        editor.setPlainText("-- Loading routine source...")
        editor.setReadOnly(True)
        editor.query_requested.connect(self._execute_sql)
        splitter.addWidget(editor)

        bottom_tabs = QTabWidget()
        bottom_tabs.setDocumentMode(True)

        result = ResultViewer()
        result.status_message.connect(self.statusBar().showMessage)
        bottom_tabs.addTab(result, "Result")

        console = ConsolePanel()
        bottom_tabs.addTab(console, "Console")

        splitter.addWidget(bottom_tabs)
        splitter.setSizes([300, 300])
        layout.addWidget(splitter)

        self._tabs.addTab(tab, f"Routine: {routine}")
        self._tabs.setCurrentWidget(tab)
        self._update_editor_schema()
        editor.setFocus()

        self._load_thread = LoadSourceThread(self._driver, routine, routine_type, "routine")
        self._load_thread.finished.connect(
            lambda source: self._on_routine_loaded(editor, console, routine, source)
        )
        self._load_thread.error.connect(
            lambda err: self._on_edit_source_error(editor, console, routine, err)
        )
        self._load_thread.start()

    def _on_routine_loaded(self, editor, console, routine, source):
        editor.setPlainText(source)
        editor.setReadOnly(False)
        log_msg = f"Routine source loaded ({len(source)} chars)"
        if console:
            console.add_entry(routine, log_msg, True)

    def _on_edit_trigger(self, trigger: str):
        if not self._driver:
            QMessageBox.warning(self, "Not Connected", "Please connect to a database first.")
            return

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)

        editor = QueryEditor()
        editor.setPlainText("-- Loading trigger source...")
        editor.setReadOnly(True)
        editor.query_requested.connect(self._execute_sql)
        splitter.addWidget(editor)

        bottom_tabs = QTabWidget()
        bottom_tabs.setDocumentMode(True)

        result = ResultViewer()
        result.status_message.connect(self.statusBar().showMessage)
        bottom_tabs.addTab(result, "Result")

        console = ConsolePanel()
        bottom_tabs.addTab(console, "Console")

        splitter.addWidget(bottom_tabs)
        splitter.setSizes([300, 300])
        layout.addWidget(splitter)

        self._tabs.addTab(tab, f"Trigger: {trigger}")
        self._tabs.setCurrentWidget(tab)
        self._update_editor_schema()
        editor.setFocus()

        self._load_thread = LoadSourceThread(self._driver, trigger, "", "trigger")
        self._load_thread.finished.connect(
            lambda source: self._on_trigger_loaded(editor, console, trigger, source)
        )
        self._load_thread.error.connect(
            lambda err: self._on_edit_source_error(editor, console, trigger, err)
        )
        self._load_thread.start()

    def _on_trigger_loaded(self, editor, console, trigger, source):
        editor.setPlainText(source)
        editor.setReadOnly(False)
        log_msg = f"Trigger source loaded ({len(source)} chars)"
        if console:
            console.add_entry(trigger, log_msg, True)

    def _on_truncate_table(self, table: str, schema: str):
        if not self._driver:
            QMessageBox.warning(self, "Not Connected", "Please connect to a database first.")
            return
        quoted = self._quote_object(table)
        schema_prefix = f"{self._quote_object(schema)}." if schema else ""
        full_name = f"{schema_prefix}{quoted}"

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Truncate Table")
        msg.setText(f"Truncate table '{full_name}'?")
        msg.setInformativeText(
            "This will DELETE ALL ROWS permanently.\n"
            "Table structure will be preserved.\n"
            "Cannot be undone."
        )
        cb = QCheckBox("I understand this cannot be undone")
        msg.setCheckBox(cb)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.button(QMessageBox.StandardButton.Yes).setEnabled(False)
        cb.toggled.connect(
            lambda checked: msg.button(QMessageBox.StandardButton.Yes).setEnabled(checked)
        )
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        if self._current_db_type == "sqlite":
            sql = f"DELETE FROM {full_name}; VACUUM;"
        else:
            sql = f"TRUNCATE TABLE {full_name};"
        self._run_sql_direct(sql)

    def _load_query_history(self):
        try:
            if HISTORY_FILE.exists():
                data = json.loads(HISTORY_FILE.read_text())
                self._query_history = data if isinstance(data, list) else []
        except Exception:
            self._query_history = []

    def _save_query_history(self):
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_FILE.write_text(json.dumps(self._query_history[-100:], indent=2))
        except Exception:
            pass

    def _add_query_history(self, sql: str):
        sql = sql.strip()
        if not sql:
            return
        if self._query_history and self._query_history[-1] == sql:
            return
        self._query_history.append(sql)
        if len(self._query_history) > 100:
            self._query_history = self._query_history[-100:]
        self._save_query_history()

    def _show_query_history(self):
        if not self._query_history:
            QMessageBox.information(self, "Query History", "No query history yet.")
            return
        dialog = QueryHistoryDialog(self._query_history, self)
        if dialog.exec() == QueryHistoryDialog.DialogCode.Accepted:
            sql = dialog.selected_query
            if sql:
                self._open_query_tab(sql)

    def _restore_tabs(self):
        from .tab_state_manager import load_tabs, clear_saved_tabs
        data = load_tabs()
        if not data:
            return
        if self._tabs.count() > 0:
            self._tabs.removeTab(0)
        for tab_info in data:
            try:
                self._restore_one_tab(tab_info)
            except Exception:
                pass
        clear_saved_tabs()
        editor = self._tabs.currentWidget().findChild(QueryEditor)
        if editor:
            editor.setFocus()

    def _restore_one_tab(self, tab_info: dict):
        t = tab_info.get("type", "")
        if t == "query":
            sql = tab_info.get("sql", "")
            title = tab_info.get("title", "")
            self._open_query_tab(sql, title)
        elif t == "data_editor":
            if not self._driver or not self._driver.is_connected():
                return
            table = tab_info.get("table", "")
            schema = tab_info.get("schema", "")
            title = tab_info.get("title", "")
            if table:
                self._on_edit_data(table, schema, title)

    def _new_query_tab(self):
        self._open_query_tab("")

    def _open_query_tab(self, sql: str, title: str = ""):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical)

        editor = QueryEditor()
        if sql:
            editor.setPlainText(sql)
        editor.query_requested.connect(self._execute_sql)
        splitter.addWidget(editor)

        bottom_tabs = QTabWidget()
        bottom_tabs.setDocumentMode(True)

        result = ResultViewer()
        result.status_message.connect(self.statusBar().showMessage)
        bottom_tabs.addTab(result, "Result")

        console = ConsolePanel()
        bottom_tabs.addTab(console, "Console")

        splitter.addWidget(bottom_tabs)

        splitter.setSizes([300, 300])
        layout.addWidget(splitter)

        label = title or f"Query {self._tabs.count() + 1}"
        self._tabs.addTab(tab, label)
        self._tabs.setCurrentWidget(tab)
        self._update_editor_schema()
        editor.setFocus()

    def _run_current_query(self):
        widget = self._tabs.currentWidget()
        if not widget:
            return
        editor = widget.findChild(QueryEditor)
        if editor:
            text = editor.toPlainText().strip()
            cursor = editor.textCursor()
            selected = cursor.selectedText()
            if selected:
                sql = selected.replace("\u2029", "\n").replace("\u2028", "\n")
            else:
                sql = text
            if sql:
                self._execute_sql(sql)

    def _format_current_query(self):
        widget = self._tabs.currentWidget()
        if not widget:
            return
        editor = widget.findChild(QueryEditor)
        if editor:
            editor._format_sql()

    def _execute_sql(self, sql: str):
        if not self._driver:
            QMessageBox.warning(self, "Not Connected", "Please connect to a database first.")
            return

        if not sql.strip():
            return

        widget = self._tabs.currentWidget()
        if not widget:
            return
        result = widget.findChild(ResultViewer)
        if not result:
            return
        console = widget.findChild(ConsolePanel)

        statements = split_sql_statements(sql)

        bottom_tabs = widget.findChild(QTabWidget)
        if bottom_tabs:
            self._clean_extra_tabs(bottom_tabs, console)

        if len(statements) > 1:
            self._execute_multi(statements, result, console, bottom_tabs)
            return

        if bottom_tabs and isinstance(bottom_tabs, QTabWidget) and bottom_tabs.indexOf(result) < 0:
            bottom_tabs.insertTab(0, result, "Result")
            bottom_tabs.setCurrentIndex(0)

        result.clear_results()
        result.show_results([], [], "Executing...")
        self.statusBar().showMessage("Executing query...")

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                result.page_changed.disconnect(self._on_page_changed)
        except TypeError:
            pass
        result.page_changed.connect(self._on_page_changed)

        if is_paginatable(sql):
            self._execute_paginated(sql, result, console)
        else:
            self._execute_single(sql, result, console)

    def _execute_single(self, sql: str, result, console=None):
        self._query_thread = QueryThread(self._driver, sql)
        self._query_thread.finished.connect(
            lambda cols, rows, msg: self._on_query_result(cols, rows, msg, result, console, sql))
        self._query_thread.error.connect(
            lambda err: self._on_query_error(err, result, console))
        self._query_thread.start()

    def _clean_extra_tabs(self, bottom_tabs, console):
        while bottom_tabs.count() > 1:
            w = bottom_tabs.widget(0)
            if w is console:
                break
            bottom_tabs.removeTab(0)

    def _execute_multi(self, statements: list[str], result, console, bottom_tabs):
        self.statusBar().showMessage(f"Executing {len(statements)} statements...")
        if console:
            console.add_entry(
                f"Split into {len(statements)} statements",
                "separator: blank line or ;",
                True
            )
        self._multi_thread = MultiQueryThread(self._driver, statements, self._current_db_type)
        original_sql = "; ".join(statements)
        self._multi_thread.finished.connect(
            lambda results, logs: self._on_multi_result(results, logs, bottom_tabs, console, original_sql))
        self._multi_thread.error.connect(
            lambda err: self._on_multi_error(err, bottom_tabs, console))
        self._multi_thread.start()

    def _execute_paginated(self, sql: str, result, console=None):
        db_type = self._current_db_type
        page_size = 200

        result._page_sql = sql
        result._page_db_type = db_type
        result._page = 1
        result._page_size = page_size

        result.show_results([], [], "Counting rows...")
        self.statusBar().showMessage("Counting rows...")

        self._page_thread = PaginatedQueryThread(self._driver, sql, db_type, 1, page_size)
        self._page_thread.finished.connect(
            lambda cols, rows, msg, total: self._on_paginated_result(cols, rows, msg, total, result, console, sql))
        self._page_thread.error.connect(
            lambda err: self._on_query_error(err, result, console))
        self._page_thread.start()

    def _on_paginated_result(self, columns, rows, message, total, result, console=None, sql=""):
        result.set_pagination(total, result._page, result._page_size)
        self._on_query_result(columns, rows, message, result, console, sql)

    def _on_page_changed(self, page: int, page_size: int):
        result = self.sender()
        if not result or not isinstance(result, ResultViewer) or not hasattr(result, "_page_sql"):
            return
        container = self._tabs.currentWidget()
        bottom_tabs = container.findChild(QTabWidget) if container else None
        console = bottom_tabs.findChild(ConsolePanel) if bottom_tabs else None

        result._page = page
        result._page_size = page_size
        sql = build_page_sql(result._page_sql, result._page_db_type, page, page_size)

        self.statusBar().showMessage(f"Loading page {page}...")

        self._page_thread = QueryThread(self._driver, sql)
        self._page_thread.finished.connect(
            lambda cols, rows, msg: self._on_page_loaded(cols, rows, msg, result, console))
        self._page_thread.error.connect(
            lambda err: self._on_query_error(err, result, console))
        self._page_thread.start()

    def _on_page_loaded(self, columns, rows, message, result, console=None):
        self._on_query_result(columns, rows, message, result, console, result._page_sql)
        total_pages = max(1, (result._total + result._page_size - 1) // result._page_size)
        result.set_pagination(result._total, result._page, result._page_size)
        self.statusBar().showMessage(f"Page {result._page} of {total_pages} | {len(rows)} rows")

    def _run_sql_direct(self, sql: str):
        if not self._driver:
            QMessageBox.warning(self, "Not Connected", "Please connect to a database first.")
            return

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        editor = QueryEditor()
        editor.setPlainText(sql)
        editor.setReadOnly(True)
        layout.addWidget(editor)

        result = ResultViewer()
        result.status_message.connect(self.statusBar().showMessage)
        layout.addWidget(result)

        self._tabs.addTab(tab, "Results")
        self._tabs.setCurrentWidget(tab)
        self._update_editor_schema()

        result.show_results([], [], "Executing...")
        self.statusBar().showMessage("Executing query...")

        self._query_thread = QueryThread(self._driver, sql)
        self._query_thread.finished.connect(lambda cols, rows, msg: self._on_query_result(cols, rows, msg, result))
        self._query_thread.error.connect(lambda err: self._on_query_error(err, result))
        self._query_thread.start()

    def _on_query_result(self, columns, rows, message, result, console=None, sql=""):
        result.show_results(columns, rows, message)
        if sql:
            self._add_query_history(sql)
        if message:
            self.statusBar().showMessage(message)
        else:
            self.statusBar().showMessage(f"Query returned {len(rows)} rows")
        if console:
            display_sql = sql.strip()[:120] if sql else "?"
            if columns:
                console.add_entry(display_sql, f"{len(rows)} rows returned", True)
            else:
                console.add_entry(display_sql, message or "Query executed", True)

    def _on_multi_result(self, results, logs, bottom_tabs, console, original_sql=""):
        console_idx = bottom_tabs.indexOf(console)
        if original_sql:
            self._add_query_history(original_sql)

        result_count = 0
        for cols, rows, stmt in results:
            if not cols:
                continue
            result_count += 1
            rv = ResultViewer()
            rv.status_message.connect(self.statusBar().showMessage)
            rv.show_results(cols, rows, None)

            if is_paginatable(stmt):
                rv._page_sql = stmt
                rv._page_db_type = self._current_db_type
                rv._page = 1
                rv._page_size = 200
                try:
                    rv.set_pagination(len(rows), 1, 200)
                except Exception:
                    pass
                rv.page_changed.connect(self._on_page_changed)

            bottom_tabs.insertTab(console_idx, rv, f"Result {result_count}")
            console_idx += 1

        if result_count == 0:
            info = QLabel("All statements executed (no result sets)")
            info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bottom_tabs.insertTab(console_idx, info, "Result")
            bottom_tabs.setCurrentIndex(console_idx)
        else:
            bottom_tabs.setCurrentIndex(0)

        if console:
            for display, detail, ok in logs:
                console.add_entry(display, detail, ok)

        self.statusBar().showMessage(f"{len(results)} statements, {result_count} with results")

    def _on_multi_error(self, error, bottom_tabs, console):
        self.statusBar().showMessage("Query failed")
        if console:
            console.add_entry("Multi-statement execution", str(error), False)
        if "SQLite objects created in a thread" in str(error):
            QMessageBox.critical(self, "SQLite Threading Error", _SQLITE_THREAD_WARN)
        rv = ResultViewer()
        rv.status_message.connect(self.statusBar().showMessage)
        rv.show_error(error)
        bottom_tabs.insertTab(0, rv, "Error")
        bottom_tabs.setCurrentWidget(rv)

    def _on_query_error(self, error, result, console=None):
        if "SQLite objects created in a thread" in str(error):
            QMessageBox.critical(self, "SQLite Threading Error", _SQLITE_THREAD_WARN)
        result.show_error(error)
        self.statusBar().showMessage("Query failed")
        if console:
            console.add_entry("SQL execution", str(error), False)

    def _stop_query(self):
        if self._query_thread and self._query_thread.isRunning():
            if self._driver:
                try:
                    self._driver.cancel_query()
                except Exception:
                    pass
            self._query_thread.quit()
            self._query_thread.wait(2000)
            self.statusBar().showMessage("Query cancelled")

    def _refresh_schema(self):
        if not self._driver:
            return
        try:
            self._driver._cache = None
            cache = self._driver.get_schema_cache()
            self._schema.set_connection(
                self._driver,
                self._driver.config.name
            )
            self._update_editor_schema()
            self.statusBar().showMessage("Schema refreshed")
        except Exception as e:
            QMessageBox.critical(self, "Refresh Failed", str(e))

    def _show_custom_results(self, columns, rows, title):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        editor = QueryEditor()
        editor.setPlainText(f"-- {title}")
        editor.setReadOnly(True)
        layout.addWidget(editor)

        result = ResultViewer()
        result.status_message.connect(self.statusBar().showMessage)
        layout.addWidget(result)

        self._tabs.addTab(tab, title)
        self._tabs.setCurrentWidget(tab)
        self._update_editor_schema()
        result.show_results(columns, rows)

    def _close_tab(self, index):
        widget = self._tabs.widget(index)
        self._tabs.removeTab(index)
        widget.deleteLater()
        if self._tabs.count() == 0:
            self._new_query_tab()

    def _toggle_sidebar(self):
        self._schema.setVisible(not self._schema.isVisible())

    def _toggle_theme(self, dark: bool):
        from .ui.theme import apply_theme, DARK_THEME, LIGHT_THEME
        from .ui.data_editor import DataEditor
        from .result_viewer import ResultViewer
        apply_theme(QApplication.instance(), dark)
        text_color = (DARK_THEME if dark else LIGHT_THEME)["text"]
        IconManager.set_theme_color(text_color)
        for action, icon_name in self._toolbar_actions:
            action.setIcon(self._load_icon(icon_name))
        self._schema.refresh_icons()
        for i in range(self._tabs.count()):
            widget = self._tabs.widget(i)
            editor = widget.findChild(DataEditor)
            if editor:
                editor.refresh_icons()
            viewer = widget.findChild(ResultViewer)
            if viewer:
                viewer.refresh_icons()

    def _show_about(self):
        QMessageBox.about(
            self, "About Database Manager",
            "Database Manager v1.0\n\n"
            "A modern database management tool\n"
            "supporting PostgreSQL, MySQL, SQLite,\n"
            "and SQL Server.\n\n"
            "Built with Python, PySide6, and Qt6."
        )

    def closeEvent(self, event):
        from .tab_state_manager import save_tabs
        self._save_query_history()
        save_tabs(self._tabs)
        if self._query_thread and self._query_thread.isRunning():
            self._query_thread.quit()
            self._query_thread.wait(2000)
        if self._driver:
            try:
                self._driver.disconnect()
            except Exception:
                pass
        event.accept()
