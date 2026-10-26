"""Seed only a synthetic pinned owner in an explicitly disposable localhost DB."""
import asyncio
import os
from sqlalchemy import select, insert
from sqlalchemy.engine import make_url
from app.auth.passwords import hash_password
from app.auth.security import OWNER_ACCOUNT_ID
from app.persistence import models as m
from app.persistence.credentials import utcnow
from app.persistence.db import Database


async def main():
    url = make_url(os.environ["CATAN_TEST_DATABASE_URL"])
    if (url.drivername != "postgresql+psycopg" or url.host not in ("127.0.0.1", "localhost", "::1")
            or not url.database.endswith("_test")):
        raise SystemExit("Only a disposable localhost *_test database is allowed")
    db = Database(url)
    try:
        await db.migrate()
        async with db.sessions() as session, session.begin():
            if not (await session.execute(select(m.users.c.id).where(m.users.c.id == OWNER_ACCOUNT_ID))).first():
                now = utcnow()
                await session.execute(insert(m.users).values(id=OWNER_ACCOUNT_ID, username="buytheaway",
                    username_normalized="buytheaway", display_name="Owner UI fixture",
                    password_hash=await hash_password("correct horse battery staple"), created_at=now, updated_at=now))
        print("Synthetic owner fixture present; no production database was accessed")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
