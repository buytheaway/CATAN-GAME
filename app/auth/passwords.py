import re
import secrets
import unicodedata

import anyio
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from .security import AuthError

hasher = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1, type=Type.ID)
dummy_hash = hasher.hash(secrets.token_urlsafe(32))
limiter = anyio.CapacityLimiter(2)


def username(value):
    if (not isinstance(value, str) or any(unicodedata.category(c).startswith("C") for c in value)
            or not re.fullmatch(r"[A-Za-z0-9_-]{3,32}", value.strip())):
        raise AuthError("invalid_username", 400)
    return value.strip().lower()


def display_name(value):
    if (not isinstance(value, str) or not 1 <= len(value.strip()) <= 32
            or any(unicodedata.category(c).startswith("C") for c in value)):
        raise AuthError("invalid_display_name", 400)
    return value.strip()


def password(value):
    try:
        valid = isinstance(value, str) and 10 <= len(value) <= 128 and len(value.encode("utf-8")) <= 512
    except UnicodeError:
        valid = False
    if not valid:
        raise AuthError("invalid_password", 400)
    return value  # Unicode is preserved exactly; no trimming or composition rules.


async def hash_password(value):
    return await anyio.to_thread.run_sync(hasher.hash, value, limiter=limiter)


def _verify(encoded, value):
    try:
        return hasher.verify(encoded or dummy_hash, value)
    except VerifyMismatchError:
        return False
    except (InvalidHashError, VerificationError):
        try:
            hasher.verify(dummy_hash, value)
        except VerificationError:
            pass
        return False


async def verify_password(encoded, value):
    return await anyio.to_thread.run_sync(_verify, encoded, value, limiter=limiter)
