"""CLI and backend share the same migration path; no credential logging."""
import asyncio
import os
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from app.persistence.models import metadata
from app.persistence.db import Database  # Applies Windows selector policy for CLI too.


def migrate(connection):
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(os.environ["DATABASE_URL"], hide_parameters=True)
    async with engine.begin() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


connection = context.config.attributes.get("connection")
if connection is not None:
    migrate(connection)
elif context.is_offline_mode():
    context.configure(url="postgresql+psycopg://", target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
