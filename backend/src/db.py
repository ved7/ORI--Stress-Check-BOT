import os
import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ori.sqlite3"
DATABASE_AVAILABLE = True


def resolve_database_path() -> Path:
    configured_path = os.getenv("ORI_DB_PATH", "").strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_DB_PATH


def database_available() -> bool:
    return DATABASE_AVAILABLE


def disable_database(error: Exception | str) -> None:
    global DATABASE_AVAILABLE
    if not DATABASE_AVAILABLE:
        return
    DATABASE_AVAILABLE = False
    logger.error("SQLite is unavailable; falling back to in-memory session storage. %s", error)


@contextmanager
def get_connection():
    if not DATABASE_AVAILABLE:
        raise RuntimeError("database unavailable")
    database_path = resolve_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database() -> None:
    try:
        with get_connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS session_records (
                    session_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    report_json TEXT
                );

                CREATE INDEX IF NOT EXISTS session_records_client_updated_idx
                ON session_records (client_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS session_messages (
                    session_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, position),
                    FOREIGN KEY (session_id) REFERENCES session_records(session_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS session_messages_session_role_idx
                ON session_messages (session_id, role, position);
                """
            )
    except Exception as error:
        disable_database(error)
