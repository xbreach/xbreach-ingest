import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import Headers

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
from app.services.sources import InactiveSourceError, SourceNotFoundError
from app.services.upload import (
    EmptyUploadFileError,
    InvalidUploadContentTypeError,
    InvalidUploadExtensionError,
    UnsafeUploadFilenameError,
    UploadFileTooLargeError,
    UploadIngestResult,
    UploadIngestService,
)

COLLECTED_AT = datetime(2026, 6, 6, tzinfo=UTC)


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


def upload_file(
    filename: str,
    content: bytes,
    content_type: str = "text/plain",
) -> UploadFile:
    from io import BytesIO

    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


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

    result = service(session, tmp_path).upload(
        file=upload_file(filename, b"email,password\n", content_type_for(filename)),
        source_id=2001,
        breach_name="sample breach",
        collected_at=COLLECTED_AT,
    )

    breach = session.get(BreachModel, 3001)
    job = session.get(IngestionJobModel, 4001)
    expected_relative_path = (
        Path("raw")
        / "year=2026"
        / "month=06"
        / "day=06"
        / "4001"
        / f"original{Path(filename).suffix}"
    )
    expected_absolute_path = tmp_path / expected_relative_path
    assert result == UploadIngestResult(
        job_id=4001,
        file_path=expected_relative_path.as_posix(),
    )
    assert breach is not None
    assert breach.name == "sample breach"
    assert job is not None
    assert job.source_id == 2001
    assert job.breach_id == 3001
    assert job.local_path == expected_relative_path.as_posix()
    assert job.file_size_bytes == len(b"email,password\n")
    assert expected_absolute_path.exists()
    assert expected_absolute_path.read_bytes() == b"email,password\n"

    manifest_path = expected_absolute_path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest == {
        "job_id": 4001,
        "checksum": hashlib.sha256(b"email,password\n").hexdigest(),
        "filename": filename,
        "size": len(b"email,password\n"),
    }


def test_upload_sanitizes_malicious_but_local_filename(
    session: Session,
    tmp_path: Path,
) -> None:
    add_source(session)

    result = service(session, tmp_path).upload(
        file=upload_file("bad name;$!.txt", b"content"),
        source_id=2001,
        breach_name="sample breach",
        collected_at=COLLECTED_AT,
    )

    job = session.get(IngestionJobModel, result.job_id)
    assert job is not None
    assert job.original_filename == "bad_name_.txt"
    assert job.local_path.endswith("/original.txt")


def test_upload_rejects_invalid_extension(session: Session, tmp_path: Path) -> None:
    add_source(session)

    with pytest.raises(InvalidUploadExtensionError):
        service(session, tmp_path).upload(
            file=upload_file("input.exe", b"content"),
            source_id=2001,
            breach_name="sample breach",
            collected_at=None,
        )


def test_upload_rejects_invalid_content_type(session: Session, tmp_path: Path) -> None:
    add_source(session)

    with pytest.raises(InvalidUploadContentTypeError):
        service(session, tmp_path).upload(
            file=upload_file("input.txt", b"content", "image/png"),
            source_id=2001,
            breach_name="sample breach",
            collected_at=None,
        )


def test_upload_rejects_path_traversal_filename(
    session: Session,
    tmp_path: Path,
) -> None:
    add_source(session)

    with pytest.raises(UnsafeUploadFilenameError):
        service(session, tmp_path).upload(
            file=upload_file("../input.txt", b"content"),
            source_id=2001,
            breach_name="sample breach",
            collected_at=None,
        )


def test_upload_rejects_empty_file(session: Session, tmp_path: Path) -> None:
    add_source(session)

    with pytest.raises(EmptyUploadFileError):
        service(session, tmp_path).upload(
            file=upload_file("input.txt", b""),
            source_id=2001,
            breach_name="sample breach",
            collected_at=None,
        )

    assert list(tmp_path.iterdir()) == []


def test_upload_rejects_file_larger_than_configured_limit(
    session: Session,
    tmp_path: Path,
) -> None:
    add_source(session)
    ids = iter([3001, 4001])
    upload_service = UploadIngestService(
        source_repository=SourceRepository(session),
        breach_repository=BreachRepository(session),
        job_repository=IngestionJobRepository(session),
        id_generator=lambda: next(ids),
        storage_path=tmp_path,
        max_file_size_bytes=3,
    )

    with pytest.raises(UploadFileTooLargeError):
        upload_service.upload(
            file=upload_file("input.txt", b"content"),
            source_id=2001,
            breach_name="sample breach",
            collected_at=None,
        )

    assert list(tmp_path.iterdir()) == []


def test_upload_rejects_unknown_source(session: Session, tmp_path: Path) -> None:
    add_source(session, source_id=2001)

    with pytest.raises(SourceNotFoundError) as exc_info:
        service(session, tmp_path).upload(
            file=upload_file("input.txt", b"content"),
            source_id=9999,
            breach_name="sample breach",
            collected_at=None,
        )

    assert exc_info.value.status_code == 404


def test_upload_rejects_inactive_source(session: Session, tmp_path: Path) -> None:
    add_source(session, status=SOURCE_STATUS_INACTIVE)

    with pytest.raises(InactiveSourceError):
        service(session, tmp_path).upload(
            file=upload_file("input.txt", b"content"),
            source_id=2001,
            breach_name="sample breach",
            collected_at=None,
        )

    assert session.query(IngestionJobModel).count() == 0


def test_upload_duplicate_checksum_returns_existing_job_without_creating_new_job(
    session: Session,
    tmp_path: Path,
) -> None:
    add_source(session)
    first_result = service(session, tmp_path).upload(
        file=upload_file("first.txt", b"same content"),
        source_id=2001,
        breach_name="first breach",
        collected_at=COLLECTED_AT,
    )

    second_result = service(session, tmp_path).upload(
        file=upload_file("second.txt", b"same content"),
        source_id=2001,
        breach_name="second breach",
        collected_at=COLLECTED_AT,
    )

    assert second_result == first_result
    assert session.query(IngestionJobModel).count() == 1
    assert session.query(BreachModel).count() == 1
    assert len(list(tmp_path.iterdir())) == 1


def content_type_for(filename: str) -> str:
    if filename.endswith(".csv"):
        return "text/csv"
    if filename.endswith(".gz"):
        return "application/gzip"
    if filename.endswith(".zst"):
        return "application/zstd"
    return "text/plain"
