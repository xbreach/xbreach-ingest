from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.database import (
    IngestionJobModel,
    SourceModel,
    get_session_dependency,
)

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
    session: Session = Depends(get_session_dependency),
) -> HTMLResponse:
    job_rows = session.scalars(
        select(IngestionJobModel).order_by(IngestionJobModel.created_at.desc()).limit(50)
    ).all()
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {"request": request, "page_title": "Jobs", "jobs": job_rows},
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
