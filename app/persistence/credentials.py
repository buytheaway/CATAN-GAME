import hashlib
import secrets
from datetime import datetime, timedelta, timezone

TOKEN_IDLE_DAYS = 30


def utcnow():
    return datetime.now(timezone.utc)


def token_hash(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("utf-8")).digest()


def issue_token() -> str:
    return secrets.token_urlsafe(32)


def renewed_expiry():
    return utcnow() + timedelta(days=TOKEN_IDLE_DAYS)


def valid_token(slot, raw: str) -> bool:
    return bool(slot.token_hash and slot.token_revoked_at is None and slot.token_expires_at and slot.token_expires_at > utcnow()
                and secrets.compare_digest(slot.token_hash, token_hash(raw)))
