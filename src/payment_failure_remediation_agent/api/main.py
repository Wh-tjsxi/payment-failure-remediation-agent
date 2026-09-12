"""FastAPI ingestion + polling API (Sprint 1 walking skeleton).

`POST /events/payment-failed` is the front door: dedupes on
`idempotency_key`, inserts the `cases` row, and starts the case
workflow. `GET /cases/{case_id}` lets the demo script (and, later, a
real dashboard) poll case status without going through the Temporal UI.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from psycopg.types.json import Jsonb
from pydantic import BaseModel
from temporalio.client import Client

from payment_failure_remediation_agent.config import (
    TASK_QUEUE,
    TEMPORAL_ADDRESS,
    TEMPORAL_NAMESPACE,
)
from payment_failure_remediation_agent.db import get_connection
from payment_failure_remediation_agent.models import CaseInput
from payment_failure_remediation_agent.workflows.payment_failure_case_workflow import (
    PaymentFailureCaseWorkflow,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.temporal_client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    yield


app = FastAPI(title="Payment Failure Remediation Agent", lifespan=lifespan)


class PaymentFailedEvent(BaseModel):
    idempotency_key: str
    payload: dict[str, str]
    # Injectable hook so the Sprint 1 verification script (and later
    # branch tests exercised end-to-end) can force a non-happy-path
    # outcome -- see workflows/payment_failure_case_workflow.py.
    force_scenario: str | None = None


class CaseResponse(BaseModel):
    case_id: str
    workflow_id: str
    status: str
    attempt_count: int


@app.post("/events/payment-failed", response_model=CaseResponse, status_code=201)
async def receive_payment_failed(event: PaymentFailedEvent, request: Request) -> CaseResponse:
    async with get_connection() as conn:
        cur = await conn.execute(
            "SELECT id, workflow_id, status, attempt_count FROM cases WHERE idempotency_key = %s",
            (event.idempotency_key,),
        )
        existing = await cur.fetchone()
        if existing is not None:
            case_id, workflow_id, status, attempt_count = existing
            return CaseResponse(
                case_id=case_id,
                workflow_id=workflow_id,
                status=status,
                attempt_count=attempt_count,
            )

        case_id = str(uuid.uuid4())
        workflow_id = f"case-{case_id}"
        await conn.execute(
            """
            INSERT INTO cases (id, idempotency_key, status, event_payload, workflow_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (case_id, event.idempotency_key, "CASE_CREATED", Jsonb(event.payload), workflow_id),
        )
        await conn.commit()

    temporal_client: Client = request.app.state.temporal_client
    await temporal_client.start_workflow(
        PaymentFailureCaseWorkflow.run,
        CaseInput(
            case_id=case_id,
            event_payload=event.payload,
            force_scenario=event.force_scenario,
        ),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return CaseResponse(case_id=case_id, workflow_id=workflow_id, status="CASE_CREATED", attempt_count=0)


@app.get("/cases/{case_id}", response_model=CaseResponse)
async def get_case(case_id: str) -> CaseResponse:
    async with get_connection() as conn:
        cur = await conn.execute(
            "SELECT id, workflow_id, status, attempt_count FROM cases WHERE id = %s",
            (case_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="case not found")
    found_case_id, workflow_id, status, attempt_count = row
    return CaseResponse(
        case_id=found_case_id,
        workflow_id=workflow_id,
        status=status,
        attempt_count=attempt_count,
    )
