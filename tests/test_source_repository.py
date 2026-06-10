from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.source import (
    SOURCE_STATUS_ACTIVE,
    SOURCE_STATUS_INACTIVE,
)
from app.infrastructure.database import Base, SourceModel
from app.repositories.sources import SourceRepository
from app.services.sources import (
    InactiveSourceError,
    SourceNotFoundError,
    SourceService,
)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        yield session


def add_source(
    session: Session,
    *,
    source_id: int = 1001,
    status: str = SOURCE_STATUS_ACTIVE,
    api_key_hash: str = "hash",
) -> None:
    session.add(
        SourceModel(
            id=source_id,
            name="example",
            type="api",
            status=status,
            api_key_hash=api_key_hash,
        )
    )
    session.commit()


def test_find_by_id_returns_source(session: Session) -> None:
    add_source(session, source_id=1001)
    repository = SourceRepository(session)

    source = repository.find_by_id(1001)

    assert source is not None
    assert source.id == 1001
    assert source.is_active


def test_is_active_returns_false_for_inactive_or_missing_source(
    session: Session,
) -> None:
    add_source(session, source_id=1001, status=SOURCE_STATUS_INACTIVE)
    repository = SourceRepository(session)

    assert repository.is_active(1001) is False
    assert repository.is_active(9999) is False


def test_require_active_source_rejects_missing_source(session: Session) -> None:
    service = SourceService(SourceRepository(session))

    with pytest.raises(SourceNotFoundError) as exc_info:
        service.require_active_source(9999)

    assert exc_info.value.status_code == 404


def test_require_active_source_rejects_inactive_source(session: Session) -> None:
    add_source(session, status=SOURCE_STATUS_INACTIVE)
    service = SourceService(SourceRepository(session))

    with pytest.raises(InactiveSourceError) as exc_info:
        service.require_active_source(1001)

    assert exc_info.value.status_code == 403


def test_require_active_source_allows_active_source(session: Session) -> None:
    add_source(session, source_id=1001)
    service = SourceService(SourceRepository(session))

    source = service.require_active_source(1001)

    assert source.id == 1001
