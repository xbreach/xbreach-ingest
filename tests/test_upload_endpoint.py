from fastapi.testclient import TestClient

from app.api.upload import get_upload_service
from app.main import app
from app.services.upload import InvalidUploadExtensionError, UploadIngestResult


class FakeUploadService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []

    def upload(self, **kwargs) -> UploadIngestResult:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return UploadIngestResult(
            job_id=12345,
            file_path="raw/year=2026/month=01/day=01/12345/original.txt",
        )


def test_upload_endpoint_requires_authentication() -> None:
    app.dependency_overrides[get_upload_service] = lambda: FakeUploadService()
    client = TestClient(app)

    response = client.post(
        "/api/v1/ingest/upload",
        data={"source_id": "2001", "breach_name": "sample breach"},
        files={"file": ("input.txt", b"content", "text/plain")},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 401


def test_auth_login_returns_bearer_token() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@xbreach.local", "password": "xbreach"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0
    assert "xbreach_ingest_token=" in response.headers["set-cookie"]


def test_upload_endpoint_accepts_bearer_token() -> None:
    fake_service = FakeUploadService()
    app.dependency_overrides[get_upload_service] = lambda: fake_service
    client = TestClient(app)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@xbreach.local", "password": "xbreach"},
    )
    token = login.json()["access_token"]

    response = client.post(
        "/api/v1/ingest/upload",
        headers={"authorization": f"Bearer {token}"},
        data={
            "source_id": "2001",
            "breach_name": "sample breach",
            "collected_at": "2026-01-01T00:00:00Z",
        },
        files={"file": ("input.txt", b"content", "text/plain")},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {
        "job_id": 12345,
        "file_path": "raw/year=2026/month=01/day=01/12345/original.txt",
    }
    assert fake_service.calls[0]["source_id"] == 2001
    assert "api_key" not in fake_service.calls[0]


def test_upload_endpoint_accepts_web_login_cookie() -> None:
    fake_service = FakeUploadService()
    app.dependency_overrides[get_upload_service] = lambda: fake_service
    client = TestClient(app)
    login = client.post(
        "/login",
        data={"email": "admin@xbreach.local", "password": "xbreach"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    response = client.post(
        "/api/v1/ingest/upload",
        data={"source_id": "2001", "breach_name": "sample breach"},
        files={"file": ("input.txt", b"content", "text/plain")},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert fake_service.calls[0]["source_id"] == 2001


def test_upload_endpoint_maps_invalid_extension_to_400() -> None:
    app.dependency_overrides[get_upload_service] = lambda: FakeUploadService(
        error=InvalidUploadExtensionError()
    )
    client = TestClient(app)
    login = client.post(
        "/login",
        data={"email": "admin@xbreach.local", "password": "xbreach"},
        follow_redirects=False,
    )
    assert login.status_code == 303

    response = client.post(
        "/api/v1/ingest/upload",
        data={"source_id": "2001", "breach_name": "sample breach"},
        files={"file": ("input.exe", b"content", "application/octet-stream")},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 400
