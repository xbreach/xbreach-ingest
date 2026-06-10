from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, sessionmaker

from app.domain.ingestion_job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
)
from app.infrastructure.database import Base, IngestionJobModel
from app.repositories.ingestion_jobs import IngestionJobRepository
from app.schemas.ingestion_job import CreateIngestionJob, IngestionJobProgress


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        yield session


def create_job_dto(job_id: int = 1001) -> CreateIngestionJob:
    return CreateIngestionJob(
        id=job_id,
        source_id=2001,
        breach_id=None,
        original_filename="input.txt",
        stored_filename="stored.txt",
        local_path="/data/xbreach/storage/stored.txt",
        checksum_sha256="a" * 64,
        file_size_bytes=128,
    )


def add_job(session: Session, job_id: int, status: str = JOB_STATUS_PENDING) -> None:
    session.add(
        IngestionJobModel(
            id=job_id,
            source_id=2001,
            breach_id=None,
            original_filename=f"input-{job_id}.txt",
            stored_filename=f"stored-{job_id}.txt",
            local_path=f"/data/xbreach/storage/stored-{job_id}.txt",
            checksum_sha256=str(job_id).zfill(64),
            file_size_bytes=128,
            status=status,
        )
    )
    session.commit()


def test_create_job_persists_pending_job(session: Session) -> None:
    repository = IngestionJobRepository(session)

    job = repository.create_job(create_job_dto())

    persisted = session.get(IngestionJobModel, 1001)
    assert persisted is not None
    assert persisted.status == JOB_STATUS_PENDING
    assert job.id == 1001
    assert job.status == JOB_STATUS_PENDING


def test_find_by_id_returns_job(session: Session) -> None:
    add_job(session, 1001)
    repository = IngestionJobRepository(session)

    job = repository.find_by_id(1001)

    assert job is not None
    assert job.id == 1001


def test_find_by_checksum_sha256_returns_first_matching_job(session: Session) -> None:
    add_job(session, 1001)
    repository = IngestionJobRepository(session)

    job = repository.find_by_checksum_sha256(str(1001).zfill(64))

    assert job is not None
    assert job.id == 1001


def test_find_pending_jobs_returns_oldest_pending_jobs(session: Session) -> None:
    add_job(session, 1001, JOB_STATUS_COMPLETED)
    add_job(session, 1002, JOB_STATUS_PENDING)
    add_job(session, 1003, JOB_STATUS_PENDING)
    repository = IngestionJobRepository(session)

    jobs = repository.find_pending_jobs(limit=1)

    assert [job.id for job in jobs] == [1002]


def test_find_pending_jobs_supports_for_update_skip_locked(session: Session) -> None:
    repository = IngestionJobRepository(session)

    statement = repository.pending_jobs_statement(
        limit=10,
        for_update_skip_locked=True,
    )
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE SKIP LOCKED" in compiled


def test_mark_as_processing_updates_pending_job(session: Session) -> None:
    add_job(session, 1001)
    repository = IngestionJobRepository(session)

    job = repository.mark_as_processing(1001)

    persisted = session.get(IngestionJobModel, 1001)
    assert persisted is not None
    assert persisted.status == JOB_STATUS_RUNNING
    assert persisted.started_at is not None
    assert job is not None
    assert job.status == JOB_STATUS_RUNNING


def test_mark_as_processing_ignores_non_pending_job(session: Session) -> None:
    add_job(session, 1001, JOB_STATUS_COMPLETED)
    repository = IngestionJobRepository(session)

    job = repository.mark_as_processing(1001)

    persisted = session.get(IngestionJobModel, 1001)
    assert persisted is not None
    assert persisted.status == JOB_STATUS_COMPLETED
    assert job is None


def test_mark_as_completed_updates_job(session: Session) -> None:
    add_job(session, 1001, JOB_STATUS_RUNNING)
    repository = IngestionJobRepository(session)

    job = repository.mark_as_completed(1001)

    persisted = session.get(IngestionJobModel, 1001)
    assert persisted is not None
    assert persisted.status == JOB_STATUS_COMPLETED
    assert persisted.finished_at is not None
    assert job is not None
    assert job.error_message is None


def test_mark_as_failed_stores_error_message(session: Session) -> None:
    add_job(session, 1001, JOB_STATUS_RUNNING)
    repository = IngestionJobRepository(session)

    job = repository.mark_as_failed(1001, "boom")

    persisted = session.get(IngestionJobModel, 1001)
    assert persisted is not None
    assert persisted.status == JOB_STATUS_FAILED
    assert persisted.error_message == "boom"
    assert persisted.finished_at is not None
    assert job is not None
    assert job.error_message == "boom"


def test_update_progress_updates_line_counts(session: Session) -> None:
    add_job(session, 1001, JOB_STATUS_RUNNING)
    repository = IngestionJobRepository(session)

    job = repository.update_progress(
        1001,
        IngestionJobProgress(
            total_lines=10,
            parsed_lines=8,
            rejected_lines=1,
            inserted_lines=7,
        ),
    )

    persisted = session.get(IngestionJobModel, 1001)
    assert persisted is not None
    assert persisted.total_lines == 10
    assert persisted.parsed_lines == 8
    assert persisted.rejected_lines == 1
    assert persisted.inserted_lines == 7
    assert job is not None
    assert job.inserted_lines == 7
