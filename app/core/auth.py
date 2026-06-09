import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import jwt
from fastapi import HTTPException, Request

from app.core.config import get_settings

AUTH_COOKIE_NAME = "xbreach_ingest_token"
JWT_ALGORITHM = "HS256"


def authenticate_credentials(email: str, password: str) -> bool:
    settings = get_settings()
    return secrets.compare_digest(
        email,
        settings.login_email,
    ) and secrets.compare_digest(password, settings.login_password)


def create_access_token(email: str) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(
        seconds=settings.session_max_age_seconds
    )
    payload = {
        "sub": email,
        "exp": expires_at,
        "iat": datetime.now(UTC),
        "typ": "access",
    }
    return jwt.encode(payload, settings.session_secret, algorithm=JWT_ALGORITHM)


def authenticated_email_from_request(request: Request) -> str | None:
    token = _token_from_authorization_header(request)
    if token is None:
        token = request.cookies.get(AUTH_COOKIE_NAME)
    if token is None:
        return None
    return verify_access_token(token)


def require_api_user(request: Request) -> str:
    email = authenticated_email_from_request(request)
    if email:
        return email
    raise HTTPException(status_code=401, detail="not authenticated")


def require_web_user(request: Request) -> str:
    email = authenticated_email_from_request(request)
    if email:
        return email
    next_url = request.url.path
    if request.url.query:
        next_url = f"{next_url}?{request.url.query}"
    raise HTTPException(
        status_code=303,
        headers={"Location": f"/login?next={quote(next_url, safe='')}"},
    )


def verify_access_token(token: str) -> str | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    email = payload.get("sub")
    token_type = payload.get("typ")
    if not isinstance(email, str) or token_type != "access":
        return None
    return email


def _token_from_authorization_header(request: Request) -> str | None:
    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token
