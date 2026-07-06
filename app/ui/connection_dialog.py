from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QDialogButtonBox, QGroupBox, QGridLayout, QWidget,
    QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

from ..db_drivers.base import ConnectionConfig
from ..connection_manager import get_default_port

DB_TYPES = [
    ("postgresql", "PostgreSQL"),
    ("mysql", "MySQL"),
    ("sqlite", "SQLite"),
    ("sqlserver", "SQL Server"),
]


class ConnectionDialog(QDialog):
    def __init__(self, parent=None, config: ConnectionConfig | None = None):
        super().__init__(parent)
        self._config = config
        self.result_config: ConnectionConfig | None = None
        self.setWindowTitle("New Connection" if config is None else "Edit Connection")
        self.setMinimumWidth(500)
        self._build_ui()
        if config:
            self._load_config(config)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        header = QLabel("Step 1: Select Database Type")
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        type_layout = QHBoxLayout()
        type_layout.setSpacing(8)
        self._type_buttons = {}
        self._selected_type = self._config.type if self._config else "postgresql"
        for key, label in DB_TYPES:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(48)
            btn.setMinimumWidth(100)
            btn.setProperty("db_type", key)
            btn.clicked.connect(lambda checked, k=key: self._select_type(k))
            if not self._config and key == "postgresql":
                btn.setChecked(True)
            elif self._config and key == self._config.type:
                btn.setChecked(True)
            self._type_buttons[key] = btn
            type_layout.addWidget(btn)
        layout.addLayout(type_layout)

        form_group = QGroupBox("Step 2: Connection Details")
        form_layout = QGridLayout(form_group)
        form_layout.setSpacing(8)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("My Database")
        form_layout.addWidget(QLabel("Name:"), 0, 0)
        form_layout.addWidget(self._name_input, 0, 1)

        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("localhost")
        form_layout.addWidget(QLabel("Host:"), 1, 0)
        form_layout.addWidget(self._host_input, 1, 1)

        self._port_input = QLineEdit()
        self._port_input.setPlaceholderText("5432")
        form_layout.addWidget(QLabel("Port:"), 2, 0)
        form_layout.addWidget(self._port_input, 2, 1)

        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("postgres")
        form_layout.addWidget(QLabel("User:"), 3, 0)
        form_layout.addWidget(self._user_input, 3, 1)

        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setPlaceholderText("Optional")
        form_layout.addWidget(QLabel("Password:"), 4, 0)
        form_layout.addWidget(self._password_input, 4, 1)

        self._database_input = QLineEdit()
        self._database_input.setPlaceholderText("database_name")
        form_layout.addWidget(QLabel("Database:"), 5, 0)
        form_layout.addWidget(self._database_input, 5, 1)

        self._file_input = QLineEdit()
        self._file_input.setPlaceholderText("/path/to/database.sqlite")
        self._file_input.setVisible(False)
        self._file_browse_btn = QPushButton("Browse...")
        self._file_browse_btn.setVisible(False)
        self._file_browse_btn.clicked.connect(self._browse_file)
        file_layout = QHBoxLayout()
        file_layout.addWidget(self._file_input)
        file_layout.addWidget(self._file_browse_btn)
        form_layout.addWidget(QLabel("File:"), 5, 0)
        form_layout.addLayout(file_layout, 5, 1)

        layout.addWidget(form_group)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self._test_btn = QPushButton("Test Connection")
        self._test_btn.clicked.connect(self._test_connection)
        btn_box.addWidget(self._test_btn)
        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._save)
        self._save_btn.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; font-weight: bold; }"
            "QPushButton:hover { background: #1d4ed8; }"
        )
        btn_box.addWidget(self._save_btn)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(self._cancel_btn)
        layout.addLayout(btn_box)

        self._update_visibility()

    def _select_type(self, key: str):
        self._selected_type = key
        for k, btn in self._type_buttons.items():
            btn.setChecked(k == key)
        self._update_visibility()

    def _update_visibility(self):
        is_sqlite = self._selected_type == "sqlite"
        is_server = not is_sqlite
        for w in [self._host_input, self._port_input, self._user_input,
                  self._password_input, self._database_input]:
            w.setVisible(is_server)
        for i in range(1, 6):
            self.layout().itemAt(2).widget().layout().itemAtPosition(i, 0).widget().setVisible(is_server)

        self._file_input.setVisible(is_sqlite)
        self._file_browse_btn.setVisible(is_sqlite)
        label = self.layout().itemAt(2).widget().layout().itemAtPosition(5, 0).widget()
        label.setVisible(is_sqlite)

        if is_sqlite:
            self._name_input.setPlaceholderText("My SQLite Database")
        else:
            self._name_input.setPlaceholderText("My Database")
            self._port_input.setText(str(get_default_port(self._selected_type)))

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SQLite Database", "", "SQLite Database (*.sqlite *.sqlite3 *.db *.db3)"
        )
        if path:
            self._file_input.setText(path)

    def _load_config(self, config: ConnectionConfig):
        self._name_input.setText(config.name)
        self._host_input.setText(config.host)
        self._port_input.setText(str(config.port) if config.port else "")
        self._user_input.setText(config.user)
        self._password_input.setText(config.password)
        self._database_input.setText(config.database)
        self._file_input.setText(config.file_path)

    def _get_config(self) -> ConnectionConfig:
        if self._selected_type == "sqlite":
            return ConnectionConfig(
                name=self._name_input.text().strip() or "SQLite DB",
                type=self._selected_type,
                file_path=self._file_input.text().strip(),
            )
        return ConnectionConfig(
            name=self._name_input.text().strip() or f"{self._selected_type} DB",
            type=self._selected_type,
            host=self._host_input.text().strip() or "localhost",
            port=int(self._port_input.text().strip()) if self._port_input.text().strip() else get_default_port(self._selected_type),
            user=self._user_input.text().strip() or "postgres",
            password=self._password_input.text(),
            database=self._database_input.text().strip() or "",
        )

    def _test_connection(self):
        config = self._get_config()
        from ..db_drivers import DRIVERS
        driver_cls = DRIVERS.get(config.type)
        if not driver_cls:
            QMessageBox.critical(self, "Error", f"Unknown database type: {config.type}")
            return
        driver = driver_cls(config)
        try:
            driver.connect()
            driver.disconnect()
            QMessageBox.information(self, "Success", "Connection successful!")
        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", str(e))

    def _save(self):
        config = self._get_config()
        if config.type == "sqlite" and not config.file_path:
            QMessageBox.warning(self, "Missing File", "Please select a SQLite database file.")
            return
        if config.type != "sqlite" and not config.database:
            QMessageBox.warning(self, "Missing Database", "Please enter a database name.")
            return
        self.result_config = config
        self.accept()
