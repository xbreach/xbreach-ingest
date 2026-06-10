from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Response

from app.core.auth import (
    AUTH_COOKIE_NAME,
    authenticate_credentials,
    create_access_token,
)
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response) -> LoginResponse:
    if not authenticate_credentials(payload.email, payload.password):
        raise HTTPException(status_code=401, detail="invalid email or password")

    settings = get_settings()
    access_token = create_access_token(payload.email)
    response.set_cookie(
        AUTH_COOKIE_NAME,
        access_token,
        httponly=True,
        max_age=settings.session_max_age_seconds,
        samesite="lax",
    )
    return LoginResponse(
        access_token=access_token,
        expires_in=settings.session_max_age_seconds,
    )


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(AUTH_COOKIE_NAME)
    return {"status": "ok"}
