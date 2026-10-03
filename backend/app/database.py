from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


if settings.database_url.startswith("sqlite:///"):
    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    database_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 30}
    if settings.database_url.startswith("sqlite")
    else {},
)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# create_all 只会建新表，不会给已有的表补列。开发期的 SQLite 加个轻量迁移，
# 免得每次加字段都要手删数据库（那条已下载的视频就白下了）。
_SQLITE_COLUMNS: dict[str, dict[str, str]] = {
    "tutorial_steps": {
        "breakdown_id": "VARCHAR(36)",
        "text_basis": "VARCHAR(16) NOT NULL DEFAULT 'none'",
        "frame_key": "TEXT",
        "en_title": "TEXT",
        "en_summary": "TEXT",
        "en_question": "TEXT",
        "en_criteria": "TEXT",
        "en_hint": "TEXT",
    },
    "videos": {
        "saved_at": "TIMESTAMP",
        "library_category": "VARCHAR(16)",
        "library_category_basis": "VARCHAR(16)",
    },
    "tutorial_breakdowns": {
        "lang": "VARCHAR(8) NOT NULL DEFAULT 'zh'",
    },
}


def _add_missing_columns(connection) -> None:
    for table, columns in _SQLITE_COLUMNS.items():
        existing = {
            row[1] for row in connection.execute(text(f"PRAGMA table_info({table})"))
        }
        if not existing:
            continue  # 表刚建出来，列本来就是齐的
        for name, ddl in columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def create_tables() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as connection:
            _add_missing_columns(connection)
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_video_platform_source_id "
                "ON videos (source_platform, source_video_id) "
                "WHERE source_video_id IS NOT NULL"
            ))


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
