import os
from contextvars import ContextVar
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import select
from app.persistence import models as m
from app.persistence.credentials import utcnow

COOKIE = "catan_session"
SESSION_AGE = timedelta(days=30)
authorization = ContextVar("account_authorization", default=None)


class AuthError(Exception):
    def __init__(self, code, status=401):
        self.code, self.status = code, status
        super().__init__(code)


def development():
    return os.getenv("CATAN_AUTH_MODE", "production") == "development"


def allowed_origin(origin):
    if not origin or origin == "null":
        return False
    configured = os.getenv("CATAN_AUTH_ORIGINS", "")
    if not configured and development():
        configured = "http://localhost,http://127.0.0.1,http://localhost:5173,http://127.0.0.1:5173"
    allowed = {value.strip() for value in configured.split(",") if value.strip()}
    try:
        parsed = urlsplit(origin)
        return (origin in allowed and parsed.scheme in (("http", "https") if development() else ("https",))
                and bool(parsed.netloc) and not parsed.username and not parsed.password
                and not parsed.path and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def require_origin(request):
    if not allowed_origin(request.headers.get("origin")):
        raise AuthError("origin_forbidden", 403)


def same_origin_guest(ws, origin):
    """Keep plain-HTTP same-origin guest play usable without enabling cookie auth."""
    try:
        parsed = urlsplit(origin or "")
        return (parsed.scheme in ("http", "https") and parsed.netloc == ws.headers.get("host")
                and not parsed.path and not parsed.query and not parsed.fragment and not parsed.username)
    except ValueError:
        return False


def set_cookie(response, raw):
    response.set_cookie(COOKIE, raw, max_age=int(SESSION_AGE.total_seconds()),
                        httponly=True, secure=not development(), samesite="lax", path="/")


def clear_cookie(response):
    response.delete_cookie(COOKIE, httponly=True, secure=not development(), samesite="lax", path="/")


async def authorize_transaction(session):
    """Share-lock session/user until room COMMIT; logout's UPDATE orders after it."""
    identity = authorization.get()
    if identity is None:
        return
    row = (await session.execute(select(m.user_sessions.c.id).select_from(
        m.user_sessions.join(m.users)).where(
        m.user_sessions.c.id == identity["session_id"], m.user_sessions.c.user_id == identity["user_id"],
        m.user_sessions.c.revoked_at.is_(None), m.user_sessions.c.expires_at > utcnow(),
        m.users.c.disabled_at.is_(None)).with_for_update(read=True))).first()
    if row is None:
        raise AuthError("session_expired")
