"""SQLite database session and schema lifecycle management."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from strata.storage.models import Base


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    """Enable WAL mode and foreign keys for SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


class DatabaseManager:
    """Manages SQLite engine lifecycle and session creation."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            echo=False,
            future=True,
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.init_schema()

    def init_schema(self) -> None:
        """Create database tables if they do not exist."""
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        """Return a new database session."""
        return self.session_factory()
