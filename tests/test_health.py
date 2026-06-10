from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_healthcheck_returns_ok(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("XBREACH_ENVIRONMENT", "test")
    monkeypatch.setattr("app.api.health.check_postgres", lambda: True)
    monkeypatch.setattr("app.api.health.check_redis", lambda: True)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "test",
        "service": "xbreach-ingest",
        "postgres": "ok",
        "redis": "ok",
    }
    get_settings.cache_clear()


def test_healthcheck_returns_error_when_dependency_fails(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setattr("app.api.health.check_postgres", lambda: True)
    monkeypatch.setattr("app.api.health.check_redis", lambda: False)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["postgres"] == "ok"
    assert response.json()["redis"] == "error"
    get_settings.cache_clear()


def test_settings_load_from_environment(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("XBREACH_ENVIRONMENT", "test")

    settings = get_settings()

    assert settings.environment == "test"
    get_settings.cache_clear()
