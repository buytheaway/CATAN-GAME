import re
import uuid
from datetime import timedelta

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from app.persistence import models as m
from app.persistence.credentials import issue_token, token_hash, utcnow
from . import passwords
from .security import AuthError, SESSION_AGE


def safe_user(row):
    return {"username": row["username"], "display_name": row["display_name"]}


class AuthService:
    def __init__(self, database):
        self.db = database

    async def resolve_hash(self, digest):
        if digest is None:
            return None
        now = utcnow()
        async with self.db.sessions() as session, session.begin():
            row = (await session.execute(select(
                m.users.c.id.label("user_id"), m.users.c.username, m.users.c.display_name,
                m.user_sessions.c.id.label("session_id"), m.user_sessions.c.expires_at,
                m.user_sessions.c.last_seen_at).select_from(m.users.join(m.user_sessions)).where(
                m.user_sessions.c.token_hash == digest, m.user_sessions.c.revoked_at.is_(None),
                m.user_sessions.c.expires_at > now, m.users.c.disabled_at.is_(None)))).mappings().one_or_none()
            if row is None:
                return None
            if row["last_seen_at"] < now - timedelta(minutes=5):
                await session.execute(update(m.user_sessions).where(
                    m.user_sessions.c.id == row["session_id"], m.user_sessions.c.last_seen_at < now - timedelta(minutes=5)
                ).values(last_seen_at=now))
            return {**row, "session_hash": digest}

    async def resolve(self, raw):
        return await self.resolve_hash(token_hash(raw)) if isinstance(raw, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", raw) else None

    async def revoke(self, identity):
        async with self.db.sessions() as session, session.begin():
            await session.execute(update(m.user_sessions).where(m.user_sessions.c.id == identity["session_id"])
                                  .values(revoked_at=utcnow()))

    async def authenticate(self, data, *, register, incoming=None):
        name, secret = passwords.username(data.get("username")), passwords.password(data.get("password"))
        now = utcnow()
        if register:
            public_name = passwords.display_name(data.get("display_name"))
            encoded = await passwords.hash_password(secret)
            user = {"id": uuid.uuid4(), "username": name, "username_normalized": name,
                    "display_name": public_name, "password_hash": encoded, "created_at": now, "updated_at": now}
        else:
            async with self.db.sessions() as session:
                user = (await session.execute(select(m.users).where(m.users.c.username_normalized == name))).mappings().one_or_none()
            verified = await passwords.verify_password(user["password_hash"] if user else None, secret)
            if not user or not verified or user["disabled_at"]:
                raise AuthError("invalid_credentials")
            encoded = await passwords.hash_password(secret) if passwords.hasher.check_needs_rehash(user["password_hash"]) else None
        raw, session_id = issue_token(), uuid.uuid4()
        try:
            async with self.db.sessions() as session, session.begin():
                if register:
                    await session.execute(insert(m.users).values(**user))
                else:
                    # Disable/revoke races cannot issue a session for a disabled account.
                    enabled = (await session.execute(select(m.users.c.id).where(
                        m.users.c.id == user["id"], m.users.c.disabled_at.is_(None)).with_for_update(read=True))).first()
                    if not enabled:
                        raise AuthError("invalid_credentials")
                    if encoded:
                        await session.execute(update(m.users).where(m.users.c.id == user["id"])
                                              .values(password_hash=encoded, updated_at=now))
                if incoming:
                    await session.execute(update(m.user_sessions).where(m.user_sessions.c.id == incoming["session_id"])
                                          .values(revoked_at=now))
                await session.execute(insert(m.user_sessions).values(
                    id=session_id, user_id=user["id"], token_hash=token_hash(raw), created_at=now,
                    expires_at=now + SESSION_AGE, last_seen_at=now))
        except IntegrityError:
            raise AuthError("username_taken", 409) from None
        return raw, safe_user(user)
