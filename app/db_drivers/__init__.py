from .postgres import PostgreSQLDriver
from .mysql import MySQLDriver
from .sqlite import SQLiteDriver
from .sqlserver import SQLServerDriver

DRIVERS = {
    "postgresql": PostgreSQLDriver,
    "mysql": MySQLDriver,
    "sqlite": SQLiteDriver,
    "sqlserver": SQLServerDriver,
}
