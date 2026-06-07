from datetime import UTC, datetime

from app.domain.ingestion_job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    IngestionJob,
)
from app.infrastructure.database import IngestionJobModel
from app.schemas.ingestion_job import CreateIngestionJob, IngestionJobProgress
from sqlalchemy import select
from sqlalchemy.orm import Session


class IngestionJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_job(self, job: CreateIngestionJob) -> IngestionJob:
        model = IngestionJobModel(
            id=job.id,
            source_id=job.source_id,
            breach_id=job.breach_id,
            original_filename=job.original_filename,
            stored_filename=job.stored_filename,
            local_path=job.local_path,
            checksum_sha256=job.checksum_sha256,
            file_size_bytes=job.file_size_bytes,
            status=JOB_STATUS_PENDING,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)

    def find_by_id(self, job_id: int) -> IngestionJob | None:
        model = self._session.get(IngestionJobModel, job_id)
        return self._to_entity(model) if model else None

    def find_pending_jobs(
        self,
        limit: int,
        *,
        for_update_skip_locked: bool = False,
    ) -> list[IngestionJob]:
        statement = self.pending_jobs_statement(
            limit=limit,
            for_update_skip_locked=for_update_skip_locked,
        )
        models = self._session.scalars(statement).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def pending_jobs_statement(limit: int, *, for_update_skip_locked: bool = False):
        statement = (
            select(IngestionJobModel)
            .where(IngestionJobModel.status == JOB_STATUS_PENDING)
            .order_by(IngestionJobModel.created_at.asc())
            .limit(limit)
        )

        if for_update_skip_locked:
            statement = statement.with_for_update(skip_locked=True)

        return statement

    def mark_as_processing(self, job_id: int) -> IngestionJob | None:
        model = self._session.get(IngestionJobModel, job_id)
        if model is None or model.status != JOB_STATUS_PENDING:
            return None

        model.status = JOB_STATUS_RUNNING
        model.started_at = model.started_at or self._now()
        model.error_message = None
        model.updated_at = self._now()
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)

    def mark_as_completed(self, job_id: int) -> IngestionJob | None:
        model = self._session.get(IngestionJobModel, job_id)
        if model is None:
            return None

        model.status = JOB_STATUS_COMPLETED
        model.finished_at = self._now()
        model.error_message = None
        model.updated_at = self._now()
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)

    def mark_as_failed(self, job_id: int, error_message: str) -> IngestionJob | None:
        model = self._session.get(IngestionJobModel, job_id)
        if model is None:
            return None

        model.status = JOB_STATUS_FAILED
        model.error_message = error_message
        model.finished_at = self._now()
        model.updated_at = self._now()
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)

    def update_progress(
        self,
        job_id: int,
        progress: IngestionJobProgress,
    ) -> IngestionJob | None:
        model = self._session.get(IngestionJobModel, job_id)
        if model is None:
            return None

        model.total_lines = progress.total_lines
        model.parsed_lines = progress.parsed_lines
        model.rejected_lines = progress.rejected_lines
        model.inserted_lines = progress.inserted_lines
        model.updated_at = self._now()
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: IngestionJobModel) -> IngestionJob:
        return IngestionJob(
            id=model.id,
            source_id=model.source_id,
            breach_id=model.breach_id,
            original_filename=model.original_filename,
            stored_filename=model.stored_filename,
            local_path=model.local_path,
            checksum_sha256=model.checksum_sha256,
            file_size_bytes=model.file_size_bytes,
            status=model.status,
            total_lines=model.total_lines,
            parsed_lines=model.parsed_lines,
            rejected_lines=model.rejected_lines,
            inserted_lines=model.inserted_lines,
            error_message=model.error_message,
            started_at=model.started_at,
            finished_at=model.finished_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)
