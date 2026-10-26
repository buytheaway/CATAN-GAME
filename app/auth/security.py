import os
import ipaddress
import uuid
from contextvars import ContextVar
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import select
from app.persistence import models as m
from app.persistence.credentials import utcnow

COOKIE = "catan_session"
SESSION_AGE = timedelta(days=30)
authorization = ContextVar("account_authorization", default=None)
# Pinned to the existing, inspected account, never a claimed name or registration.
OWNER_ACCOUNT_ID = uuid.UUID("9ceeeab2-9d25-4e67-84f7-3bb09e4914c6")
owner_test_tools_required = ContextVar("owner_test_tools_required", default=False)


def owner_test_enabled(identity):
    return bool(identity and identity.get("user_id", identity.get("id")) == OWNER_ACCOUNT_ID
                and identity.get("test_tools_enabled") is True)


def client_ip(request):
    """Canonical ASGI peer authenticated by Uvicorn; never parse client headers."""
    client = getattr(request, "client", None)
    peer = client.host if client else "unknown"
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    return str(address.ipv4_mapped or address) if address.version == 6 else str(address)


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


async def authorize_transaction(session, *, exclusive=False):
    """Share-lock session/user until room COMMIT; logout's UPDATE orders after it."""
    identity = authorization.get()
    row = None
    if identity is not None:
        row = (await session.execute(select(m.users.c.id.label("user_id"), m.users.c.test_tools_enabled).select_from(
            m.user_sessions.join(m.users)).where(
            m.user_sessions.c.id == identity["session_id"], m.user_sessions.c.user_id == identity["user_id"],
            m.user_sessions.c.revoked_at.is_(None), m.user_sessions.c.expires_at > utcnow(),
            m.users.c.disabled_at.is_(None)).with_for_update(read=not exclusive))).mappings().one_or_none()
        if row is None:
            raise AuthError("session_expired")
    if owner_test_tools_required.get():
        enabled = (await session.execute(select(m.users.c.test_tools_enabled).where(
            m.users.c.id == OWNER_ACCOUNT_ID, m.users.c.disabled_at.is_(None)
        ).with_for_update(read=True))).scalar_one_or_none()
        if enabled is not True:
            raise AuthError("test_mode_disabled", 403)
    return row
