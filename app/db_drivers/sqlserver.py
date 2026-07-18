import re
import pymssql
from typing import Any

from .base import BaseDriver, ConnectionConfig, SchemaCache, TableInfo, ColumnInfo, RoutineInfo


class SQLServerDriver(BaseDriver):
    def connect(self) -> None:
        if self._connection:
            return
        self._connection = pymssql.connect(
            server=self.config.host,
            port=str(self.config.port or 1433),
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            timeout=10,
        )
        self._cache = None

    def disconnect(self) -> None:
        if self._connection:
            self._connection.close()
        self._connection = None
        self._cache = None

    def is_connected(self) -> bool:
        return self._connection is not None

    def ping(self) -> bool:
        try:
            if not self._connection:
                return False
            cur = self._connection.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return True
        except Exception:
            return False

    def execute_query(self, sql: str) -> tuple[list[str], list[list[Any]], str | None]:
        if not self._connection:
            raise RuntimeError("Not connected")

        clean = sql.replace("\r\n", "\n").replace("\r", "\n")
        batches = re.split(r'(?:^|\n)\s*GO\s*(?:\n|$)', clean, flags=re.IGNORECASE)
        batches = [b.strip() for b in batches if b.strip()]
        if len(batches) <= 1:
            return self._execute_batch(sql)

        columns, rows, message = [], [], None
        messages = []
        for batch in batches:
            c, r, msg = self._execute_batch(batch)
            if c:
                columns, rows = c, r
            if msg:
                messages.append(msg)
        if messages:
            message = "; ".join(messages)
        return columns, rows, message

    def _execute_batch(self, sql: str) -> tuple[list[str], list[list[Any]], str | None]:
        if not self._connection:
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
        with self._connection.cursor() as cur:
            cur.execute("""
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
            """)
            for row in cur.fetchall():
                schema = "" if row[0] == "dbo" else row[0]
                cache.tables.append(TableInfo(name=row[1], schema=schema))

            cur.execute("""
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.VIEWS
                ORDER BY TABLE_SCHEMA, TABLE_NAME
            """)
            for row in cur.fetchall():
                schema = "" if row[0] == "dbo" else row[0]
                cache.views.append(TableInfo(name=row[1], schema=schema))

            cur.execute("""
                SELECT SPECIFIC_NAME, ROUTINE_TYPE, DATA_TYPE
                FROM INFORMATION_SCHEMA.ROUTINES
                WHERE ROUTINE_TYPE IN ('FUNCTION', 'PROCEDURE')
                ORDER BY SPECIFIC_NAME
            """)
            for row in cur.fetchall():
                cache.routines.append(RoutineInfo(
                    name=row[0],
                    routine_type=row[1],
                    return_type=row[2] or "",
                ))

            cur.execute("""
                SELECT name FROM sys.triggers
                WHERE parent_id > 0
                ORDER BY name
            """)
            cache.triggers = [row[0] for row in cur.fetchall()]

            cur.execute("""
                SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                       (SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                        JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                        ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                        WHERE kcu.TABLE_NAME = c.TABLE_NAME
                          AND kcu.COLUMN_NAME = c.COLUMN_NAME
                          AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY') as is_pk
                FROM INFORMATION_SCHEMA.COLUMNS c
                ORDER BY TABLE_NAME, ORDINAL_POSITION
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
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                       (SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                        JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                        ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                        WHERE kcu.TABLE_NAME = %s
                          AND kcu.COLUMN_NAME = c.COLUMN_NAME
                          AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY') as is_pk
                FROM INFORMATION_SCHEMA.COLUMNS c
                WHERE TABLE_NAME = %s AND TABLE_SCHEMA = %s
                ORDER BY ORDINAL_POSITION
            """, (table, table, schema))
        else:
            cur.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                       (SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                        JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                        ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                        WHERE kcu.TABLE_NAME = %s
                          AND kcu.COLUMN_NAME = c.COLUMN_NAME
                          AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY') as is_pk
                FROM INFORMATION_SCHEMA.COLUMNS c
                WHERE TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
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
        full_name = f"{schema}.{view}" if schema else view
        cur.execute("SELECT OBJECT_DEFINITION(OBJECT_ID(%s))", (full_name,))
        result = cur.fetchone()
        cur.close()
        return result[0] if result else ""

    def get_routine_source(self, routine: str, routine_type: str) -> str:
        cur = self._connection.cursor()
        cur.execute("""
            SELECT OBJECT_DEFINITION(OBJECT_ID(%s))
        """, (routine,))
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
                SELECT i.name, c.name, i.is_unique, i.is_primary_key
                FROM sys.indexes i
                JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                JOIN sys.tables t ON i.object_id = t.object_id
                JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE t.name = %s AND s.name = %s
                ORDER BY i.name, ic.key_ordinal
            """, (table, schema))
        else:
            cur.execute("""
                SELECT i.name, c.name, i.is_unique, i.is_primary_key
                FROM sys.indexes i
                JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                JOIN sys.tables t ON i.object_id = t.object_id
                JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE t.name = %s
                ORDER BY i.name, ic.key_ordinal
            """, (table,))
        indexes = {}
        for row in cur.fetchall():
            name = row[0]
            if name not in indexes:
                indexes[name] = {"name": name, "unique": row[2], "primary": row[3], "columns": []}
            indexes[name]["columns"].append(row[1])
        cur.close()
        return list(indexes.values())

    def get_table_ddl(self, table: str, schema: str = "") -> str:
        cur = self._connection.cursor()
        try:
            full_name = f"[{schema}].[{table}]" if schema else f"[{table}]"

            if schema:
                cur.execute("""
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                           NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE,
                           COLUMN_DEFAULT
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = %s AND TABLE_SCHEMA = %s
                    ORDER BY ORDINAL_POSITION
                """, (table, schema))
            else:
                cur.execute("""
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                           NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE,
                           COLUMN_DEFAULT
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                """, (table,))

            columns_data = cur.fetchall()

            if schema:
                cur.execute("""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                        ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                    WHERE kcu.TABLE_NAME = %s
                      AND kcu.TABLE_SCHEMA = %s
                      AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                    ORDER BY ORDINAL_POSITION
                """, (table, schema))
            else:
                cur.execute("""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                        ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                    WHERE kcu.TABLE_NAME = %s
                      AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                    ORDER BY ORDINAL_POSITION
                """, (table,))
            pk_cols = [row[0] for row in cur.fetchall()]

            def _fmt_type(dt, max_len, num_prec, num_scale):
                u = dt.upper()
                if u in ('VARCHAR', 'NVARCHAR', 'CHAR', 'NCHAR'):
                    if max_len == -1 or max_len is None:
                        return f"{dt}(MAX)"
                    return f"{dt}({max_len})"
                if u in ('DECIMAL', 'NUMERIC'):
                    if num_prec is not None:
                        if num_scale is not None:
                            return f"{dt}({num_prec}, {num_scale})"
                        return f"{dt}({num_prec})"
                return dt

            lines = []
            for col_name, dt, max_len, num_prec, num_scale, nullable, default in columns_data:
                col_type = _fmt_type(dt, max_len, num_prec, num_scale)
                col_def = f"    [{col_name}] {col_type}"
                if col_name in pk_cols and nullable is False:
                    col_def += " NOT NULL"
                elif not nullable:
                    col_def += " NOT NULL"
                if default:
                    col_def += f" DEFAULT {default}"
                lines.append(col_def)

            if pk_cols:
                pk_str = ", ".join(f"[{c}]" for c in pk_cols)
                lines.append(f"    PRIMARY KEY ({pk_str})")

            return f"CREATE TABLE {full_name} (\n" + ",\n".join(lines) + "\n)"
        finally:
            cur.close()

    def get_trigger_source(self, trigger: str) -> str:
        cur = self._connection.cursor()
        cur.execute("SELECT OBJECT_DEFINITION(OBJECT_ID(%s))", (trigger,))
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
