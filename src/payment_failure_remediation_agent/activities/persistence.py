"""Real (non-stub) persistence activities, called at every workflow
transition.

Unlike every other Sprint 1 activity, this one isn't a stub -- the whole
point of `cases`/`audit_events` (db/migrations/0001_init.sql) is to mirror
the workflow's actual state as it runs, so there's nothing to fake here.
"""

from psycopg.types.json import Jsonb
from temporalio import activity

from payment_failure_remediation_agent.db import get_connection


@activity.defn(name="persist_case_status")
async def persist_case_status(case_id: str, status: str, attempt_count: int) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE cases SET status = %s, attempt_count = %s, updated_at = now() WHERE id = %s",
            (status, attempt_count, case_id),
        )
        await conn.commit()


@activity.defn(name="append_audit_event")
async def append_audit_event(
    case_id: str,
    from_status: str | None,
    to_status: str,
    detail: dict[str, str] | None = None,
) -> None:
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO audit_events (case_id, from_status, to_status, detail)
            VALUES (%s, %s, %s, %s)
            """,
            (case_id, from_status, to_status, Jsonb(detail) if detail is not None else None),
        )
        await conn.commit()
