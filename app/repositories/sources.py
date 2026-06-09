from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.source import SOURCE_STATUS_ACTIVE, Source
from app.infrastructure.database import SourceModel


class SourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, source_id: int) -> Source | None:
        model = self._session.get(SourceModel, source_id)
        return self._to_entity(model) if model else None

    def is_active(self, source_id: int) -> bool:
        statement = select(SourceModel.status).where(SourceModel.id == source_id)
        status = self._session.scalar(statement)
        return status == SOURCE_STATUS_ACTIVE

    @staticmethod
    def _to_entity(model: SourceModel) -> Source:
        return Source(
            id=model.id,
            name=model.name,
            type=model.type,
            status=model.status,
            api_key_hash=model.api_key_hash,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
