from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_healthcheck_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_settings_load_from_environment(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("XBREACH_ENVIRONMENT", "test")

    settings = get_settings()

    assert settings.environment == "test"
    get_settings.cache_clear()
