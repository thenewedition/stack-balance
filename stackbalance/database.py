from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(
            f"sqlite:///{config.db_path()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine():
    """Dispose the current engine so the next call rebuilds it (used by tests/restore)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


# Columns added after the 0.1 schema; applied to existing databases on startup
# (SQLite create_all never alters existing tables).
_MIGRATIONS: list[tuple[str, str, str]] = [
    ("accounts", "payment_category_id",
     "ALTER TABLE accounts ADD COLUMN payment_category_id INTEGER REFERENCES categories(id)"),
    ("transactions", "transfer_peer_id",
     "ALTER TABLE transactions ADD COLUMN transfer_peer_id INTEGER REFERENCES transactions(id)"),
]


def _migrate(engine):
    with engine.connect() as conn:
        for table, column, ddl in _MIGRATIONS:
            columns = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if columns and column not in columns:
                conn.exec_driver_sql(ddl)
        conn.commit()


def init_db():
    from . import models  # noqa: F401  (register tables)

    engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate(engine)


def get_session():
    get_engine()
    session: Session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
