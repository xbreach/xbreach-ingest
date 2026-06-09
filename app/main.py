from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.upload import router as upload_router
from app.core.config import get_settings
from app.web.routes import router as web_router

settings = get_settings()
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(web_router)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(upload_router)
