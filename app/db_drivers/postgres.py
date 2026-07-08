import psycopg2
import psycopg2.extras
from typing import Any

from .base import BaseDriver, ConnectionConfig, SchemaCache, TableInfo, ColumnInfo, RoutineInfo


class PostgreSQLDriver(BaseDriver):
    def connect(self) -> None:
        if self._connection and self._connection.closed == 0:
            return
        self._connection = psycopg2.connect(
            host=self.config.host,
            port=self.config.port or 5432,
            user=self.config.user,
            password=self.config.password,
            dbname=self.config.database,
            connect_timeout=10,
        )
        self._connection.autocommit = False
        self._cache = None

    def disconnect(self) -> None:
        if self._connection and self._connection.closed == 0:
            self._connection.close()
        self._connection = None
        self._cache = None

    def is_connected(self) -> bool:
        return self._connection is not None and self._connection.closed == 0

    def ping(self) -> bool:
        try:
            if not self._connection or self._connection.closed != 0:
                return False
            cur = self._connection.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return True
        except Exception:
            return False

    def execute_query(self, sql: str) -> tuple[list[str], list[list[Any]], str | None]:
        if not self._connection or self._connection.closed != 0:
            raise RuntimeError("Not connected")
        cur = self._connection.cursor()
        try:
            cur.execute(sql)
            if cur.description:
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                rows = [[_convert_pg_value(c) for c in r] for r in rows]
                cur.close()
                return columns, rows, None
            else:
                if not self._in_transaction:
                    self._connection.commit()
                cur.close()
                return [], [], f"Query OK, {cur.rowcount} rows affected"
        except Exception as e:
            if not self._in_transaction:
                self._connection.rollback()
            cur.close()
            raise

    def get_schema_cache(self) -> SchemaCache:
        if self._cache:
            return self._cache
        cache = SchemaCache()
        with self._connection.cursor() as cur:
            cur.execute("""
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
            """)
            for row in cur.fetchall():
                schema = "" if row[0] == "public" else row[0]
                cache.tables.append(TableInfo(name=row[1], schema=schema))

            cur.execute("""
                SELECT table_schema, table_name
                FROM information_schema.views
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
            """)
            for row in cur.fetchall():
                schema = "" if row[0] == "public" else row[0]
                cache.views.append(TableInfo(name=row[1], schema=schema))

            cur.execute("""
                SELECT n.nspname, p.proname, p.prorettype::regtype::text,
                       CASE WHEN p.prokind = 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END
                FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY n.nspname, p.proname
            """)
            for row in cur.fetchall():
                cache.routines.append(RoutineInfo(
                    name=row[1],
                    routine_type=row[3],
                    return_type=row[2],
                ))

            cur.execute("""
                SELECT event_object_schema, trigger_name
                FROM information_schema.triggers
                ORDER BY event_object_schema, trigger_name
            """)
            cache.triggers = [row[1] for row in cur.fetchall()]

            cur.execute("""
                SELECT table_name, column_name, data_type, is_nullable, column_default,
                       (SELECT TRUE FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        WHERE tc.table_name = c.table_name
                          AND kcu.column_name = c.column_name
                          AND tc.constraint_type = 'PRIMARY KEY'
                          AND tc.table_schema = c.table_schema) as is_pk
                FROM information_schema.columns c
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
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

        self._cache = cache
        return cache

    def get_table_columns(self, table: str, schema: str = "") -> list[ColumnInfo]:
        cur = self._connection.cursor()
        if schema:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default,
                       (SELECT TRUE FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        WHERE tc.table_name = %s
                          AND kcu.column_name = c.column_name
                          AND tc.constraint_type = 'PRIMARY KEY'
                          AND tc.table_schema = c.table_schema) as is_pk
                FROM information_schema.columns c
                WHERE table_name = %s AND table_schema = %s
                ORDER BY ordinal_position
            """, (table, table, schema))
        else:
            cur.execute("""
                SELECT column_name, data_type, is_nullable, column_default,
                       (SELECT TRUE FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        WHERE tc.table_name = %s
                          AND kcu.column_name = c.column_name
                          AND tc.constraint_type = 'PRIMARY KEY'
                          AND tc.table_schema = c.table_schema) as is_pk
                FROM information_schema.columns c
                WHERE table_name = %s
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY ordinal_position
            """, (table, table))
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
        if schema:
            cur.execute("""
                SELECT pg_get_viewdef(c.oid, true)
                FROM pg_class c
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE c.relname = %s AND n.nspname = %s AND c.relkind = 'v'
            """, (view, schema))
        else:
            cur.execute("""
                SELECT pg_get_viewdef(c.oid, true)
                FROM pg_class c
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE c.relname = %s
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                  AND c.relkind = 'v'
            """, (view,))
        result = cur.fetchone()
        cur.close()
        if result:
            return f"CREATE OR REPLACE VIEW \"{view}\" AS\n{result[0]};"
        return ""

    def get_routine_source(self, routine: str, routine_type: str) -> str:
        cur = self._connection.cursor()
        if routine_type == "PROCEDURE":
            cur.execute("SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid WHERE p.proname = %s", (routine,))
        else:
            cur.execute("SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid WHERE p.proname = %s", (routine,))
        result = cur.fetchone()
        cur.close()
        return result[0] if result else ""

    def save_routine(self, routine: str, routine_type: str, source: str) -> None:
        cur = self._connection.cursor()
        try:
            cur.execute(source)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cur.close()

    def get_indexes(self, table: str, schema: str = "") -> list[dict[str, Any]]:
        cur = self._connection.cursor()
        if schema:
            cur.execute("""
                SELECT i.relname, a.attname, ix.indisunique, ix.indisprimary
                FROM pg_index ix
                JOIN pg_class t ON t.oid = ix.indrelid
                JOIN pg_class i ON i.oid = ix.indexrelid
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
                JOIN pg_namespace n ON t.relnamespace = n.oid
                WHERE t.relname = %s AND n.nspname = %s
                ORDER BY i.relname, a.attnum
            """, (table, schema))
        else:
            cur.execute("""
                SELECT i.relname, a.attname, ix.indisunique, ix.indisprimary
                FROM pg_index ix
                JOIN pg_class t ON t.oid = ix.indrelid
                JOIN pg_class i ON i.oid = ix.indexrelid
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
                JOIN pg_namespace n ON t.relnamespace = n.oid
                WHERE t.relname = %s
                  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY i.relname, a.attnum
            """, (table,))
        indexes = {}
        for row in cur.fetchall():
            name = row[0]
            if name not in indexes:
                indexes[name] = {"name": name, "unique": row[2], "primary": row[3], "columns": []}
            indexes[name]["columns"].append(row[1])
        cur.close()
        return list(indexes.values())

    def cancel_query(self) -> None:
        if self._connection and self._connection.closed == 0:
            self._connection.cancel()

    def get_trigger_source(self, trigger: str) -> str:
        cur = self._connection.cursor()
        cur.execute("""
            SELECT pg_get_triggerdef(t.oid)
            FROM pg_trigger t
            JOIN pg_class c ON t.tgrelid = c.oid
            WHERE t.tgname = %s AND NOT t.tgisinternal
        """, (trigger,))
        result = cur.fetchone()
        cur.close()
        return result[0] if result else ""

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


def _convert_pg_value(val: Any) -> Any:
    if isinstance(val, memoryview):
        return bytes(val).decode("utf-8", errors="replace")
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    if isinstance(val, dict):
        return str(val)
    return val
