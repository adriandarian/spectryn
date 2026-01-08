"""
State Store Adapters - Implementations of StateStorePort.

Available backends:
- SQLiteStateStore: Local SQLite database (recommended for most users)
- PostgresStateStore: PostgreSQL for multi-user/distributed deployments
- FileStateStore: JSON files (default, compatible with existing StateStore)
"""

from .file_store import FileStateStore
from .migration import (
    StateStoreMigrator,
    create_store,
    export_to_json,
    import_from_json,
)
from .sqlite_store import SQLiteStateStore


__all__ = [
    "FileStateStore",
    "SQLiteStateStore",
    "StateStoreMigrator",
    "create_store",
    "export_to_json",
    "import_from_json",
]

# PostgresStateStore is optional - only available if psycopg2 is installed
try:
    from .postgres_store import PostgresStateStore

    __all__.append("PostgresStateStore")
except ImportError:
    pass
