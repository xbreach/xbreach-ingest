from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "xbreach-ingest"
    app_version: str = "0.1.0"
    environment: str = "local"
    log_level: str = "INFO"
    data_path: str = "/data/xbreach"
    app_id: int = 1
    node_id: int = 1
    upload_max_file_size_bytes: int = 104_857_600
    login_email: str = "admin@xbreach.local"
    login_password: str = "xbreach"
    session_secret: str = "change-me-in-production-with-32-bytes-minimum"
    session_max_age_seconds: int = 28_800

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "xbreach"
    postgres_user: str = "xbreach"
    postgres_password: str = "xbreach"

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="XBREACH_",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
