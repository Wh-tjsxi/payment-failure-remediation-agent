from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg

from payment_failure_remediation_agent.config import DATABASE_URL


@asynccontextmanager
async def get_connection() -> AsyncIterator[psycopg.AsyncConnection]:
    """Open one async Postgres connection per call.

    Activities and FastAPI routes run inside an asyncio event loop, so a
    blocking (sync) psycopg connection would stall every other task on that
    loop while a query is in flight. This keeps every DB call non-blocking.
    A connection pool would be the next step once call volume matters; a
    solo/single-user project doesn't need one yet.
    """
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        yield conn
