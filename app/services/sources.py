from dataclasses import dataclass

from app.domain.source import Source
from app.repositories.sources import SourceRepository


@dataclass(frozen=True)
class SourceAccessError(Exception):
    message: str
    status_code: int


class InvalidApiKeyError(SourceAccessError):
    def __init__(self) -> None:
        super().__init__("invalid API key", 401)


class SourceNotFoundError(SourceAccessError):
    def __init__(self, *, status_code: int = 404) -> None:
        super().__init__("source not found", status_code)


class InactiveSourceError(SourceAccessError):
    def __init__(self) -> None:
        super().__init__("source is inactive", 403)


class SourceService:
    def __init__(self, source_repository: SourceRepository) -> None:
        self._source_repository = source_repository

    def authenticate_by_api_key_hash(self, api_key_hash: str) -> Source:
        source = self._source_repository.find_by_api_key_hash(api_key_hash)
        if source is None:
            raise InvalidApiKeyError()
        if not source.is_active:
            raise InactiveSourceError()
        return source

    def require_active_source(self, source_id: int) -> Source:
        source = self._source_repository.find_by_id(source_id)
        if source is None:
            raise SourceNotFoundError()
        if not source.is_active:
            raise InactiveSourceError()
        return source
