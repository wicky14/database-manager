import sqlite3
import threading
from typing import Any
from pathlib import Path

from .base import BaseDriver, ConnectionConfig, SchemaCache, TableInfo, ColumnInfo, RoutineInfo


class SQLiteDriver(BaseDriver):
    @staticmethod
    def _quote_id(name: str) -> str:
        escaped = name.replace("'", "''")
        return f"'{escaped}'"

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._lock = threading.Lock()

    def connect(self) -> None:
        if self._connection:
            return
        db_path = self.config.file_path or self.config.database
        if not db_path:
            raise ValueError("SQLite requires a file path")
        self._connection = sqlite3.connect(db_path, check_same_thread=False)
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._cache = None

    def disconnect(self) -> None:
        if self._connection:
            self._connection.close()
        self._connection = None
        self._cache = None

    def is_connected(self) -> bool:
        return self._connection is not None

    def begin(self) -> None:
        self._in_transaction = True
        with self._lock:
            self._connection.execute("BEGIN")

    def ping(self) -> bool:
        try:
            if not self._connection:
                return False
            with self._lock:
                self._connection.execute("SELECT 1")
            return True
        except Exception:
            return False

    def execute_query(self, sql: str) -> tuple[list[str], list[list[Any]], str | None]:
        if not self._connection:
            raise RuntimeError("Not connected")
        with self._lock:
            cur = self._connection.cursor()
            try:
                cur.execute(sql)
                if cur.description:
                    columns = [desc[0] for desc in cur.description]
                    rows = list(cur.fetchall())
                    cur.close()
                    return columns, rows, None
                else:
                    if not self._in_transaction:
                        self._connection.commit()
                    affected = cur.rowcount
                    cur.close()
                    return [], [], f"Query OK, {affected} rows affected"
            except Exception as e:
                if not self._in_transaction:
                    self._connection.rollback()
                cur.close()
                raise

    def get_schema_cache(self) -> SchemaCache:
        if self._cache:
            return self._cache
        cache = SchemaCache()
        with self._lock:
            cur = self._connection.cursor()

            cur.execute("""
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            for row in cur.fetchall():
                cache.tables.append(TableInfo(name=row[0], schema="main"))

            cur.execute("""
                SELECT name FROM sqlite_master
                WHERE type = 'view'
                ORDER BY name
            """)
            for row in cur.fetchall():
                cache.views.append(TableInfo(name=row[0], schema="main"))

            cur.execute("""
                SELECT name FROM sqlite_master
                WHERE type = 'trigger'
                ORDER BY name
            """)
            cache.triggers = [row[0] for row in cur.fetchall()]

            for t in cache.tables:
                cur.execute(f"PRAGMA table_info({self._quote_id(t.name)})")
                cols = []
                for row in cur.fetchall():
                    cols.append(ColumnInfo(
                        name=row[1],
                        data_type=row[2] or "TEXT",
                        nullable=not row[3],
                        default=row[4],
                        is_pk=bool(row[5]),
                    ))
                cache.columns[t.name] = cols

            cur.close()
        self._cache = cache
        return cache

    def get_table_columns(self, table: str, schema: str = "") -> list[ColumnInfo]:
        with self._lock:
            cur = self._connection.cursor()
            cur.execute(f"PRAGMA table_info({self._quote_id(table)})")
            cols = []
            for row in cur.fetchall():
                cols.append(ColumnInfo(
                    name=row[1],
                    data_type=row[2] or "TEXT",
                    nullable=not row[3],
                    default=row[4],
                    is_pk=bool(row[5]),
                ))
            cur.close()
        return cols

    def get_view_source(self, view: str, schema: str = "") -> str:
        with self._lock:
            cur = self._connection.cursor()
            cur.execute("SELECT sql FROM sqlite_master WHERE type='view' AND name=?", (view,))
            result = cur.fetchone()
            cur.close()
        return result[0] if result else ""

    def get_routine_source(self, routine: str, routine_type: str) -> str:
        return ""

    def save_routine(self, routine: str, routine_type: str, source: str) -> None:
        raise NotImplementedError("SQLite does not support stored routines")

    def get_indexes(self, table: str, schema: str = "") -> list[dict[str, Any]]:
        with self._lock:
            cur = self._connection.cursor()
            cur.execute(f"PRAGMA index_list({self._quote_id(table)})")
            indexes = {}
            for row in cur.fetchall():
                name = row[1]
                unique = row[2] == 1
                is_pk = False
                cur2 = self._connection.cursor()
                cur2.execute(f"PRAGMA index_info({self._quote_id(name)})")
                columns = [r[2] for r in cur2.fetchall()]
                cur2.close()
                indexes[name] = {"name": name, "unique": unique, "primary": is_pk, "columns": columns}
            cur.close()
        return list(indexes.values())

    def get_config(self) -> ConnectionConfig:
        return self.config

    def get_trigger_source(self, trigger: str) -> str:
        with self._lock:
            cur = self._connection.cursor()
            cur.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (trigger,))
            result = cur.fetchone()
            cur.close()
        return result[0] if result else ""

    def save_trigger(self, trigger: str, source: str) -> None:
        with self._lock:
            cur = self._connection.cursor()
            try:
                cur.execute(source)
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cur.close()

    @property
    def display_name(self) -> str:
        return f"SQLite:{Path(self.config.file_path or self.config.database).name}"
