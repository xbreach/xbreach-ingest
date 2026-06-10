from redis import Redis

from app.core.config import get_settings


def check_redis() -> bool:
    settings = get_settings()
    client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    return bool(client.ping())
