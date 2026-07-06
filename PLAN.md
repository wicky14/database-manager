# Database Manager — Plan

## Overview
A modern database manager GUI for Linux (Wayland) supporting PostgreSQL, MySQL, SQLite, and SQL Server. Single-file installer that also serves as uninstaller and application launcher.

## Tech Stack
- **Python 3.14** + **PySide6** (Qt6, Wayland-native, LGPL)
- **psycopg2** — PostgreSQL
- **mysql-connector-python** — MySQL
- **pymssql** — SQL Server
- **sqlite3** — SQLite (built-in)
- **QScintilla** — SQL editor with syntax highlighting + autocomplete
- **PyInstaller** — Single-file packaging
- **PyJWT / keyring** — Password encryption (optional)

## Directory Structure

```
Database/
├── main.py                     # Entry: launch / install / uninstall
├── build.py                    # Auto-venv + PyInstaller build
├── requirements.txt
├── build.spec                  # PyInstaller spec
├── PLAN.md                     # This file
├── app/
│   ├── __init__.py
│   ├── main_window.py          # Main window: sidebar + tabs + toolbar
│   ├── connection_manager.py   # CRUD saved connections (~/.config/database-manager/connections.json)
│   ├── query_editor.py         # QScintilla editor + autocomplete + syntax highlight
│   ├── result_viewer.py        # QTableView + inline editing + export CSV/JSON
│   ├── schema_browser.py       # QTreeView sidebar: tables, views, routines, triggers
│   ├── db_drivers/
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract base driver
│   │   ├── postgres.py
│   │   ├── mysql.py
│   │   ├── sqlite.py
│   │   └── sqlserver.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── connection_dialog.py # Step-by-step connection form
│   │   └── theme.py            # Dark / Light theme manager
│   └── resources/
│       ├── icon.svg
│       ├── postgresql.svg
│       ├── mysql.svg
│       ├── sqlite.svg
│       ├── sqlserver.svg
│       ├── table.svg
│       ├── view.svg
│       ├── routine.svg
│       ├── trigger.svg
│       ├── connection.svg
│       ├── database.svg
│       ├── run.svg
│       ├── stop.svg
│       ├── save.svg
│       ├── export.svg
│       ├── new_query.svg
│       ├── refresh.svg
│       └── delete.svg
└── installer/
    ├── __init__.py
    └── manager.py              # Install / uninstall logic
```

## Visual Design

### Layout (3-panel)

```
┌───────────────────────────────────────────────┐
│  Database Manager  │  db@host     │─  □  ✕    │
├──────┬────────────────────────────────────────┤
│      │  [New Tab +]  Tab 1 │ Tab 2           │
│  📁  ├────────────────────────────────────────┤
│  All  │  ┌─────────────────────────────────┐  │
│  Conns │  │  SELECT * FROM users           │  │
│       │  │  LIMIT 10;                      │  │
│  mydb │  │                                  │  │
│  ├─📋 │  │                                  │  │
│  │  📊 │  └─────────────────────────────────┘  │
│  ├─⚡  │  [▶ Run (F5)]  [⏹ Stop]  [💾 Save]  │
│  │  🔁 │  ├─────────────────────────────────┤  │
│  │     │  │ id │ name  │ email         │ age│  │
│  │     │  ├────┼───────┼───────────────┼────┤  │
│  │     │  │ 1  │ Alice │ a@x.com       │ 25 │  │
│  │     │  │ 2  │ Bob   │ b@x.com       │ 30 │  │
│  │     │  └────┴───────┴───────────────┴────┘  │
│  │     │  2 rows in 3ms      [📥 CSV] [📥 JSON]│
│       │                                         │
├───────┴─────────────────────────────────────────┤
│  🐘 mydb (postgres@localhost:5432)              │
└─────────────────────────────────────────────────┘
```

### No Emoji — professional SVG icons for all UI elements

### Theme
- Modern flat design, rounded corners (8px), subtle shadows
- **Sidebar**: 240px collapsible, dark (#1e1e2e) or light
- **Editor**: Monospace font, SQL syntax highlighting
- **Result table**: Alternating rows, sortable columns, inline editing
- **Accent color**: Blue (#4a9eff) — configurable

## Features

### Connection Management
- Save/load connections to `~/.config/database-manager/connections.json`
- Step-by-step connection dialog with big visual DB type selector
- Test connection button
- Password save (encrypted via keyring) or prompt each time
- Quick search saved connections

### Schema Browser (Sidebar)
- Tree view: Databases → Schemas → Tables / Views / Routines / Triggers
- Search/filter box above tree
- **Right-click menu on table:**
  - Open New Query
  - Select Top 100
  - Select All
  - Count Rows
  - Describe Table
  - Show Indexes
  - Export CSV
  - Export JSON
  - Edit Table (alter dialog)
  - Drop Table (with confirmation)
  - Refresh
- **Right-click on view:** Select Top 100, Describe, Refresh
- **Right-click on routine:** Show Source, Refresh
- **Right-click on trigger:** Show Source, Refresh
- **Double-click table/view:** Open tab with `SELECT * FROM table LIMIT 100`

### Query Editor (QScintilla)
- SQL syntax highlighting
- Autocomplete: keywords, table names, column names, function names
- Context-aware: detect alias after `FROM users u`
- Trigger after 3 chars or `.` (schema.table)
- Line numbers
- Multiple tabs (draggable, renameable)
- Execute selected query or entire editor
- Stop running query
- Transaction toggle (auto-commit ON/OFF, Commit, Rollback buttons)
- Query history (navigate with arrow keys)
- Search in query (Ctrl+F)
- **Format SQL** (right-click → Format SQL, or `Ctrl+Shift+F`) via `sqlparse`
  - Keywords → uppercase
  - Consistent indentation
  - Line breaks after clauses
  - Format entire query or selected text only
- **Dependency:** `sqlparse>=0.5.0`

### Result Viewer
- QTableView with sortable, resizable columns
- Inline cell editing (double-click to edit, save via button)
- Insert row / Delete row
- Filter per column
- Pagination for large result sets
- Export: CSV, JSON (with file dialog)
- Execution time display in status bar

### Routine / Stored Procedure Editor
- View routines in schema browser (Functions/Procedures node)
- Double-click → open source in editor tab
- Save routine: `CREATE OR REPLACE` / `ALTER` + execute

### Supported Databases & Capabilities

| Feature | PostgreSQL | MySQL | SQLite | SQL Server |
|---|---|---|---|---|
| Connect | ✅ | ✅ | ✅ | ✅ |
| Browse Tables | ✅ | ✅ | ✅ | ✅ |
| Browse Views | ✅ | ✅ | ✅ | ✅ |
| Browse Routines | ✅ | ✅ | ❌ | ✅ |
| Browse Triggers | ✅ | ✅ | ✅ | ✅ |
| Read Routine Source | ✅ | ✅ | ❌ | ✅ |
| Save Routine | ✅ | ✅ | ❌ | ✅ |
| Describe | ✅ | ✅ | ✅ | ✅ |
| Indexes | ✅ | ✅ | ✅ | ✅ |
| Export | ✅ | ✅ | ✅ | ✅ |
| Inline Edit | ✅ | ✅ | ✅ | ✅ |

## Installer / Uninstaller (Single File)

### Flow
```
Double-click installer (or built binary):

1. Check marker: ~/.local/share/database-manager/installed
   │
   ├─ NOT FOUND → INSTALL:
   │   ├─ Create ~/.local/share/database-manager/
   │   ├─ Copy binary → ~/.local/bin/database-manager
   │   ├─ Create desktop entry → ~/.local/share/applications/database-manager.desktop
   │   ├─ Copy icon → ~/.local/share/icons/hicolor/scalable/apps/database-manager.svg
   │   ├─ Write marker
   │   └─ Show: "✅ Database Manager installed! Launch from app menu."
   │
   └─ FOUND → UNINSTALL:
       ├─ Remove binary
       ├─ Remove desktop entry
       ├─ Remove icon
       ├─ Remove config (~/.config/database-manager/) [optional: ask]
       ├─ Remove marker
       └─ Show: "Database Manager uninstalled."

2. If launched from desktop entry (with --app flag):
   → Skip install/uninstall → run application normally.
```

### Build System
```
./build.py
├── Create venv/ if missing
├── pip install -r requirements.txt
├── pyinstaller build.spec --onefile --windowed
└── Output: dist/database-manager
```

## Data Storage

| Path | Purpose |
|---|---|
| `~/.local/share/database-manager/installed` | Installation marker |
| `~/.config/database-manager/connections.json` | Saved connections |
| `~/.config/database-manager/settings.json` | App preferences (theme, window size, etc.) |
| `~/.local/bin/database-manager` | Installed binary |
| `~/.local/share/applications/database-manager.desktop` | Desktop entry |
| `~/.local/share/icons/hicolor/scalable/apps/database-manager.svg` | App icon |

## Build Dependencies

```
PySide6>=6.11.0
psycopg2-binary>=2.9.0
mysql-connector-python>=8.0.0
pymssql>=2.2.0
PyQt6.QtScintilla>=2.14.0
sqlparse>=0.5.0
pyinstaller>=6.0.0
keyring>=25.0.0
```

## Performance & Reliability

### Connection
- **Connection pooling** — reuse existing connection, don't create new per query
- **Timeout** — 10s default, configurable
- **Keepalive** — periodic ping, auto-reconnect prompt on lost connection

### Schema Caching
- Cache schema in memory after first load (tables, columns, views, routines)
- Refresh only on explicit user action or reconnect
- No `information_schema` query on every tree expand

### Query Execution
- **Separate QThread** for every query — UI never freezes
- **Cancellable** — kill the query thread, not the connection
- **Streaming / pagination** — fetch 500 rows initially, load more on scroll
- **Parameterized queries** for all internal metadata queries

### Autocomplete
- Build prefix index in memory at connect time
- O(1) lookup via prefix matching
- Refresh cache when schema changes

### Error Handling
- Catch all DB driver exceptions with clear messages (line number, detail)
- Transaction mode OFF by default (no accidental writes)
- Type validation before inline edit save
- Validate SQL before execution (empty, comment-only)

### Expected Performance Targets

| Operation | Target |
|---|---|
| Connect (local) | < 1s |
| Connect (remote) | < 3s |
| Load schema (50 tables) | < 500ms |
| Autocomplete popup | < 100ms |
| Result render (1000 rows) | < 200ms |
| Format SQL (100 lines) | < 50ms |

## Future (Post-MVP)

- SSH tunnel support
- SSL/TLS config per connection
- Visual query builder
- ER diagram viewer
- Table data import (CSV, JSON)
- Multiple result tabs per query
- Database diff / migration generation
