import json
import os
import uuid
from pathlib import Path

from .crypto_utils import decrypt, encrypt
from .db_drivers.base import ConnectionConfig

CONFIG_DIR = Path.home() / ".config" / "database-manager"
CONNECTIONS_FILE = CONFIG_DIR / "connections.json"


def _ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_connections() -> list[ConnectionConfig]:
    _ensure_config_dir()
    if not CONNECTIONS_FILE.exists():
        return []
    try:
        data = json.loads(CONNECTIONS_FILE.read_text())
        for c in data:
            c["password"] = decrypt(c.get("password", ""))
        return [ConnectionConfig(**c) for c in data]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def save_connections(connections: list[ConnectionConfig]) -> None:
    _ensure_config_dir()
    data = []
    for c in connections:
        d = {
            "name": c.name,
            "type": c.type,
            "host": c.host,
            "port": c.port,
            "user": c.user,
            "password": encrypt(c.password),
            "database": c.database,
            "file_path": c.file_path,
            "charset": c.charset,
        }
        data.append(d)
    CONNECTIONS_FILE.write_text(json.dumps(data, indent=2))


def add_connection(config: ConnectionConfig) -> None:
    conns = load_connections()
    conns.append(config)
    save_connections(conns)


def update_connection(index: int, config: ConnectionConfig) -> None:
    conns = load_connections()
    if 0 <= index < len(conns):
        conns[index] = config
        save_connections(conns)


def delete_connection(index: int) -> None:
    conns = load_connections()
    if 0 <= index < len(conns):
        conns.pop(index)
        save_connections(conns)


def get_default_port(db_type: str) -> int:
    return {
        "postgresql": 5432,
        "mysql": 3306,
        "sqlserver": 1433,
        "sqlite": 0,
    }.get(db_type, 0)
