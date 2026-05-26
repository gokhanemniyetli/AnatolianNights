"""
Database engine and session factory.
All modules should import `get_session` and use it as a context manager.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import settings
from src.storage.models import Base


def _make_engine():
    db_url = settings.storage.database_url
    # Ensure the data directory exists for SQLite
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
        echo=False,
    )

    # Enable WAL mode for SQLite — better concurrent read performance
    if "sqlite" in db_url:
        @event.listens_for(engine, "connect")
        def set_wal(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all tables. Safe to call multiple times."""
    Base.metadata.create_all(bind=engine)
    _migrate_columns()


def _migrate_columns() -> None:
    """Add new columns to existing tables without losing data (SQLite-safe)."""
    from sqlalchemy import text
    new_columns = [
        ("songs", "suno_task_id", "TEXT"),
        ("songs", "concept_playlist_id", "INTEGER"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in new_columns:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()
            except Exception:
                pass  # Column already exists


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a database session, commit on success, rollback on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
