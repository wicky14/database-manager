from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor

DARK_THEME = {
    "window": "#1e1e2e",
    "window_text": "#cdd6f4",
    "base": "#181825",
    "alternate_base": "#313244",
    "text": "#cdd6f4",
    "button": "#313244",
    "button_text": "#cdd6f4",
    "highlight": "#4a9eff",
    "highlight_text": "#ffffff",
    "tooltip_base": "#313244",
    "tooltip_text": "#cdd6f4",
    "link": "#89b4fa",
    "bright_text": "#ffffff",
}

LIGHT_THEME = {
    "window": "#f5f5f5",
    "window_text": "#1e1e2e",
    "base": "#ffffff",
    "alternate_base": "#e8e8e8",
    "text": "#1e1e2e",
    "button": "#e0e0e0",
    "button_text": "#1e1e2e",
    "highlight": "#2563eb",
    "highlight_text": "#ffffff",
    "tooltip_base": "#333333",
    "tooltip_text": "#ffffff",
    "link": "#2563eb",
    "bright_text": "#000000",
}

SYNTAX_COLORS = {
    "keyword": "#c678dd",
    "function": "#61afef",
    "string": "#98c379",
    "number": "#d19a66",
    "comment": "#5c6370",
    "operator": "#56b6c2",
    "type": "#e5c07b",
    "builtin": "#61afef",
}

SYNTAX_COLORS_LIGHT = {
    "keyword": "#7c3aed",
    "function": "#2563eb",
    "string": "#16a34a",
    "number": "#d97706",
    "comment": "#9ca3af",
    "operator": "#0891b2",
    "type": "#b45309",
    "builtin": "#2563eb",
}


def apply_theme(app, dark: bool = True):
    colors = DARK_THEME if dark else LIGHT_THEME
    pal = QPalette()

    pal.setColor(QPalette.ColorRole.Window, QColor(colors["window"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(colors["window_text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(colors["base"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["alternate_base"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(colors["button"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(colors["button_text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(colors["highlight"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["highlight_text"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["tooltip_base"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["tooltip_text"]))
    pal.setColor(QPalette.ColorRole.Link, QColor(colors["link"]))
    pal.setColor(QPalette.ColorRole.BrightText, QColor(colors["bright_text"]))

    app.setPalette(pal)

    style = f"""
        QMainWindow {{ background: {colors["window"]}; }}
        QTreeView {{
            background: {colors["base"]};
            color: {colors["text"]};
            border: none;
            font-size: 13px;
        }}
        QTreeView::item {{
            padding: 4px 8px;
        }}
        QTreeView::item:selected {{
            background: {colors["highlight"]};
            color: {colors["highlight_text"]};
        }}
        QTreeView::item:hover {{
            background: {colors["alternate_base"]};
        }}
        QPlainTextEdit {{
            background: {colors["base"]};
            color: {colors["text"]};
            border: 1px solid {colors["alternate_base"]};
            font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
            font-size: 13px;
        }}
        QTabWidget::pane {{
            background: {colors["base"]};
            border: none;
            border-top: 1px solid {colors["alternate_base"]};
        }}
        QTabWidget::tab-bar {{
            alignment: left;
        }}
        QTabBar {{
            background: {colors["window"]};
            border: none;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {colors["button_text"]};
            padding: 6px 16px;
            border: none;
            border-bottom: 2px solid transparent;
            margin-right: 0px;
        }}
        QTabBar::tab:selected {{
            color: {colors["highlight"]};
            border-bottom: 2px solid {colors["highlight"]};
        }}
        QTabBar::tab:hover:!selected {{
            background: {colors["alternate_base"]};
        }}
        QMenuBar {{
            background: {colors["window"]};
            color: {colors["window_text"]};
            border-bottom: 1px solid {colors["alternate_base"]};
        }}
        QMenuBar::item:selected {{
            background: {colors["highlight"]};
            color: {colors["highlight_text"]};
        }}
        QMenu {{
            background: {colors["base"]};
            color: {colors["text"]};
            border: 1px solid {colors["alternate_base"]};
        }}
        QMenu::item:selected {{
            background: {colors["highlight"]};
            color: {colors["highlight_text"]};
        }}
        QToolBar {{
            background: {colors["window"]};
            border: none;
            border-bottom: 1px solid {colors["alternate_base"]};
            spacing: 2px;
            padding: 1px;
        }}
        QToolButton {{
            background: transparent;
            color: {colors["text"]};
            border: none;
            border-radius: 4px;
            padding: 3px 6px;
            font-size: 12px;
        }}
        QToolButton:hover {{
            background: {colors["alternate_base"]};
        }}
        QPushButton {{
            background: {colors["button"]};
            color: {colors["button_text"]};
            border: 1px solid {colors["alternate_base"]};
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 12px;
        }}
        QPushButton:hover {{
            background: {colors["highlight"]};
            color: {colors["highlight_text"]};
        }}
        QPushButton:pressed {{
            background: {colors["highlight"]};
        }}
        QPushButton:checked {{
            background: {colors["highlight"]};
            color: {colors["highlight_text"]};
            border: 2px solid {colors["link"]};
        }}
        QLineEdit {{
            background: {colors["base"]};
            color: {colors["text"]};
            border: 1px solid {colors["alternate_base"]};
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 12px;
        }}
        QLineEdit:focus {{
            border-color: {colors["highlight"]};
        }}
        QComboBox {{
            background: {colors["base"]};
            color: {colors["text"]};
            border: 1px solid {colors["alternate_base"]};
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 12px;
        }}
        QComboBox:focus {{
            border-color: {colors["highlight"]};
        }}
        QComboBox QAbstractItemView {{
            background: {colors["base"]};
            color: {colors["text"]};
            selection-background-color: {colors["highlight"]};
        }}
        QStatusBar {{
            background: {colors["window"]};
            color: {colors["window_text"]};
            border-top: 1px solid {colors["alternate_base"]};
            font-size: 12px;
        }}
        QTableWidget {{
            background: {colors["base"]};
            color: {colors["text"]};
            border: 1px solid {colors["alternate_base"]};
            gridline-color: {colors["alternate_base"]};
            font-size: 12px;
        }}
        QTableWidget::item {{
            padding: 4px 8px;
        }}
        QTableWidget::item:selected {{
            background: {colors["highlight"]};
            color: {colors["highlight_text"]};
        }}
        QTableWidget QLineEdit {{
            border: 1px solid {colors["alternate_base"]};
            border-radius: 0;
            padding: 0 2px;
            margin: -1px;
            background: {colors["base"]};
            color: {colors["text"]};
        }}
        QHeaderView::section {{
            background: {colors["button"]};
            color: {colors["button_text"]};
            border: none;
            border-right: 1px solid {colors["alternate_base"]};
            border-bottom: 1px solid {colors["alternate_base"]};
            padding: 6px 8px;
            font-weight: bold;
        }}
        QSplitter::handle {{
            background: {colors["alternate_base"]};
            width: 2px;
        }}
        QScrollBar:vertical {{
            background: {colors["window"]};
            width: 10px;
        }}
        QScrollBar::handle:vertical {{
            background: {colors["alternate_base"]};
            border-radius: 5px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {colors["text"]};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: {colors["window"]};
            height: 10px;
        }}
        QScrollBar::handle:horizontal {{
            background: {colors["alternate_base"]};
            border-radius: 5px;
            min-width: 30px;
        }}
        QCheckBox {{
            color: {colors["text"]};
            spacing: 8px;
        }}
        QGroupBox {{
            color: {colors["text"]};
            border: 1px solid {colors["alternate_base"]};
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 16px;
            font-size: 13px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }}
        QDialog {{
            background: {colors["window"]};
        }}
        QLabel {{
            color: {colors["text"]};
        }}
    """
    app.setStyleSheet(style)


def get_syntax_colors(dark: bool = True):
    return SYNTAX_COLORS if dark else SYNTAX_COLORS_LIGHT
