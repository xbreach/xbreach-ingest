import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.source import SOURCE_STATUS_ACTIVE, SOURCE_STATUS_INACTIVE
from app.infrastructure.database import (
    Base,
    BreachModel,
    IngestionJobModel,
    SourceModel,
)
from app.repositories.breaches import BreachRepository
from app.repositories.ingestion_jobs import IngestionJobRepository
from app.repositories.sources import SourceRepository
from app.services.sources import InactiveSourceError, InvalidApiKeyError
from app.services.upload import EmptyUploadFileError, InvalidUploadExtensionError
from app.services.upload import SourceMismatchError, UploadIngestService


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        yield session


def add_source(
    session: Session,
    *,
    source_id: int = 2001,
    api_key: str = "secret",
    status: str = SOURCE_STATUS_ACTIVE,
) -> None:
    session.add(
        SourceModel(
            id=source_id,
            name="example",
            type="api",
            status=status,
            api_key_hash=hashlib.sha256(api_key.encode("utf-8")).hexdigest(),
        )
    )
    session.commit()


def upload_file(filename: str, content: bytes) -> UploadFile:
    from io import BytesIO

    return UploadFile(filename=filename, file=BytesIO(content))


def service(session: Session, tmp_path: Path) -> UploadIngestService:
    ids = iter([3001, 4001])
    return UploadIngestService(
        source_repository=SourceRepository(session),
        breach_repository=BreachRepository(session),
        job_repository=IngestionJobRepository(session),
        id_generator=lambda: next(ids),
        storage_path=tmp_path,
    )


@pytest.mark.parametrize("filename", ["input.txt", "input.csv", "input.gz", "input.zst"])
def test_upload_creates_breach_job_and_saves_file(
    session: Session,
    tmp_path: Path,
    filename: str,
) -> None:
    add_source(session)

    job_id = service(session, tmp_path).upload(
        file=upload_file(filename, b"email,password\n"),
        source_id=2001,
        breach_name="sample breach",
        collected_at=None,
        api_key="secret",
    )

    breach = session.get(BreachModel, 3001)
    job = session.get(IngestionJobModel, 4001)
    assert job_id == 4001
    assert breach is not None
    assert breach.name == "sample breach"
    assert job is not None
    assert job.source_id == 2001
    assert job.breach_id == 3001
    assert job.file_size_bytes == len(b"email,password\n")
    assert Path(job.local_path).exists()
    assert Path(job.local_path).read_bytes() == b"email,password\n"


def test_upload_rejects_invalid_extension(session: Session, tmp_path: Path) -> None:
    add_source(session)

    with pytest.raises(InvalidUploadExtensionError):
        service(session, tmp_path).upload(
            file=upload_file("input.exe", b"content"),
            source_id=2001,
            breach_name="sample breach",
            collected_at=None,
            api_key="secret",
        )


def test_upload_rejects_empty_file(session: Session, tmp_path: Path) -> None:
    add_source(session)

    with pytest.raises(EmptyUploadFileError):
        service(session, tmp_path).upload(
            file=upload_file("input.txt", b""),
            source_id=2001,
            breach_name="sample breach",
            collected_at=None,
            api_key="secret",
        )

    assert list(tmp_path.iterdir()) == []


def test_upload_rejects_invalid_api_key(session: Session, tmp_path: Path) -> None:
    add_source(session)

    with pytest.raises(InvalidApiKeyError):
        service(session, tmp_path).upload(
            file=upload_file("input.txt", b"content"),
            source_id=2001,
            breach_name="sample breach",
            collected_at=None,
            api_key="wrong",
        )


def test_upload_rejects_source_id_mismatch(session: Session, tmp_path: Path) -> None:
    add_source(session, source_id=2001)

    with pytest.raises(SourceMismatchError) as exc_info:
        service(session, tmp_path).upload(
            file=upload_file("input.txt", b"content"),
            source_id=9999,
            breach_name="sample breach",
            collected_at=None,
            api_key="secret",
        )

    assert exc_info.value.status_code == 401


def test_upload_rejects_inactive_source(session: Session, tmp_path: Path) -> None:
    add_source(session, status=SOURCE_STATUS_INACTIVE)

    with pytest.raises(InactiveSourceError):
        service(session, tmp_path).upload(
            file=upload_file("input.txt", b"content"),
            source_id=2001,
            breach_name="sample breach",
            collected_at=None,
            api_key="secret",
        )

    assert session.query(IngestionJobModel).count() == 0
