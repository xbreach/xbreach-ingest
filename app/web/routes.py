from datetime import UTC, date, datetime, time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.database import (
    IngestionJobModel,
    SourceModel,
    get_session_dependency,
)
from app.repositories.breaches import BreachRepository
from app.repositories.ingestion_jobs import IngestionJobRepository
from app.repositories.sources import SourceRepository
from app.services.sources import SourceAccessError
from app.services.upload import UploadIngestService, UploadValidationError

JOB_LISTING_PAGE_SIZE = 20
JOB_STATUS_OPTIONS = ["pending", "running", "completed", "failed"]

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "page_title": "Login"},
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    summary = {
        "sources": session.scalar(select(func.count()).select_from(SourceModel)) or 0,
        "jobs": session.scalar(select(func.count()).select_from(IngestionJobModel)) or 0,
        "pending_jobs": _count_jobs_by_status(session, "pending"),
        "failed_jobs": _count_jobs_by_status(session, "failed"),
    }
    recent_jobs = session.scalars(
        select(IngestionJobModel).order_by(IngestionJobModel.created_at.desc()).limit(5)
    ).all()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "page_title": "Dashboard",
            "summary": summary,
            "recent_jobs": recent_jobs,
        },
    )


@router.get("/jobs", response_class=HTMLResponse)
def jobs(
    request: Request,
    status: str | None = None,
    source_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    filename: str | None = None,
    page: int = Query(1, ge=1),
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    filters = JobListingFilters(
        status=status,
        source_id=source_id,
        date_from=date_from,
        date_to=date_to,
        filename=filename.strip() if filename else None,
    )
    statement = _filtered_jobs_statement(filters)
    total_jobs = session.scalar(
        select(func.count()).select_from(statement.subquery())
    ) or 0
    total_pages = max(1, (total_jobs + JOB_LISTING_PAGE_SIZE - 1) // JOB_LISTING_PAGE_SIZE)
    current_page = min(page, total_pages)
    job_rows = session.scalars(
        statement.offset((current_page - 1) * JOB_LISTING_PAGE_SIZE).limit(
            JOB_LISTING_PAGE_SIZE
        )
    ).all()
    sources = session.scalars(select(SourceModel).order_by(SourceModel.name.asc())).all()
    source_names = {source.id: source.name for source in sources}
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {
            "request": request,
            "page_title": "Jobs",
            "jobs": job_rows,
            "sources": sources,
            "source_names": source_names,
            "status_options": JOB_STATUS_OPTIONS,
            "filters": filters,
            "page": current_page,
            "page_size": JOB_LISTING_PAGE_SIZE,
            "total_jobs": total_jobs,
            "total_pages": total_pages,
            "previous_page_url": _jobs_page_url(request, current_page - 1)
            if current_page > 1
            else None,
            "next_page_url": _jobs_page_url(request, current_page + 1)
            if current_page < total_pages
            else None,
        },
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(
    job_id: int,
    request: Request,
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    job = session.get(IngestionJobModel, job_id)
    return templates.TemplateResponse(
        request,
        "job_detail.html",
        {"request": request, "page_title": f"Job {job_id}", "job": job},
        status_code=200 if job else 404,
    )


@router.get("/upload", response_class=HTMLResponse)
def upload(
    request: Request,
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "upload.html",
        _upload_context(
            request=request,
            sources=_list_sources(session),
        ),
    )


@router.post("/upload", response_class=HTMLResponse)
def submit_upload(
    request: Request,
    source_id: int = Form(...),
    breach_name: str = Form(...),
    collected_at: str = Form(""),
    api_key: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    upload_service = UploadIngestService(
        source_repository=SourceRepository(session),
        breach_repository=BreachRepository(session),
        job_repository=IngestionJobRepository(session),
    )
    try:
        parsed_collected_at = _parse_collected_at(collected_at)
        result = upload_service.upload(
            file=file,
            source_id=source_id,
            breach_name=breach_name,
            collected_at=parsed_collected_at,
            api_key=api_key,
        )
    except ValueError:
        return _upload_response(
            request=request,
            session=session,
            error_message="collected at must be a valid datetime",
            status_code=400,
            selected_source_id=source_id,
            breach_name=breach_name,
            collected_at=collected_at,
        )
    except (SourceAccessError, UploadValidationError) as exc:
        return _upload_response(
            request=request,
            session=session,
            error_message=exc.message,
            status_code=exc.status_code,
            selected_source_id=source_id,
            breach_name=breach_name,
            collected_at=collected_at,
        )

    return _upload_response(
        request=request,
        session=session,
        job_id=result.job_id,
        selected_source_id=source_id,
    )


@router.get("/sources", response_class=HTMLResponse)
def sources(
    request: Request,
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    source_rows = session.scalars(
        select(SourceModel).order_by(SourceModel.created_at.desc()).limit(50)
    ).all()
    return templates.TemplateResponse(
        request,
        "sources.html",
        {"request": request, "page_title": "Sources", "sources": source_rows},
    )


def _count_jobs_by_status(session: Session, status: str) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(IngestionJobModel)
            .where(IngestionJobModel.status == status)
        )
        or 0
    )


def _list_sources(session: Session) -> list[SourceModel]:
    return session.scalars(select(SourceModel).order_by(SourceModel.name.asc())).all()


def _upload_context(
    *,
    request: Request,
    sources: list[SourceModel],
    error_message: str | None = None,
    job_id: int | None = None,
    selected_source_id: int | None = None,
    breach_name: str = "",
    collected_at: str = "",
) -> dict:
    return {
        "request": request,
        "page_title": "Upload",
        "sources": sources,
        "error_message": error_message,
        "job_id": job_id,
        "selected_source_id": selected_source_id,
        "breach_name": breach_name,
        "collected_at": collected_at,
    }


def _upload_response(
    *,
    request: Request,
    session: Session,
    error_message: str | None = None,
    job_id: int | None = None,
    status_code: int = 200,
    selected_source_id: int | None = None,
    breach_name: str = "",
    collected_at: str = "",
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "upload.html",
        _upload_context(
            request=request,
            sources=_list_sources(session),
            error_message=error_message,
            job_id=job_id,
            selected_source_id=selected_source_id,
            breach_name=breach_name,
            collected_at=collected_at,
        ),
        status_code=status_code,
    )


def _parse_collected_at(collected_at: str):
    if not collected_at:
        return None
    return datetime.fromisoformat(collected_at)


class JobListingFilters:
    def __init__(
        self,
        *,
        status: str | None,
        source_id: int | None,
        date_from: date | None,
        date_to: date | None,
        filename: str | None,
    ) -> None:
        self.status = status
        self.source_id = source_id
        self.date_from = date_from
        self.date_to = date_to
        self.filename = filename


def _filtered_jobs_statement(filters: JobListingFilters):
    statement = select(IngestionJobModel)

    if filters.status:
        statement = statement.where(IngestionJobModel.status == filters.status)
    if filters.source_id:
        statement = statement.where(IngestionJobModel.source_id == filters.source_id)
    if filters.date_from:
        statement = statement.where(
            IngestionJobModel.created_at >= _start_of_day(filters.date_from)
        )
    if filters.date_to:
        statement = statement.where(
            IngestionJobModel.created_at <= _end_of_day(filters.date_to)
        )
    if filters.filename:
        statement = statement.where(
            IngestionJobModel.original_filename.ilike(f"%{filters.filename}%")
        )

    return statement.order_by(
        IngestionJobModel.created_at.desc(),
        IngestionJobModel.id.desc(),
    )


def _jobs_page_url(request: Request, page: int) -> str:
    params = dict(request.query_params)
    params["page"] = str(page)
    return str(request.url.include_query_params(**params))


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _end_of_day(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=UTC)
