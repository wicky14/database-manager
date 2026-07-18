import pymysql
from typing import Any

from .base import BaseDriver, ConnectionConfig, SchemaCache, TableInfo, ColumnInfo, RoutineInfo


class MySQLDriver(BaseDriver):
    def connect(self) -> None:
        if self._connection and self._connection.open:
            return
        self._connection = pymysql.connect(
            host=self.config.host,
            port=self.config.port or 3306,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            connect_timeout=10,
            charset=self.config.charset or "utf8mb4",
            autocommit=False,
        )
        self._cache = None

    def disconnect(self) -> None:
        if self._connection and self._connection.open:
            self._connection.close()
        self._connection = None
        self._cache = None

    def is_connected(self) -> bool:
        return self._connection is not None and self._connection.open

    def ping(self) -> bool:
        try:
            if not self._connection or not self._connection.open:
                return False
            self._connection.ping()
            return True
        except Exception:
            return False

    def execute_query(self, sql: str) -> tuple[list[str], list[list[Any]], str | None]:
        if not self._connection or not self._connection.open:
            raise RuntimeError("Not connected")
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
        cur = self._connection.cursor()
        try:
            cur.execute("""
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema = DATABASE()
                ORDER BY table_name
            """)
            for row in cur.fetchall():
                schema = "" if row[0] == self.config.database else row[0]
                cache.tables.append(TableInfo(name=row[1], schema=schema))

            cur.execute("""
                SELECT table_schema, table_name
                FROM information_schema.views
                WHERE table_schema = DATABASE()
                ORDER BY table_name
            """)
            for row in cur.fetchall():
                schema = "" if row[0] == self.config.database else row[0]
                cache.views.append(TableInfo(name=row[1], schema=schema))

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

            cur.execute("""
                SELECT table_name, column_name, data_type, is_nullable,
                       column_default, column_key = 'PRI' as is_pk
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                ORDER BY table_name, ordinal_position
            """)
            for row in cur.fetchall():
                col = ColumnInfo(
                    name=row[1],
                    data_type=row[2],
                    nullable=row[3] == 'YES',
                    default=row[4],
                    is_pk=bool(row[5]),
                )
                cache.columns.setdefault(row[0], []).append(col)
        finally:
            cur.close()
        self._cache = cache
        return cache

    @staticmethod
    def _quote_id(name: str) -> str:
        return "`" + name.replace("`", "``") + "`"

    def get_table_columns(self, table: str, schema: str = "") -> list[ColumnInfo]:
        cur = self._connection.cursor()
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default,
                   column_key = 'PRI' as is_pk
            FROM information_schema.columns
            WHERE table_name = %s
              AND table_schema = DATABASE()
            ORDER BY ordinal_position
        """, (table,))
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
        cur.execute(f"SHOW CREATE VIEW {self._quote_id(view)}")
        result = cur.fetchone()
        cur.close()
        if result:
            return result[1]
        return ""

    def get_routine_source(self, routine: str, routine_type: str) -> str:
        cur = self._connection.cursor()
        cur.execute(f"SHOW CREATE {'PROCEDURE' if routine_type == 'PROCEDURE' else 'FUNCTION'} {self._quote_id(routine)}")
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
                    cur.execute(stmt)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cur.close()

    def get_indexes(self, table: str, schema: str = "") -> list[dict[str, Any]]:
        cur = self._connection.cursor()
        cur.execute(f"SHOW INDEX FROM {self._quote_id(table)}")
        indexes = {}
        for row in cur.fetchall():
            name = row[2]
            if name not in indexes:
                indexes[name] = {"name": name, "unique": not row[1], "primary": row[2] == "PRIMARY", "columns": []}
            indexes[name]["columns"].append(row[4])
        cur.close()
        return list(indexes.values())

    def cancel_query(self) -> None:
        if self._connection and self._connection.open:
            cur = self._connection.cursor()
            try:
                cur.execute(f"KILL QUERY {self._connection.thread_id()}")
            except Exception:
                pass
            cur.close()

    def get_table_ddl(self, table: str, schema: str = "") -> str:
        cur = self._connection.cursor()
        try:
            name = f"{self._quote_id(schema)}." if schema else ""
            name += self._quote_id(table)
            cur.execute(f"SHOW CREATE TABLE {name}")
            result = cur.fetchone()
            return result[1] if result else ""
        finally:
            cur.close()

    def get_trigger_source(self, trigger: str) -> str:
        cur = self._connection.cursor()
        cur.execute(f"SHOW CREATE TRIGGER {self._quote_id(trigger)}")
        result = cur.fetchone()
        cur.close()
        return result[2] if result else ""

    def save_trigger(self, trigger: str, source: str) -> None:
        cur = self._connection.cursor()
        try:
            cur.execute(source)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cur.close()
