# Database Manager

A multi-database management GUI built with PySide6. Supports PostgreSQL, MySQL, SQLite, and SQL Server.

## Features

- **Multi-database support** — PostgreSQL, MySQL, SQLite, SQL Server
- **Query editor** — SQL syntax highlighting (QScintilla), autocomplete, multi-statement execution
- **Schema browser** — Tree view of tables, views, routines, triggers with type-ahead search
- **Trigger editing** — View and edit trigger source code with syntax highlighting
- **Inline data editing** — Add/delete rows, cell editing, sort by column, filter with WHERE/ORDER BY (autocomplete on WHERE/ORDER BY fields)
- **Table designer** — Add/drop/reorder columns with live SQL preview
- **Column header customization** — Drag to reorder columns, resize column widths, numeric sorting
- **Copy selected cells** — Right-click → Copy Selected copies tab/line-separated text
- **Pagination** — Server-side LIMIT/OFFSET for large result sets
- **Export** — CSV and JSON export (auto-appends extension)
- **Tab persistence** — Saves open query and data editor tabs across sessions
- **Dark/light theme** — Toggle between themes
- **Console panel** — Execution log for multi-statement queries

## Supported Databases

| Database   | Library               | Notes                        |
|------------|-----------------------|------------------------------|
| PostgreSQL | psycopg2-binary       |                              |
| MySQL      | mysql-connector-python|                              |
| SQLite     | sqlite3 (built-in)    |                              |
| SQL Server | pymssql               | Supports `GO` batch separator|

## Screenshot

<img width="1496" height="860" alt="fix" src="https://github.com/user-attachments/assets/7eb47866-1c6b-48c5-8e4a-d26a19836e32" />



## Installation

### From source

```bash
# Clone the repository
git clone https://github.com/yourusername/database-manager.git
cd database-manager

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run
python main.py --app
```

### Build standalone binary

```bash
python build.py
```

The executable will be at `dist/database-manager`.

## Usage

1. **Connect** — Click the connection button or `File → New Connection`
2. **Browse schema** — Use the sidebar to explore tables, views, routines, and triggers
3. **Query** — Open a query tab, write SQL, and click Run (or `Ctrl+Enter`)
4. **Edit data** — Right-click a table → "Edit Data" (or `Ctrl+Click`)
5. **Export** — Use the export buttons in the result viewer toolbar

### Multi-statement queries

Separate statements with a blank line or semicolon (`;`):

```sql
SELECT * FROM users

SELECT * FROM orders
```

A line containing only `--` also acts as a separator:

```sql
SELECT * FROM users
--
SELECT * FROM orders
```

Each statement's result appears in its own tab with individual pagination. The console shows how many statements were detected.

## Keyboard Shortcuts

| Shortcut      | Action            |
|---------------|-------------------|
| `Ctrl+Enter`  | Run query         |
| `Ctrl+Shift+F`| Format SQL        |
| `Ctrl+W`      | Close tab         |
| `Ctrl+Tab`    | Next tab          |

## Project Structure

```
Database/
├── app/
│   ├── db_drivers/       # Database drivers (PostgreSQL, MySQL, SQLite, SQL Server)
│   ├── ui/               # UI components (connection dialog, console, data editor, etc.)
│   ├── resources/        # SVG icons
│   ├── main_window.py    # Main window with sidebar, tabs, toolbar
│   ├── query_editor.py   # SQL editor with syntax highlighting
│   ├── result_viewer.py  # Result table with pagination, export, inline editing
│   ├── schema_browser.py # Tree view sidebar
│   ├── connection_manager.py  # Saved connection CRUD
│   ├── icon_manager.py   # SVG icon rendering
│   └── tab_state_manager.py   # Session persistence
├── main.py               # Entry point / installer
├── build.py              # Build script
├── requirements.txt
└── README.md
```

## Data Storage

- **Connections:** `~/.config/database-manager/connections.json`
- **Tab state:** `~/.config/database-manager/tabs_state.json`
- **Query history:** `~/.config/database-manager/query_history.json`

## License

MIT
