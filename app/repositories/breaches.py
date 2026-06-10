from sqlalchemy.orm import Session

from app.domain.breach import Breach
from app.infrastructure.database import BreachModel
from app.schemas.breach import CreateBreach


class BreachRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_breach(self, breach: CreateBreach) -> Breach:
        model = BreachModel(
            id=breach.id,
            source_id=breach.source_id,
            name=breach.name,
            description=breach.description,
            collected_at=breach.collected_at,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: BreachModel) -> Breach:
        return Breach(
            id=model.id,
            source_id=model.source_id,
            name=model.name,
            description=model.description,
            collected_at=model.collected_at,
            created_at=model.created_at,
        )
