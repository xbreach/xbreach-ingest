import hashlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import (
    Base,
    IngestionJobModel,
    SourceModel,
    get_session_dependency,
)
from app.main import app


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
    job_detail = client.get("/jobs/4001").text

    rendered_html = "\n".join([dashboard, sources, job_detail])
    assert "sensitive-api-key-hash" not in rendered_html
    assert hashlib.sha256(b"content").hexdigest() not in rendered_html
    assert "/data/xbreach" not in rendered_html
