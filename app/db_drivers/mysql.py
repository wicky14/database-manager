import mysql.connector
from typing import Any

from .base import BaseDriver, ConnectionConfig, SchemaCache, TableInfo, ColumnInfo, RoutineInfo


class MySQLDriver(BaseDriver):
    def connect(self) -> None:
        if self._connection and self._connection.is_connected():
            return
        self._connection = mysql.connector.connect(
            host=self.config.host,
            port=self.config.port or 3306,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            connect_timeout=10,
            charset="utf8mb4",
        )
        self._connection.autocommit = False
        self._cache = None

    def disconnect(self) -> None:
        if self._connection and self._connection.is_connected():
            self._connection.close()
        self._connection = None
        self._cache = None

    def is_connected(self) -> bool:
        return self._connection is not None and self._connection.is_connected()

    def ping(self) -> bool:
        try:
            if not self._connection or not self._connection.is_connected():
                return False
            self._connection.ping(reconnect=False, attempts=1)
            return True
        except Exception:
            return False

    def execute_query(self, sql: str) -> tuple[list[str], list[list[Any]], str | None]:
        if not self._connection or not self._connection.is_connected():
            raise RuntimeError("Not connected")
        cur = self._connection.cursor()
        try:
            cur.execute(sql)
            if cur.with_rows:
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
        cur = self._connection.cursor()

        cur.execute("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema = DATABASE()
            ORDER BY table_name
        """)
        for row in cur.fetchall():
            cache.tables.append(TableInfo(name=row[1], schema=row[0]))

        cur.execute("""
            SELECT table_schema, table_name
            FROM information_schema.views
            WHERE table_schema = DATABASE()
            ORDER BY table_name
        """)
        for row in cur.fetchall():
            cache.views.append(TableInfo(name=row[1], schema=row[0]))

        cur.execute("""
            SELECT ROUTINE_NAME, ROUTINE_TYPE, DTD_IDENTIFIER
            FROM information_schema.routines
            WHERE routine_schema = DATABASE()
            ORDER BY routine_name
        """)
        for row in cur.fetchall():
            cache.routines.append(RoutineInfo(
                name=row[0],
                routine_type=row[1],
                return_type=row[2] or "",
            ))

        cur.execute("""
            SELECT trigger_name FROM information_schema.triggers
            WHERE trigger_schema = DATABASE()
        """)
        cache.triggers = [row[0] for row in cur.fetchall()]

        cur.close()
        self._cache = cache
        return cache

    def get_table_columns(self, table: str, schema: str = "") -> list[ColumnInfo]:
        cur = self._connection.cursor()
        cur.execute(f"""
            SELECT column_name, data_type, is_nullable, column_default,
                   column_key = 'PRI' as is_pk
            FROM information_schema.columns
            WHERE table_name = '{table}'
              AND table_schema = DATABASE()
            ORDER BY ordinal_position
        """)
        cols = []
        for row in cur.fetchall():
            cols.append(ColumnInfo(
                name=row[0],
                data_type=row[1],
                nullable=row[2] == 'YES',
                default=row[3],
                is_pk=bool(row[4]),
            ))
        cur.close()
        return cols

    def get_view_source(self, view: str, schema: str = "") -> str:
        cur = self._connection.cursor()
        cur.execute(f"SHOW CREATE VIEW `{view}`")
        result = cur.fetchone()
        cur.close()
        if result:
            return result[1]
        return ""

    def get_routine_source(self, routine: str, routine_type: str) -> str:
        cur = self._connection.cursor()
        cur.execute(f"SHOW CREATE {'PROCEDURE' if routine_type == 'PROCEDURE' else 'FUNCTION'} `{routine}`")
        result = cur.fetchone()
        cur.close()
        if result:
            return result[2] if routine_type == "PROCEDURE" else result[2]
        return ""

    def save_routine(self, routine: str, routine_type: str, source: str) -> None:
        cur = self._connection.cursor()
        try:
            for stmt in source.split(";;"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt, multi=True)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cur.close()

    def get_indexes(self, table: str, schema: str = "") -> list[dict[str, Any]]:
        cur = self._connection.cursor()
        cur.execute(f"SHOW INDEX FROM `{table}`")
        indexes = {}
        for row in cur.fetchall():
            name = row[2]
            if name not in indexes:
                indexes[name] = {"name": name, "unique": not row[1], "primary": row[2] == "PRIMARY", "columns": []}
            indexes[name]["columns"].append(row[4])
        cur.close()
        return list(indexes.values())

    def cancel_query(self) -> None:
        if self._connection and self._connection.is_connected():
            cur = self._connection.cursor()
            try:
                cur.execute(f"KILL QUERY {self._connection.connection_id}")
            except Exception:
                pass
            cur.close()

    def get_trigger_source(self, trigger: str) -> str:
        cur = self._connection.cursor()
        cur.execute(f"SHOW CREATE TRIGGER `{trigger}`")
        result = cur.fetchone()
        cur.close()
        return result[2] if result else ""

    def save_trigger(self, trigger: str, source: str) -> None:
        cur = self._connection.cursor()
        try:
            cur.execute(source, multi=True)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cur.close()
