import pytest

from app.domain.source import SOURCE_STATUS_INACTIVE, Source
from app.schemas.ingestion_job import CreateIngestionJob
from app.services.ingestion_jobs import IngestionJobService
from app.services.sources import InactiveSourceError, SourceService


class FakeJobRepository:
    def __init__(self) -> None:
        self.created_jobs: list[CreateIngestionJob] = []

    def create_job(self, job: CreateIngestionJob):
        self.created_jobs.append(job)
        return job


class FakeSourceRepository:
    def __init__(self, source: Source | None) -> None:
        self.source = source

    def find_by_id(self, source_id: int) -> Source | None:
        return self.source


def create_job_dto() -> CreateIngestionJob:
    return CreateIngestionJob(
        id=1001,
        source_id=2001,
        breach_id=None,
        original_filename="input.txt",
        stored_filename="stored.txt",
        local_path="/data/xbreach/storage/stored.txt",
        checksum_sha256="a" * 64,
        file_size_bytes=128,
    )


def test_inactive_source_cannot_create_job(inactive_source: Source) -> None:
    job_repository = FakeJobRepository()
    service = IngestionJobService(
        job_repository=job_repository,  # type: ignore[arg-type]
        source_service=SourceService(FakeSourceRepository(inactive_source)),  # type: ignore[arg-type]
    )

    with pytest.raises(InactiveSourceError):
        service.create_job(create_job_dto())

    assert job_repository.created_jobs == []


@pytest.fixture()
def inactive_source() -> Source:
    from datetime import UTC, datetime

    now = datetime(2026, 1, 1, tzinfo=UTC)
    return Source(
        id=2001,
        name="inactive",
        type="api",
        status=SOURCE_STATUS_INACTIVE,
        api_key_hash="hash",
        created_at=now,
        updated_at=now,
    )
