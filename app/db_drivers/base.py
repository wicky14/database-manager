from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectionConfig:
    name: str
    type: str
    host: str = ""
    port: int = 0
    user: str = ""
    password: str = ""
    database: str = ""
    file_path: str = ""
    charset: str = ""


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    default: Any = None
    is_pk: bool = False


@dataclass
class TableInfo:
    name: str
    schema: str = ""


@dataclass
class RoutineInfo:
    name: str
    routine_type: str  # FUNCTION or PROCEDURE
    return_type: str = ""


@dataclass
class SchemaCache:
    tables: list[TableInfo] = field(default_factory=list)
    views: list[TableInfo] = field(default_factory=list)
    routines: list[RoutineInfo] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    columns: dict[str, list[ColumnInfo]] = field(default_factory=dict)


class BaseDriver(ABC):
    def __init__(self, config: ConnectionConfig):
        self.config = config
        self._connection = None
        self._cache: SchemaCache | None = None
        self._in_transaction = False

    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @abstractmethod
    def execute_query(self, sql: str) -> tuple[list[str], list[list[Any]], str | None]:
        ...

    @abstractmethod
    def get_schema_cache(self) -> SchemaCache:
        ...

    @abstractmethod
    def get_table_columns(self, table: str, schema: str = "") -> list[ColumnInfo]:
        ...

    @abstractmethod
    def get_view_source(self, view: str, schema: str = "") -> str:
        ...

    @abstractmethod
    def get_routine_source(self, routine: str, routine_type: str) -> str:
        ...

    @abstractmethod
    def save_routine(self, routine: str, routine_type: str, source: str) -> None:
        ...

    @abstractmethod
    def get_trigger_source(self, trigger: str) -> str:
        ...

    @abstractmethod
    def save_trigger(self, trigger: str, source: str) -> None:
        ...

    @abstractmethod
    def get_indexes(self, table: str, schema: str = "") -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def ping(self) -> bool:
        ...

    def begin(self) -> None:
        self._in_transaction = True

    def commit(self) -> None:
        if self._connection:
            self._connection.commit()
        self._in_transaction = False

    def rollback(self) -> None:
        if self._connection:
            self._connection.rollback()
        self._in_transaction = False

    def cancel_query(self) -> None:
        pass

    @property
    def display_name(self) -> str:
        return f"{self.config.type}:{self.config.database}@{self.config.host}"

    def get_icon_key(self) -> str:
        return self.config.type
