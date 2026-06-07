import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import (
    Base,
    BreachModel,
    IngestionJobErrorModel,
    IngestionJobModel,
    SourceModel,
    get_session_dependency,
)
from app.main import app
from app.services.upload import InvalidUploadExtensionError, UploadIngestResult


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        yield session


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session_dependency] = lambda: session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def seed_operational_data(session: Session) -> None:
    session.add(
        SourceModel(
            id=2001,
            name="Partner feed",
            type="api",
            status="active",
            api_key_hash="sensitive-api-key-hash",
        )
    )
    session.add(
        IngestionJobModel(
            id=4001,
            source_id=2001,
            breach_id=3001,
            original_filename="original.txt",
            stored_filename="original.txt",
            local_path="/data/xbreach/raw/year=2026/month=06/day=06/4001/original.txt",
            checksum_sha256=hashlib.sha256(b"content").hexdigest(),
            file_size_bytes=7,
            status="pending",
            total_lines=10,
            parsed_lines=3,
            rejected_lines=1,
            inserted_lines=2,
        )
    )
    session.commit()


def add_source(
    session: Session,
    *,
    source_id: int,
    name: str,
    status: str = "active",
) -> None:
    session.add(
        SourceModel(
            id=source_id,
            name=name,
            type="api",
            status=status,
            api_key_hash=f"{source_id}-api-key-hash",
        )
    )


def add_job(
    session: Session,
    *,
    job_id: int,
    source_id: int,
    filename: str,
    status: str,
    created_at: datetime,
    file_size_bytes: int = 100,
    parsed_lines: int = 10,
    rejected_lines: int = 1,
    inserted_lines: int = 9,
) -> None:
    session.add(
        IngestionJobModel(
            id=job_id,
            source_id=source_id,
            breach_id=job_id - 1000,
            original_filename=filename,
            stored_filename="original.txt",
            local_path=f"raw/year=2026/month=06/day=07/{job_id}/original.txt",
            checksum_sha256=hashlib.sha256(str(job_id).encode("utf-8")).hexdigest(),
            file_size_bytes=file_size_bytes,
            status=status,
            total_lines=parsed_lines + rejected_lines,
            parsed_lines=parsed_lines,
            rejected_lines=rejected_lines,
            inserted_lines=inserted_lines,
            created_at=created_at,
            updated_at=created_at + timedelta(minutes=5),
        )
    )


def seed_job_listing_data(session: Session) -> None:
    add_source(session, source_id=2001, name="Partner feed")
    add_source(session, source_id=2002, name="Internal import")
    add_job(
        session,
        job_id=4001,
        source_id=2001,
        filename="alpha.txt",
        status="pending",
        created_at=datetime(2026, 6, 5, 10, 0, tzinfo=UTC),
        file_size_bytes=512,
        parsed_lines=3,
        rejected_lines=1,
        inserted_lines=2,
    )
    add_job(
        session,
        job_id=4002,
        source_id=2002,
        filename="beta.csv",
        status="completed",
        created_at=datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
        file_size_bytes=2048,
        parsed_lines=20,
        rejected_lines=0,
        inserted_lines=20,
    )
    add_job(
        session,
        job_id=4003,
        source_id=2001,
        filename="gamma.txt",
        status="failed",
        created_at=datetime(2026, 6, 6, 10, 0, tzinfo=UTC),
        file_size_bytes=1024,
        parsed_lines=12,
        rejected_lines=4,
        inserted_lines=8,
    )
    session.commit()


def seed_job_detail_data(session: Session) -> None:
    add_source(session, source_id=2001, name="Partner feed")
    session.add(
        BreachModel(
            id=3001,
            source_id=2001,
            name="Credential dump",
            collected_at=datetime(2026, 6, 6, 8, 0, tzinfo=UTC),
        )
    )
    session.add(
        IngestionJobModel(
            id=4001,
            source_id=2001,
            breach_id=3001,
            original_filename="accounts.csv",
            stored_filename="original.csv",
            local_path="raw/year=2026/month=06/day=06/4001/original.csv",
            checksum_sha256=hashlib.sha256(b"content").hexdigest(),
            file_size_bytes=2048,
            status="running",
            total_lines=100,
            parsed_lines=60,
            rejected_lines=10,
            inserted_lines=55,
            started_at=datetime(2026, 6, 7, 12, 0, tzinfo=UTC),
            created_at=datetime(2026, 6, 7, 11, 0, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, 12, 5, tzinfo=UTC),
        )
    )
    session.add_all(
        [
            IngestionJobErrorModel(
                id=7001,
                job_id=4001,
                line_number=10,
                error_type="invalid_email",
                error_message="raw leak line user@example.com:secret-password",
                created_at=datetime(2026, 6, 7, 12, 1, tzinfo=UTC),
            ),
            IngestionJobErrorModel(
                id=7002,
                job_id=4001,
                line_number=11,
                error_type="invalid_email",
                error_message="raw leak line admin@example.com:password123",
                created_at=datetime(2026, 6, 7, 12, 2, tzinfo=UTC),
            ),
            IngestionJobErrorModel(
                id=7003,
                job_id=4001,
                line_number=None,
                error_type="parse_error",
                error_message="raw file chunk should not appear",
                created_at=datetime(2026, 6, 7, 12, 3, tzinfo=UTC),
            ),
        ]
    )
    session.commit()


@pytest.mark.parametrize(
    "path, expected_text",
    [
        ("/login", "Login"),
        ("/dashboard", "Total jobs"),
        ("/jobs", "original.txt"),
        ("/jobs/4001", "Job details"),
        ("/upload", "Breach name"),
        ("/sources", "Partner feed"),
    ],
)
def test_web_pages_render_basic_layout(
    client: TestClient,
    session: Session,
    path: str,
    expected_text: str,
) -> None:
    seed_operational_data(session)

    response = client.get(path)

    assert response.status_code == 200
    assert expected_text in response.text
    assert "/dashboard" in response.text
    assert "/jobs" in response.text
    assert "/upload" in response.text
    assert "/sources" in response.text


def test_root_redirects_to_dashboard(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


def test_web_interface_does_not_expose_sensitive_data(
    client: TestClient,
    session: Session,
) -> None:
    seed_operational_data(session)

    dashboard = client.get("/dashboard").text
    sources = client.get("/sources").text
    rendered_html = "\n".join([dashboard, sources])
    assert "sensitive-api-key-hash" not in rendered_html


def test_sources_screen_lists_sources_without_api_key_hash(
    client: TestClient,
    session: Session,
) -> None:
    seed_operational_data(session)

    response = client.get("/sources")

    assert response.status_code == 200
    assert "Partner feed" in response.text
    assert "active" in response.text
    assert "Created at" in response.text
    assert "sensitive-api-key-hash" not in response.text


def test_sources_screen_creates_source_and_shows_api_key_once(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.web.routes.secrets.token_urlsafe",
        lambda size: "plain-api-key",
    )

    response = client.post(
        "/sources",
        data={"name": "New feed", "type": "api", "status": "active"},
    )

    source = session.scalar(select(SourceModel).where(SourceModel.name == "New feed"))
    assert response.status_code == 200
    assert "source created" in response.text
    assert "plain-api-key" in response.text
    assert source is not None
    assert source.api_key_hash == hashlib.sha256(b"plain-api-key").hexdigest()
    assert source.api_key_hash != "plain-api-key"

    follow_up = client.get("/sources")
    assert "New feed" in follow_up.text
    assert "plain-api-key" not in follow_up.text
    assert source.api_key_hash not in follow_up.text


def test_sources_screen_toggles_source_status(
    client: TestClient,
    session: Session,
) -> None:
    seed_operational_data(session)

    deactivate = client.post("/sources/2001/toggle")
    session.expire_all()
    source = session.get(SourceModel, 2001)
    assert deactivate.status_code == 200
    assert source is not None
    assert source.status == "inactive"

    activate = client.post("/sources/2001/toggle")
    session.expire_all()
    source = session.get(SourceModel, 2001)
    assert activate.status_code == 200
    assert source is not None
    assert source.status == "active"


def test_upload_screen_renders_source_select_and_file_input(
    client: TestClient,
    session: Session,
) -> None:
    seed_operational_data(session)

    response = client.get("/upload")

    assert response.status_code == 200
    assert 'action="/upload"' in response.text
    assert 'method="post"' in response.text
    assert 'enctype="multipart/form-data"' in response.text
    assert 'select name="source_id"' in response.text
    assert 'input type="file" name="file"' in response.text
    assert "Partner feed" in response.text


def test_upload_screen_submits_multipart_and_shows_job_id(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_operational_data(session)
    calls = []

    def fake_upload(self, **kwargs) -> UploadIngestResult:
        calls.append(kwargs)
        return UploadIngestResult(
            job_id=9001,
            file_path="raw/year=2026/month=06/day=07/9001/original.txt",
        )

    monkeypatch.setattr("app.services.upload.UploadIngestService.upload", fake_upload)

    response = client.post(
        "/upload",
        data={
            "source_id": "2001",
            "breach_name": "sample breach",
            "collected_at": "2026-06-07T12:30",
            "api_key": "secret",
        },
        files={"file": ("input.txt", b"content", "text/plain")},
    )

    assert response.status_code == 200
    assert "Upload created job 9001." in response.text
    assert calls[0]["source_id"] == 2001
    assert calls[0]["breach_name"] == "sample breach"
    assert calls[0]["api_key"] == "secret"
    assert calls[0]["file"].filename == "input.txt"


def test_upload_screen_shows_validation_error(
    client: TestClient,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_operational_data(session)

    def fake_upload(self, **kwargs) -> UploadIngestResult:
        raise InvalidUploadExtensionError()

    monkeypatch.setattr("app.services.upload.UploadIngestService.upload", fake_upload)

    response = client.post(
        "/upload",
        data={
            "source_id": "2001",
            "breach_name": "sample breach",
            "api_key": "secret",
        },
        files={"file": ("input.exe", b"content", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "file extension is not allowed" in response.text
    assert "sample breach" in response.text


def test_jobs_screen_lists_expected_columns_and_recent_jobs_first(
    client: TestClient,
    session: Session,
) -> None:
    seed_job_listing_data(session)

    response = client.get("/jobs")

    assert response.status_code == 200
    for heading in [
        "Job ID",
        "Source",
        "Filename",
        "Status",
        "File size",
        "Parsed",
        "Rejected",
        "Inserted",
        "Created",
        "Updated",
    ]:
        assert heading in response.text
    assert response.text.index("4002") < response.text.index("4003")
    assert response.text.index("4003") < response.text.index("4001")
    assert "Internal import" in response.text
    assert "2048 bytes" in response.text
    assert "status-completed" in response.text
    assert "status-failed" in response.text


def test_jobs_screen_filters_by_status_source_date_range_and_filename(
    client: TestClient,
    session: Session,
) -> None:
    seed_job_listing_data(session)

    response = client.get(
        "/jobs",
        params={
            "status": "failed",
            "source_id": "2001",
            "date_from": "2026-06-06",
            "date_to": "2026-06-06",
            "filename": "gamma",
        },
    )

    assert response.status_code == 200
    assert "4003" in response.text
    assert "gamma.txt" in response.text
    assert "4001" not in response.text
    assert "4002" not in response.text


def test_jobs_screen_is_paginated(client: TestClient, session: Session) -> None:
    add_source(session, source_id=2001, name="Partner feed")
    base_time = datetime(2026, 6, 7, 12, 0, tzinfo=UTC)
    for index in range(25):
        add_job(
            session,
            job_id=5000 + index,
            source_id=2001,
            filename=f"batch-{index}.txt",
            status="pending",
            created_at=base_time - timedelta(minutes=index),
        )
    session.commit()

    first_page = client.get("/jobs")
    second_page = client.get("/jobs", params={"page": "2"})

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert "Page 1 of 2" in first_page.text
    assert "Page 2 of 2" in second_page.text
    assert "batch-0.txt" in first_page.text
    assert "batch-20.txt" not in first_page.text
    assert "batch-20.txt" in second_page.text


def test_job_details_screen_shows_progress_metadata_and_errors(
    client: TestClient,
    session: Session,
) -> None:
    seed_job_detail_data(session)

    response = client.get("/jobs/4001")

    assert response.status_code == 200
    assert "70% processed" in response.text
    assert "70 / 100 lines" in response.text
    assert "accounts.csv" in response.text
    assert hashlib.sha256(b"content").hexdigest() in response.text
    assert "raw/year=2026/month=06/day=06/4001/original.csv" in response.text
    assert "Partner feed" in response.text
    assert "Credential dump" in response.text
    assert "Total lines" in response.text
    assert "Parsed lines" in response.text
    assert "Rejected lines" in response.text
    assert "Inserted lines" in response.text
    assert "invalid_email" in response.text
    assert "parse_error" in response.text
    assert "Latest failures" in response.text
    assert "raw leak line" not in response.text
    assert "secret-password" not in response.text
    assert "password123" not in response.text


def test_job_details_screen_shows_not_found(client: TestClient) -> None:
    response = client.get("/jobs/9999")

    assert response.status_code == 404
    assert "Job not found." in response.text
