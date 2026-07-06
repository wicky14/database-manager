import json
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QTabWidget

from .query_editor import QueryEditor
from .ui.data_editor import DataEditor

TABS_STATE_FILE = Path.home() / ".config" / "database-manager" / "tabs_state.json"


def collect_tabs(tabs: QTabWidget) -> list[dict[str, Any]]:
    data = []
    for i in range(tabs.count()):
        widget = tabs.widget(i)
        title = tabs.tabText(i)

        editor = widget.findChild(QueryEditor)
        if editor:
            sql = editor.toPlainText()
            data.append({
                "type": "query",
                "title": title,
                "sql": sql,
            })
            continue

        data_editor = widget.findChild(DataEditor)
        if data_editor:
            data.append({
                "type": "data_editor",
                "title": title,
                "table": data_editor._table,
                "schema": data_editor._schema,
            })
            continue

    return data


def save_tabs(tabs: QTabWidget):
    try:
        data = collect_tabs(tabs)
        TABS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        TABS_STATE_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def load_tabs() -> list[dict[str, Any]]:
    try:
        if TABS_STATE_FILE.exists():
            data = json.loads(TABS_STATE_FILE.read_text())
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def clear_saved_tabs():
    try:
        TABS_STATE_FILE.unlink(missing_ok=True)
    except Exception:
        pass
