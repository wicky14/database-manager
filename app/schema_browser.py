import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QMenu, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtGui import QIcon, QAction

from .icon_manager import IconManager

TREE_STATE_FILE = Path.home() / ".config" / "database-manager" / "tree_state.json"


class SchemaBrowser(QWidget):
    select_top_requested = Signal(str, str, str)
    select_all_requested = Signal(str, str, str)
    count_requested = Signal(str, str, str)
    describe_requested = Signal(str, str, str)
    indexes_requested = Signal(str, str, str)
    export_csv_requested = Signal(str, str, str)
    export_json_requested = Signal(str, str, str)
    drop_requested = Signal(str, str, str)
    truncate_table_requested = Signal(str, str)
    new_query_requested = Signal()
    refresh_requested = Signal()
    connect_requested = Signal(int, object)
    edit_data_requested = Signal(str, str)
    edit_table_requested = Signal(str, str)
    edit_view_requested = Signal(str, str)
    edit_routine_requested = Signal(str, str)
    edit_trigger_requested = Signal(str)
    create_table_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_connection = None
        self._saved_connections = []
        self._conn_section = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search tables, views, routines...")
        self._search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search_input)

        self._tree = QTreeWidget()
        self._tree.installEventFilter(self)
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setAnimated(True)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._context_menu)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemCollapsed.connect(self._on_item_collapsed)
        self._tree.setDragEnabled(False)

        layout.addWidget(self._tree)

    def _load_icon(self, name: str) -> QIcon:
        return IconManager.get_icon(name)

    def _get_item_path(self, item) -> str:
        parts = [item.text(0)]
        parent = item.parent()
        while parent:
            parts.append(parent.text(0))
            parent = parent.parent()
        return " > ".join(reversed(parts))

    def _collect_expanded_paths(self) -> list[str]:
        paths = []
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.isExpanded():
                paths.append(self._get_item_path(item))
            for i in range(item.childCount()):
                stack.append(item.child(i))
        return paths

    def _restore_expanded_paths(self, paths: set):
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.childCount() > 0:
                item.setExpanded(self._get_item_path(item) in paths)
            for i in range(item.childCount()):
                stack.append(item.child(i))

    def _save_tree_state(self):
        paths = self._collect_expanded_paths()
        try:
            TREE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            TREE_STATE_FILE.write_text(json.dumps({"expanded": paths}, indent=2))
        except Exception:
            pass

    def _load_tree_state(self) -> set:
        try:
            if TREE_STATE_FILE.exists():
                data = json.loads(TREE_STATE_FILE.read_text())
                return set(data.get("expanded", []))
        except Exception:
            pass
        return set()

    def _on_item_expanded(self, item):
        self._save_tree_state()

    def _on_item_collapsed(self, item):
        self._save_tree_state()

    def set_saved_connections(self, connections) -> None:
        self._saved_connections = list(connections)
        self._rebuild_tree()

    def set_connection(self, driver, connection_name: str):
        self._active_connection = driver
        self._rebuild_tree()

    def _rebuild_tree(self):
        self._tree.blockSignals(True)
        self._tree.clear()

        if self._saved_connections:
            self._conn_section = QTreeWidgetItem(["Connections"])
            self._conn_section.setIcon(0, self._load_icon("connection"))
            self._conn_section.setData(0, Qt.ItemDataRole.UserRole, "saved_connections_header")
            self._conn_section.setFlags(self._conn_section.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._tree.addTopLevelItem(self._conn_section)

            for i, conn in enumerate(self._saved_connections):
                item = QTreeWidgetItem([conn.name or f"{conn.type}:{conn.database}  ({conn.host})"])
                item.setIcon(0, self._load_icon(conn.type))
                item.setData(0, Qt.ItemDataRole.UserRole, "saved_connection")
                item.setData(0, Qt.ItemDataRole.UserRole + 1, i)
                item.setToolTip(0, f"{conn.type} - {conn.host}:{conn.port}/{conn.database}")
                self._conn_section.addChild(item)

            self._conn_section.setExpanded(True)

        if self._active_connection:
            try:
                cache = self._active_connection.get_schema_cache()
            except Exception as e:
                error_item = QTreeWidgetItem([f"Error: {e}"])
                self._tree.addTopLevelItem(error_item)
                self._tree.blockSignals(False)
                return

            conn_item = QTreeWidgetItem([self._active_connection.config.name])
            conn_item.setIcon(0, self._load_icon("database"))
            conn_item.setData(0, Qt.ItemDataRole.UserRole, "active_connection")
            self._tree.addTopLevelItem(conn_item)

            tables_item = QTreeWidgetItem(["Tables"])
            tables_item.setIcon(0, self._load_icon("table"))
            tables_item.setData(0, Qt.ItemDataRole.UserRole, "table_group")
            conn_item.addChild(tables_item)

            for t in cache.tables:
                table_item = QTreeWidgetItem([f"{t.schema}.{t.name}" if t.schema else t.name])
                table_item.setIcon(0, self._load_icon("table"))
                table_item.setData(0, Qt.ItemDataRole.UserRole, "table")
                table_item.setData(0, Qt.ItemDataRole.UserRole + 1, t.name)
                table_item.setData(0, Qt.ItemDataRole.UserRole + 2, t.schema)
                tables_item.addChild(table_item)

            if cache.views:
                views_item = QTreeWidgetItem(["Views"])
                views_item.setIcon(0, self._load_icon("view"))
                views_item.setData(0, Qt.ItemDataRole.UserRole, "view_group")
                conn_item.addChild(views_item)
                for v in cache.views:
                    view_item = QTreeWidgetItem([f"{v.schema}.{v.name}" if v.schema else v.name])
                    view_item.setIcon(0, self._load_icon("view"))
                    view_item.setData(0, Qt.ItemDataRole.UserRole, "view")
                    view_item.setData(0, Qt.ItemDataRole.UserRole + 1, v.name)
                    view_item.setData(0, Qt.ItemDataRole.UserRole + 2, v.schema)
                    views_item.addChild(view_item)

            if cache.routines:
                routines_item = QTreeWidgetItem(["Functions / Procedures"])
                routines_item.setIcon(0, self._load_icon("routine"))
                routines_item.setData(0, Qt.ItemDataRole.UserRole, "routine_group")
                conn_item.addChild(routines_item)
                for r in cache.routines:
                    routine_item = QTreeWidgetItem([r.name])
                    routine_item.setIcon(0, self._load_icon("routine"))
                    routine_item.setData(0, Qt.ItemDataRole.UserRole, "routine")
                    routine_item.setData(0, Qt.ItemDataRole.UserRole + 1, r.name)
                    routine_item.setData(0, Qt.ItemDataRole.UserRole + 2, r.routine_type)
                    routines_item.addChild(routine_item)

            if cache.triggers:
                triggers_item = QTreeWidgetItem(["Triggers"])
                triggers_item.setIcon(0, self._load_icon("trigger"))
                triggers_item.setData(0, Qt.ItemDataRole.UserRole, "trigger_group")
                conn_item.addChild(triggers_item)
                for t in cache.triggers:
                    trigger_item = QTreeWidgetItem([t])
                    trigger_item.setIcon(0, self._load_icon("trigger"))
                    trigger_item.setData(0, Qt.ItemDataRole.UserRole, "trigger")
                    trigger_item.setData(0, Qt.ItemDataRole.UserRole + 1, t)
                    triggers_item.addChild(trigger_item)

        saved = self._load_tree_state()
        if saved:
            self._restore_expanded_paths(saved)
        elif self._active_connection:
            conn_item.setExpanded(True)
            tables_item.setExpanded(True)
            if cache.views:
                views_item.setExpanded(True)
            if cache.routines:
                routines_item.setExpanded(True)
            if cache.triggers:
                triggers_item.setExpanded(True)

        self._tree.blockSignals(False)

    def refresh_icons(self):
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        icon_map = {
            "saved_connections_header": "connection",
            "saved_connection": None,
            "active_connection": "database",
            "table_group": "table",
            "view_group": "view",
            "routine_group": "routine",
            "trigger_group": "trigger",
            "table": "table",
            "view": "view",
            "routine": "routine",
            "trigger": "trigger",
        }
        while stack:
            item = stack.pop()
            role = item.data(0, Qt.ItemDataRole.UserRole)
            if role == "saved_connection":
                idx = item.data(0, Qt.ItemDataRole.UserRole + 1)
                if 0 <= idx < len(self._saved_connections):
                    item.setIcon(0, self._load_icon(self._saved_connections[idx].type))
            elif role in icon_map:
                icon_name = icon_map[role]
                if icon_name:
                    item.setIcon(0, self._load_icon(icon_name))
            for i in range(item.childCount()):
                stack.append(item.child(i))

    def clear(self):
        self._active_connection = None
        self._rebuild_tree()

    def eventFilter(self, obj, event):
        if obj is self._tree and event.type() == event.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()

            nav_keys = {
                Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
                Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape,
                Qt.Key.Key_Tab, Qt.Key.Key_Backtab, Qt.Key.Key_Space,
                Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End,
                Qt.Key.Key_F5,
            }
            if key in nav_keys or modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
                return False

            self._search_input.setFocus()
            if key == Qt.Key.Key_Backspace:
                text = self._search_input.text()
                self._search_input.setText(text[:-1])
            else:
                self._search_input.setText(event.text())
            return True
        return super().eventFilter(obj, event)

    def _on_search_changed(self, text: str):
        self._filter_tree(text)

    def _filter_tree(self, text: str):
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            self._filter_item(item, text.lower())
        if text:
            self._expand_search_results(self._tree)

    def _filter_item(self, item, text: str) -> bool:
        if item.childCount() == 0:
            visible = not text or text in item.text(0).lower()
            item.setHidden(not visible)
            return visible
        any_visible = False
        for i in range(item.childCount()):
            if self._filter_item(item.child(i), text):
                any_visible = True
        item.setHidden(not any_visible and text != "")
        return any_visible or (not text or text in item.text(0).lower())

    def _expand_search_results(self, root):
        for i in range(root.topLevelItemCount() if isinstance(root, QTreeWidget) else root.childCount()):
            item = root.topLevelItem(i) if isinstance(root, QTreeWidget) else root.child(i)
            if item.childCount() > 0:
                any_visible = False
                for j in range(item.childCount()):
                    child = item.child(j)
                    if not child.isHidden():
                        any_visible = True
                        break
                item.setExpanded(any_visible)
                self._expand_search_results(item)

    def _on_item_clicked(self, item, col):
        role = item.data(0, Qt.ItemDataRole.UserRole)
        if role == "saved_connection":
            idx = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if 0 <= idx < len(self._saved_connections):
                self.connect_requested.emit(idx, self._saved_connections[idx])

    def _context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return

        role = item.data(0, Qt.ItemDataRole.UserRole)

        if role == "saved_connection":
            idx = item.data(0, Qt.ItemDataRole.UserRole + 1)
            conn = self._saved_connections[idx] if 0 <= idx < len(self._saved_connections) else None
            if not conn:
                return
            menu = QMenu(self)
            connect_action = QAction("Connect", self)
            connect_action.triggered.connect(
                lambda: self.connect_requested.emit(idx, conn)
            )
            menu.addAction(connect_action)

            from .connection_manager import delete_connection
            show_source = QAction("Delete", self)
            show_source.triggered.connect(lambda: self._delete_saved_connection(idx))
            menu.addAction(show_source)

            menu.exec(self._tree.mapToGlobal(pos))
            return

        if role == "active_connection":
            menu = QMenu(self)
            disconnect = QAction("Disconnect", self)
            disconnect.triggered.connect(self._disconnect)
            menu.addAction(disconnect)

            refresh = QAction("Refresh", self)
            refresh.triggered.connect(self.refresh_requested.emit)
            menu.addAction(refresh)
            menu.exec(self._tree.mapToGlobal(pos))
            return

        if role in ("table", "view"):
            table_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
            schema = item.data(0, Qt.ItemDataRole.UserRole + 2) or ""
            menu = QMenu(self)

            new_query = QAction("Open New Query", self)
            new_query.triggered.connect(self.new_query_requested.emit)
            menu.addAction(new_query)

            if role == "table":
                edit_data = QAction("Edit Data...", self)
                edit_data.triggered.connect(
                    lambda: self.edit_data_requested.emit(table_name, schema)
                )
                menu.addAction(edit_data)

                edit_table = QAction("Edit Table...", self)
                edit_table.triggered.connect(
                    lambda: self.edit_table_requested.emit(table_name, schema)
                )
                menu.addAction(edit_table)
            else:
                edit_view = QAction("Edit View...", self)
                edit_view.triggered.connect(
                    lambda: self.edit_view_requested.emit(table_name, schema)
                )
                menu.addAction(edit_view)

            menu.addSeparator()

            select_top = QAction("Select Top 100", self)
            select_top.triggered.connect(
                lambda: self.select_top_requested.emit(table_name, schema, role)
            )
            menu.addAction(select_top)

            select_all = QAction("Select All", self)
            select_all.triggered.connect(
                lambda: self.select_all_requested.emit(table_name, schema, role)
            )
            menu.addAction(select_all)

            count = QAction("Count Rows", self)
            count.triggered.connect(
                lambda: self.count_requested.emit(table_name, schema, role)
            )
            menu.addAction(count)

            menu.addSeparator()

            describe = QAction("Describe", self)
            describe.triggered.connect(
                lambda: self.describe_requested.emit(table_name, schema, role)
            )
            menu.addAction(describe)

            indexes = QAction("Show Indexes", self)
            indexes.triggered.connect(
                lambda: self.indexes_requested.emit(table_name, schema, role)
            )
            menu.addAction(indexes)

            menu.addSeparator()

            if role == "table":
                truncate = QAction("Truncate Table...", self)
                truncate.triggered.connect(
                    lambda: self.truncate_table_requested.emit(table_name, schema)
                )
                menu.addAction(truncate)
                menu.addSeparator()

            csv_export = QAction("Export CSV", self)
            csv_export.triggered.connect(
                lambda: self.export_csv_requested.emit(table_name, schema, role)
            )
            menu.addAction(csv_export)

            json_export = QAction("Export JSON", self)
            json_export.triggered.connect(
                lambda: self.export_json_requested.emit(table_name, schema, role)
            )
            menu.addAction(json_export)

            menu.addSeparator()

            drop = QAction("Drop...", self)
            drop.setToolTip(f"DROP {role.upper()} {table_name}")
            drop.triggered.connect(
                lambda: self.drop_requested.emit(table_name, schema, role)
            )
            menu.addAction(drop)

            menu.addSeparator()

            refresh = QAction("Refresh", self)
            refresh.triggered.connect(self.refresh_requested.emit)
            menu.addAction(refresh)

            menu.exec(self._tree.mapToGlobal(pos))
            return

        if role == "table_group":
            menu = QMenu(self)
            new_table = QAction("New Table...", self)
            new_table.triggered.connect(self.create_table_requested.emit)
            menu.addAction(new_table)
            menu.addSeparator()
            refresh = QAction("Refresh", self)
            refresh.triggered.connect(self.refresh_requested.emit)
            menu.addAction(refresh)
            menu.exec(self._tree.mapToGlobal(pos))
            return

        if role in ("view_group", "routine_group", "trigger_group"):
            menu = QMenu(self)
            refresh = QAction("Refresh", self)
            refresh.triggered.connect(self.refresh_requested.emit)
            menu.addAction(refresh)
            menu.exec(self._tree.mapToGlobal(pos))
            return

        if role == "routine":
            table_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
            routine_type = item.data(0, Qt.ItemDataRole.UserRole + 2) or ""
            menu = QMenu(self)
            edit_routine = QAction("Edit Routine...", self)
            edit_routine.triggered.connect(
                lambda: self.edit_routine_requested.emit(table_name, routine_type)
            )
            menu.addAction(edit_routine)
            menu.exec(self._tree.mapToGlobal(pos))
            return

        if role == "trigger":
            trigger_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
            menu = QMenu(self)
            edit_trigger = QAction("Edit Trigger...", self)
            edit_trigger.triggered.connect(
                lambda: self.edit_trigger_requested.emit(trigger_name)
            )
            menu.addAction(edit_trigger)
            menu.exec(self._tree.mapToGlobal(pos))
            return

    def _on_item_double_clicked(self, item, col):
        role = item.data(0, Qt.ItemDataRole.UserRole)
        if role == "table":
            table_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
            schema = item.data(0, Qt.ItemDataRole.UserRole + 2) or ""
            self.edit_data_requested.emit(table_name, schema)
        elif role == "view":
            table_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
            schema = item.data(0, Qt.ItemDataRole.UserRole + 2) or ""
            self.select_top_requested.emit(table_name, schema, role)
        elif role == "saved_connection":
            idx = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if 0 <= idx < len(self._saved_connections):
                self.connect_requested.emit(idx, self._saved_connections[idx])

    def _delete_saved_connection(self, idx):
        if 0 <= idx < len(self._saved_connections):
            from .connection_manager import delete_connection
            delete_connection(idx)
            self._saved_connections.pop(idx)
            self._rebuild_tree()

    def _disconnect(self):
        if self._active_connection:
            try:
                self._active_connection.disconnect()
            except Exception:
                pass
        self._active_connection = None
        self._rebuild_tree()
