"""One engine, a fresh AsyncSession per operation, explicit durable mode."""
import os
import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select, literal
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

ROOT = Path(__file__).resolve().parents[2]

# CLI migrations and standalone async callers use the Windows selector policy.
# Uvicorn selects its own loop factory; the local server entrypoint sets it explicitly.
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def selector_event_loop():
    """Uvicorn-compatible Windows loop factory for async psycopg."""
    return asyncio.SelectorEventLoop()


class Database:
    def __init__(self, url: str):
        if make_url(url).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        self.engine = create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=0,
                                         connect_args={"connect_timeout": 3, "options": "-c statement_timeout=5000"}, hide_parameters=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def ping(self):
        async with self.sessions() as session:
            await session.execute(select(literal(1)))

    async def migrate(self, revision="head"):
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "migrations"))
        def run(connection):
            config.attributes["connection"] = connection
            if revision == "base":
                command.downgrade(config, revision)
            else:
                command.upgrade(config, revision)
        async with self.engine.begin() as connection:
            await connection.run_sync(run)

    async def close(self):
        await self.engine.dispose()


def configured_database():
    mode = os.getenv("CATAN_PERSISTENCE_MODE", "durable" if os.getenv("DATABASE_URL") else "memory")
    if mode == "memory":
        if os.getenv("DATABASE_URL"):
            raise ValueError("Explicit memory mode cannot ignore DATABASE_URL")
        return None
    if mode != "durable":
        raise ValueError("Invalid persistence mode")
    if os.getenv("DATABASE_URL"):
        return Database(os.environ["DATABASE_URL"])
    required = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "CATAN_DATABASE_HOST")
    if not all(os.getenv(key) for key in required):
        raise ValueError("Durable mode requires DATABASE_URL or complete PostgreSQL environment")
    # URL.create safely handles passwords with @/:/%; never interpolate credentials into a URL.
    return Database(URL.create("postgresql+psycopg", username=os.environ["POSTGRES_USER"],
                               password=os.environ["POSTGRES_PASSWORD"], host=os.environ["CATAN_DATABASE_HOST"],
                               port=5432, database=os.environ["POSTGRES_DB"]))
