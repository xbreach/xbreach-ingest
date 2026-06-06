from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.sql import func

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


class IngestionJobModel(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    breach_id: Mapped[int | None] = mapped_column(BigInteger)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    stored_filename: Mapped[str] = mapped_column(Text, nullable=False)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    total_lines: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    parsed_lines: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rejected_lines: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    inserted_lines: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


def build_database_url() -> str:
    settings = get_settings()
    return (
        "postgresql+psycopg://"
        f"{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}"
        f"/{settings.postgres_db}"
    )


engine = create_engine(build_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Session:
    return SessionLocal()
