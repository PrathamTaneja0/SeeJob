"""SQLAlchemy engine and session factory."""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from seejob.core.config import get_settings

settings = get_settings()

connect_args: dict[str, object] = {}
if settings.is_sqlite:
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=not settings.is_sqlite,
    echo=settings.debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
    """Enable foreign keys for SQLite connections."""
    if settings.is_sqlite:
        cursor = dbapi_connection.cursor()  # type: ignore[union-attr]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and close it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
