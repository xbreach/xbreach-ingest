from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import require_api_user
from app.infrastructure.database import get_session_dependency
from app.repositories.breaches import BreachRepository
from app.repositories.ingestion_jobs import IngestionJobRepository
from app.repositories.sources import SourceRepository
from app.schemas.upload import UploadIngestResponse
from app.services.sources import SourceAccessError
from app.services.upload import UploadIngestService, UploadValidationError

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


def get_upload_service(
    session: Session = Depends(get_session_dependency),
) -> UploadIngestService:
    return UploadIngestService(
        source_repository=SourceRepository(session),
        breach_repository=BreachRepository(session),
        job_repository=IngestionJobRepository(session),
    )


@router.post("/upload", response_model=UploadIngestResponse)
def upload_file(
    file: UploadFile = File(...),
    source_id: int = Form(...),
    breach_name: str = Form(...),
    collected_at: datetime | None = Form(None),
    _authenticated_email: str = Depends(require_api_user),
    upload_service: UploadIngestService = Depends(get_upload_service),
) -> UploadIngestResponse:
    try:
        result = upload_service.upload(
            file=file,
            source_id=source_id,
            breach_name=breach_name,
            collected_at=collected_at,
        )
    except (SourceAccessError, UploadValidationError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return UploadIngestResponse(job_id=result.job_id, file_path=result.file_path)
