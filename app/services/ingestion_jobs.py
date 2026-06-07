from app.domain.ingestion_job import IngestionJob
from app.repositories.ingestion_jobs import IngestionJobRepository
from app.schemas.ingestion_job import CreateIngestionJob
from app.services.sources import SourceService


class IngestionJobService:
    def __init__(
        self,
        job_repository: IngestionJobRepository,
        source_service: SourceService,
    ) -> None:
        self._job_repository = job_repository
        self._source_service = source_service

    def create_job(self, job: CreateIngestionJob) -> IngestionJob:
        self._source_service.require_active_source(job.source_id)
        return self._job_repository.create_job(job)
