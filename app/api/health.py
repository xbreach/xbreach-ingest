from collections.abc import Callable

from fastapi import APIRouter

from app.core.config import get_settings
from app.infrastructure.postgres import check_postgres
from app.infrastructure.redis import check_redis

router = APIRouter(tags=["health"])


def _dependency_status(check: Callable[[], bool]) -> str:
    try:
        return "ok" if check() else "error"
    except Exception:
        return "error"


@router.get("/health")
def healthcheck() -> dict[str, str]:
    settings = get_settings()
    postgres_status = _dependency_status(check_postgres)
    redis_status = _dependency_status(check_redis)

    return {
        "status": "ok" if postgres_status == redis_status == "ok" else "error",
        "environment": settings.environment,
        "service": settings.app_name,
        "postgres": postgres_status,
        "redis": redis_status,
    }
