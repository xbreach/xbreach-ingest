import hashlib
import secrets
from datetime import UTC, date, datetime, time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import (
    AUTH_COOKIE_NAME,
    authenticate_credentials,
    authenticated_email_from_request,
    create_access_token,
    require_web_user,
)
from app.core.config import get_settings
from app.domain.snowflake import SnowflakeGenerator
from app.domain.source import SOURCE_STATUS_ACTIVE, SOURCE_STATUS_INACTIVE
from app.infrastructure.database import (
    BreachModel,
    IngestionJobErrorModel,
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
SOURCE_STATUS_OPTIONS = ["active", "inactive", "disabled"]

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login(request: Request, next: str = "/dashboard") -> Response:
    if authenticated_email_from_request(request):
        return RedirectResponse(url=_safe_next_url(next), status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "page_title": "Login",
            "next": _safe_next_url(next),
            "is_authenticated": False,
        },
    )


@router.post("/login", response_class=HTMLResponse)
def submit_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard"),
) -> Response:
    settings = get_settings()
    if not authenticate_credentials(email, password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "page_title": "Login",
                "next": _safe_next_url(next),
                "error_message": "invalid email or password",
                "is_authenticated": False,
            },
            status_code=401,
        )

    response = RedirectResponse(url=_safe_next_url(next), status_code=303)
    response.set_cookie(
        AUTH_COOKIE_NAME,
        create_access_token(email),
        httponly=True,
        max_age=settings.session_max_age_seconds,
        samesite="lax",
    )
    return response


@router.post("/logout", include_in_schema=False)
def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response


def _safe_next_url(next_url: str) -> str:
    if not next_url.startswith("/") or next_url.startswith("//"):
        return "/dashboard"
    return next_url


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    authenticated_email: str = Depends(require_web_user),
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
            "is_authenticated": True,
            "authenticated_email": authenticated_email,
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
    authenticated_email: str = Depends(require_web_user),
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
            "is_authenticated": True,
            "authenticated_email": authenticated_email,
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
    authenticated_email: str = Depends(require_web_user),
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    job = session.get(IngestionJobModel, job_id)
    source = session.get(SourceModel, job.source_id) if job else None
    breach = session.get(BreachModel, job.breach_id) if job and job.breach_id else None
    error_summary = _job_error_summary(session, job_id) if job else []
    recent_errors = _recent_job_errors(session, job_id) if job else []
    return templates.TemplateResponse(
        request,
        "job_detail.html",
        {
            "request": request,
            "page_title": f"Job {job_id}",
            "is_authenticated": True,
            "authenticated_email": authenticated_email,
            "job": job,
            "source": source,
            "breach": breach,
            "error_summary": error_summary,
            "recent_errors": recent_errors,
            "progress_percent": _job_progress_percent(job),
        },
        status_code=200 if job else 404,
    )


@router.get("/upload", response_class=HTMLResponse)
def upload(
    request: Request,
    authenticated_email: str = Depends(require_web_user),
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "upload.html",
        _upload_context(
            request=request,
            authenticated_email=authenticated_email,
            sources=_list_sources(session),
        ),
    )


@router.post("/upload", response_class=HTMLResponse)
def submit_upload(
    request: Request,
    source_id: int = Form(...),
    breach_name: str = Form(...),
    collected_at: str = Form(""),
    file: UploadFile = File(...),
    authenticated_email: str = Depends(require_web_user),
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
        )
    except ValueError:
        return _upload_response(
            request=request,
            session=session,
            authenticated_email=authenticated_email,
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
            authenticated_email=authenticated_email,
            error_message=exc.message,
            status_code=exc.status_code,
            selected_source_id=source_id,
            breach_name=breach_name,
            collected_at=collected_at,
        )

    return _upload_response(
        request=request,
        session=session,
        authenticated_email=authenticated_email,
        job_id=result.job_id,
        selected_source_id=source_id,
    )


@router.get("/sources", response_class=HTMLResponse)
def sources(
    request: Request,
    authenticated_email: str = Depends(require_web_user),
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    return _sources_response(
        request=request,
        session=session,
        authenticated_email=authenticated_email,
    )


@router.post("/sources", response_class=HTMLResponse)
def create_source(
    request: Request,
    name: str = Form(...),
    type: str = Form(...),
    status: str = Form(SOURCE_STATUS_ACTIVE),
    authenticated_email: str = Depends(require_web_user),
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    name = name.strip()
    source_type = type.strip()
    if not name or not source_type or status not in SOURCE_STATUS_OPTIONS:
        return _sources_response(
            request=request,
            session=session,
            authenticated_email=authenticated_email,
            error_message="source name, type and status are required",
            status_code=400,
            form_values={"name": name, "type": source_type, "status": status},
        )

    source = SourceModel(
        id=_next_source_id(),
        name=name,
        type=source_type,
        status=status,
        api_key_hash=_hash_api_key(secrets.token_urlsafe(32)),
    )
    session.add(source)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return _sources_response(
            request=request,
            session=session,
            authenticated_email=authenticated_email,
            error_message="failed to create source",
            status_code=409,
            form_values={"name": name, "type": source_type, "status": status},
        )

    return _sources_response(
        request=request,
        session=session,
        authenticated_email=authenticated_email,
        success_message="source created",
    )


@router.post("/sources/{source_id}/toggle", response_class=HTMLResponse)
def toggle_source_status(
    source_id: int,
    request: Request,
    authenticated_email: str = Depends(require_web_user),
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    source = session.get(SourceModel, source_id)
    if source is None:
        return _sources_response(
            request=request,
            session=session,
            authenticated_email=authenticated_email,
            error_message="source not found",
            status_code=404,
        )

    source.status = (
        SOURCE_STATUS_INACTIVE
        if source.status == SOURCE_STATUS_ACTIVE
        else SOURCE_STATUS_ACTIVE
    )
    source.updated_at = datetime.now(UTC)
    session.commit()
    return _sources_response(
        request=request,
        session=session,
        authenticated_email=authenticated_email,
        success_message=f"source {source.id} updated",
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


def _sources_response(
    *,
    request: Request,
    session: Session,
    authenticated_email: str,
    error_message: str | None = None,
    success_message: str | None = None,
    status_code: int = 200,
    form_values: dict | None = None,
) -> HTMLResponse:
    source_rows = session.scalars(
        select(SourceModel).order_by(SourceModel.created_at.desc()).limit(100)
    ).all()
    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            "request": request,
            "page_title": "Sources",
            "is_authenticated": True,
            "authenticated_email": authenticated_email,
            "sources": source_rows,
            "status_options": SOURCE_STATUS_OPTIONS,
            "error_message": error_message,
            "success_message": success_message,
            "form_values": form_values or {
                "name": "",
                "type": "api",
                "status": SOURCE_STATUS_ACTIVE,
            },
        },
        status_code=status_code,
    )


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _next_source_id() -> int:
    settings = get_settings()
    return SnowflakeGenerator(app_id=settings.app_id, node_id=settings.node_id).next_id()


def _job_error_summary(session: Session, job_id: int):
    statement = (
        select(
            IngestionJobErrorModel.error_type,
            func.count(IngestionJobErrorModel.id).label("total"),
        )
        .where(IngestionJobErrorModel.job_id == job_id)
        .group_by(IngestionJobErrorModel.error_type)
        .order_by(func.count(IngestionJobErrorModel.id).desc())
    )
    return session.execute(statement).all()


def _recent_job_errors(session: Session, job_id: int) -> list[IngestionJobErrorModel]:
    statement = (
        select(IngestionJobErrorModel)
        .where(IngestionJobErrorModel.job_id == job_id)
        .order_by(IngestionJobErrorModel.created_at.desc())
        .limit(10)
    )
    return list(session.scalars(statement).all())


def _job_progress_percent(job: IngestionJobModel | None) -> int:
    if job is None or job.total_lines <= 0:
        return 0
    processed_lines = min(job.parsed_lines + job.rejected_lines, job.total_lines)
    return round((processed_lines / job.total_lines) * 100)


def _list_sources(session: Session) -> list[SourceModel]:
    return session.scalars(select(SourceModel).order_by(SourceModel.name.asc())).all()


def _upload_context(
    *,
    request: Request,
    authenticated_email: str,
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
        "is_authenticated": True,
        "authenticated_email": authenticated_email,
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
    authenticated_email: str,
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
            authenticated_email=authenticated_email,
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
