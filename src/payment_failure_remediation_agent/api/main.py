"""FastAPI ingestion + polling API (Sprint 1 walking skeleton, grown in
Sprint 6a/6 with customer-resolution and admin-approval routes).

`POST /events/payment-failed` is the front door: dedupes on
`idempotency_key`, inserts the `cases` row, and starts the case
workflow. `GET /cases/{case_id}` lets the demo script poll raw case
status without going through the Temporal UI.

The newer routes split into two audiences, both reading the same
`approval_packet` audit row the workflow logs for every case (see
`workflows/payment_failure_case_workflow.py`, right after
`propose_remediation`):
- Customer-safe (`/cases/{case_id}/resolution`): never exposes *why* a
  case escalated or which policy rule fired -- computed server-side on
  purpose, not left to the frontend to hide fields client-side.
- Admin (`/cases`, `/cases/{case_id}/timeline`, `/approve`, `/reject`):
  full context, no redaction -- there is no auth yet (matches this
  project's standing no-auth-while-data-is-synthetic scope), so these
  are trusted equally with the CLI they replace for day-to-day use.
"""

import datetime
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from psycopg.types.json import Jsonb
from pydantic import BaseModel
from temporalio.client import Client

from payment_failure_remediation_agent.config import (
    FRONTEND_ORIGINS,
    TASK_QUEUE,
    TEMPORAL_ADDRESS,
    TEMPORAL_NAMESPACE,
)
from payment_failure_remediation_agent.db import get_connection
from payment_failure_remediation_agent.models import ApprovalDecision, CaseInput
from payment_failure_remediation_agent.workflows.payment_failure_case_workflow import (
    PaymentFailureCaseWorkflow,
)

# Mirrors policy.rules_engine.ACTION_RISK_TIERS's keys -- a human-readable
# sentence per action, never the raw action/rationale text (which is
# written for an internal/audit audience, not a customer-facing tone).
ACTION_CUSTOMER_MESSAGES = {
    "retry_payment": "We retried your payment and it went through successfully.",
    "switch_backup_payment_method": "We switched your payment to the backup method on file.",
    "request_card_update": "Your card appears to be expired — please update your card details.",
    "issue_refund": "We've issued a refund for this charge.",
    "toggle_feature_flag": "We adjusted a setting on our end to resolve this.",
}
DEFAULT_RESOLVED_MESSAGE = "We took action to resolve this issue."

# Same "never reveal why" reasoning as the customer page before this
# endpoint existed: neither status is fraud-specific (fraud escalates
# straight to CASE_ESCALATED without ever passing through
# AWAITING_APPROVAL; HUMAN_RUNBOOK_AUTHORING just means no runbook entry
# matched yet).
HUMAN_REVIEW_STATUSES = {"AWAITING_APPROVAL", "HUMAN_RUNBOOK_AUTHORING"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.temporal_client = await Client.connect(TEMPORAL_ADDRESS, namespace=TEMPORAL_NAMESPACE)
    yield


app = FastAPI(title="Payment Failure Remediation Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


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


class CaseSummary(BaseModel):
    case_id: str
    status: str
    attempt_count: int
    created_at: datetime.datetime


@app.get("/cases", response_model=list[CaseSummary])
async def list_cases(status: str | None = None) -> list[CaseSummary]:
    """Admin queue listing -- e.g. `GET /cases?status=AWAITING_APPROVAL`."""
    async with get_connection() as conn:
        if status is not None:
            cur = await conn.execute(
                "SELECT id, status, attempt_count, created_at FROM cases "
                "WHERE status = %s ORDER BY created_at ASC LIMIT 100",
                (status,),
            )
        else:
            cur = await conn.execute(
                "SELECT id, status, attempt_count, created_at FROM cases "
                "ORDER BY created_at ASC LIMIT 100"
            )
        rows = await cur.fetchall()
    return [
        CaseSummary(case_id=row[0], status=row[1], attempt_count=row[2], created_at=row[3])
        for row in rows
    ]


class AuditEventOut(BaseModel):
    from_status: str | None
    to_status: str
    detail: dict[str, Any] | None
    created_at: datetime.datetime


@app.get("/cases/{case_id}/timeline", response_model=list[AuditEventOut])
async def get_case_timeline(case_id: str) -> list[AuditEventOut]:
    """Full audit trail for the admin case-detail view -- includes the
    `approval_packet` row (diagnosis, runbook match, policy rule, proposed
    action) logged by the workflow for every case."""
    async with get_connection() as conn:
        cur = await conn.execute(
            "SELECT from_status, to_status, detail, created_at FROM audit_events "
            "WHERE case_id = %s ORDER BY created_at ASC",
            (case_id,),
        )
        rows = await cur.fetchall()
    return [
        AuditEventOut(from_status=row[0], to_status=row[1], detail=row[2], created_at=row[3])
        for row in rows
    ]


class ApproveRequest(BaseModel):
    approver: str


class RejectRequest(BaseModel):
    approver: str
    decision: Literal["reject_try_different", "reject_no_automation"]
    reason: str = ""


@app.post("/cases/{case_id}/approve")
async def approve_case(case_id: str, body: ApproveRequest, request: Request) -> dict[str, bool]:
    """Same signal `cli.py`'s `approve` subcommand sends -- the admin
    portal replaces the terminal, not the signal mechanism."""
    temporal_client: Client = request.app.state.temporal_client
    handle = temporal_client.get_workflow_handle(f"case-{case_id}")
    await handle.signal(
        "submit_approval", ApprovalDecision(decision="approve", approver=body.approver)
    )
    return {"ok": True}


@app.post("/cases/{case_id}/reject")
async def reject_case(case_id: str, body: RejectRequest, request: Request) -> dict[str, bool]:
    temporal_client: Client = request.app.state.temporal_client
    handle = temporal_client.get_workflow_handle(f"case-{case_id}")
    await handle.signal(
        "submit_approval",
        ApprovalDecision(decision=body.decision, approver=body.approver, reason=body.reason),
    )
    return {"ok": True}


class ResolutionResponse(BaseModel):
    customer_status: Literal["in_progress", "being_reviewed", "resolved", "escalated"]
    message: str


@app.get("/cases/{case_id}/resolution", response_model=ResolutionResponse)
async def get_case_resolution(case_id: str) -> ResolutionResponse:
    """Customer-safe status, computed server-side -- never exposes which
    policy rule fired or why a case escalated, and for a resolved case
    names the actual action taken instead of a generic "resolved"."""
    async with get_connection() as conn:
        cur = await conn.execute("SELECT status FROM cases WHERE id = %s", (case_id,))
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="case not found")
        status = row[0]

        if status != "CASE_CLOSED":
            if status == "CASE_ESCALATED":
                return ResolutionResponse(
                    customer_status="escalated",
                    message="We need a closer look at your case. Please contact support.",
                )
            if status in HUMAN_REVIEW_STATUSES:
                return ResolutionResponse(
                    customer_status="being_reviewed",
                    message="Your case is being reviewed by our team.",
                )
            return ResolutionResponse(
                customer_status="in_progress", message="We're looking into it."
            )

        packet_cur = await conn.execute(
            """
            SELECT detail FROM audit_events
            WHERE case_id = %s AND detail->>'event' = 'approval_packet'
            ORDER BY created_at DESC LIMIT 1
            """,
            (case_id,),
        )
        packet_row = await packet_cur.fetchone()

    action_name = packet_row[0].get("action_name") if packet_row else None
    message = (
        ACTION_CUSTOMER_MESSAGES.get(action_name, DEFAULT_RESOLVED_MESSAGE)
        if isinstance(action_name, str)
        else DEFAULT_RESOLVED_MESSAGE
    )
    return ResolutionResponse(customer_status="resolved", message=message)
