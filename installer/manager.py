import shutil
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel,
    QProgressBar, QHBoxLayout, QPushButton,
)
from PySide6.QtCore import Qt, QTimer

APP_NAME = "database-manager"
DISPLAY_NAME = "Database Manager"
MARKER_DIR = Path.home() / ".local" / "share" / APP_NAME
MARKER_FILE = MARKER_DIR / "installed"
BIN_DIR = Path.home() / ".local" / "bin"
BIN_PATH = BIN_DIR / APP_NAME
DESKTOP_DIR = Path.home() / ".local" / "share" / "applications"
DESKTOP_FILE = DESKTOP_DIR / f"{APP_NAME}.desktop"
ICON_DIR = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
ICON_PATH = ICON_DIR / f"{APP_NAME}.svg"
CONFIG_DIR = Path.home() / ".config" / APP_NAME


class _ProgressDialog(QDialog):
    def __init__(self, title: str, steps: list[tuple[str, callable]],
                 done_message: str, show_run: bool = False):
        super().__init__(None)
        self._steps = steps
        self._show_run = show_run
        self._done_message = done_message
        self._result_run = False

        self.setWindowTitle(title)
        self.setFixedSize(420, 180)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowFlags(Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._label = QLabel("Starting...")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, len(steps))
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(24)
        layout.addWidget(self._bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._close_btn = QPushButton("Close")
        self._close_btn.setFixedWidth(100)
        self._close_btn.clicked.connect(self._on_close)
        btn_layout.addWidget(self._close_btn)
        self._close_btn.setVisible(False)

        self._run_btn = QPushButton("Run Application")
        self._run_btn.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; font-weight: bold; }"
            "QPushButton:hover { background: #1d4ed8; }"
        )
        self._run_btn.setFixedWidth(140)
        self._run_btn.clicked.connect(self._on_run)
        btn_layout.addWidget(self._run_btn)
        self._run_btn.setVisible(False)

        layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog { background: #1e1e2e; }
            QLabel { color: #cdd6f4; font-size: 13px; }
            QPushButton {
                background: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 8px 16px; font-size: 13px;
            }
            QPushButton:hover { background: #45475a; }
            QProgressBar {
                border: 1px solid #45475a; border-radius: 6px;
                background: #181825; text-align: center;
            }
            QProgressBar::chunk {
                background: #4a9eff; border-radius: 5px;
            }
        """)

    def run_steps(self):
        self.show()
        QApplication.processEvents()

        for i, (label, action) in enumerate(self._steps):
            self._label.setText(label)
            self._bar.setValue(i)
            QApplication.processEvents()
            action()
            QApplication.processEvents()

        self._bar.setValue(len(self._steps))
        self._label.setText(self._done_message)

        self._close_btn.setVisible(True)
        if self._show_run:
            self._run_btn.setVisible(True)
        QApplication.processEvents()

    def _on_close(self):
        self._result_run = False
        self.close()

    def _on_run(self):
        self._result_run = True
        self.close()

    def should_run(self) -> bool:
        return self._result_run


def is_installed() -> bool:
    return MARKER_FILE.exists() and BIN_PATH.exists()


def install(binary_path: str) -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    MARKER_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(binary_path, BIN_PATH)
    BIN_PATH.chmod(0o755)

    icon_src = Path(__file__).parent.parent / "app" / "resources" / "icon.svg"
    if icon_src.exists():
        shutil.copy2(icon_src, ICON_PATH)

    desktop_entry = f"""[Desktop Entry]
Type=Application
Name={DISPLAY_NAME}
Comment=A modern database manager for PostgreSQL, MySQL, SQLite, and SQL Server
Exec={BIN_PATH} --app
Icon={ICON_PATH}
Terminal=false
Categories=Database;Development;Utility;
StartupNotify=true
"""
    DESKTOP_FILE.write_text(desktop_entry)
    MARKER_FILE.write_text("installed")


def uninstall() -> None:
    if BIN_PATH.exists():
        BIN_PATH.unlink()
    if DESKTOP_FILE.exists():
        DESKTOP_FILE.unlink()
    if ICON_PATH.exists():
        ICON_PATH.unlink()
    if MARKER_DIR.exists():
        shutil.rmtree(MARKER_DIR)


def install_with_progress(binary_path: str) -> bool:
    steps = [
        ("Copying application binary...", lambda: _copy_binary(binary_path)),
        ("Installing icon...", lambda: _install_icon()),
        ("Creating desktop entry...", lambda: _create_desktop_entry()),
        ("Finalizing installation...", lambda: _write_marker()),
    ]
    dialog = _ProgressDialog(
        "Installing Database Manager...", steps,
        "Database Manager installed successfully!",
        show_run=True,
    )
    dialog.run_steps()
    dialog.exec()
    return dialog.should_run()


def uninstall_with_progress() -> None:
    steps = [
        ("Removing application binary...", lambda: _remove_if_exists(BIN_PATH)),
        ("Removing icon...", lambda: _remove_if_exists(ICON_PATH)),
        ("Removing desktop entry...", lambda: _remove_if_exists(DESKTOP_FILE)),
        ("Removing configuration...", lambda: _remove_config()),
    ]
    dialog = _ProgressDialog(
        "Uninstalling Database Manager...", steps,
        "Database Manager has been uninstalled.",
        show_run=False,
    )
    dialog.run_steps()
    dialog.exec()


def _copy_binary(binary_path: str) -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary_path, BIN_PATH)
    BIN_PATH.chmod(0o755)


def _install_icon() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    icon_src = Path(__file__).parent.parent / "app" / "resources" / "icon.svg"
    if icon_src.exists():
        shutil.copy2(icon_src, ICON_PATH)


def _create_desktop_entry() -> None:
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    desktop_entry = f"""[Desktop Entry]
Type=Application
Name={DISPLAY_NAME}
Comment=A modern database manager for PostgreSQL, MySQL, SQLite, and SQL Server
Exec={BIN_PATH} --app
Icon={ICON_PATH}
Terminal=false
Categories=Database;Development;Utility;
StartupNotify=true
"""
    DESKTOP_FILE.write_text(desktop_entry)


def _write_marker() -> None:
    MARKER_DIR.mkdir(parents=True, exist_ok=True)
    MARKER_FILE.write_text("installed")


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def _remove_config() -> None:
    if MARKER_DIR.exists():
        shutil.rmtree(MARKER_DIR)


def run_app() -> None:
    from app.main_window import MainWindow
    from app.ui.theme import apply_theme

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName(DISPLAY_NAME)
    app.setOrganizationName("DatabaseManager")
    apply_theme(app, dark=True)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
