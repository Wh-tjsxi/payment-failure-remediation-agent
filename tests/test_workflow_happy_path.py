"""Happy-path Temporal test for `PaymentFailureCaseWorkflow`.

Runs the full case lifecycle against Temporal's time-skipping test
environment (`temporalio.testing.WorkflowEnvironment`) -- no
docker-compose stack, no real Postgres required. The two real
(Postgres-backed) persistence activities are swapped for in-memory
fakes registered under the same activity names, so this test exercises
workflow logic in isolation from the DB.

This also satisfies the outstanding CLAUDE.md Sprint 0 gap ("add a
trivial passing test so CI has something to gate on") -- no separate
throwaway test needed.
"""

import shutil
import uuid

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from payment_failure_remediation_agent.actions import (
    issue_refund,
    retry_payment,
    toggle_feature_flag,
)
from payment_failure_remediation_agent.activities import (
    diagnosis_agent,
    remediation_proposal_agent,
    resolution_analysis,
    runbook_retrieval,
    verification,
)
from payment_failure_remediation_agent.activities.evidence_connectors import (
    case_history,
    customer_data,
    gateway,
    observability,
)
from payment_failure_remediation_agent.models import ApprovalDecision, CaseInput, CaseStatus
from payment_failure_remediation_agent.policy import rules_engine
from payment_failure_remediation_agent.workflows.payment_failure_case_workflow import (
    PaymentFailureCaseWorkflow,
)
from payment_failure_remediation_agent.workflows.runbook_update_review_workflow import (
    RunbookUpdateReviewWorkflow,
)

TASK_QUEUE = "test-payment-failure-case-queue"

# Use an already-installed `temporal` CLI as the time-skipping test
# server if one is on PATH, instead of always letting the SDK download
# its own copy from temporal.download -- falls back to the normal
# download when none is found (e.g. in CI), so this stays portable.
_EXISTING_TEMPORAL_BINARY = shutil.which("temporal")


@activity.defn(name="persist_case_status")
async def fake_persist_case_status(case_id: str, status: str, attempt_count: int) -> None:
    pass


@activity.defn(name="append_audit_event")
async def fake_append_audit_event(
    case_id: str,
    from_status: str | None,
    to_status: str,
    detail: dict[str, str] | None,
) -> None:
    pass


ALL_ACTIVITIES = [
    gateway.fetch_gateway_evidence,
    observability.fetch_observability_evidence,
    customer_data.fetch_customer_data_evidence,
    case_history.fetch_case_history_evidence,
    diagnosis_agent.diagnose,
    runbook_retrieval.retrieve_runbook_entry,
    rules_engine.evaluate_policy,
    remediation_proposal_agent.propose_remediation,
    retry_payment.retry_payment,
    issue_refund.issue_refund,
    toggle_feature_flag.toggle_feature_flag,
    verification.verify_resolution,
    resolution_analysis.analyze_resolution,
    fake_persist_case_status,
    fake_append_audit_event,
]


async def test_happy_path_reaches_case_closed() -> None:
    async with await WorkflowEnvironment.start_time_skipping(
        test_server_existing_path=_EXISTING_TEMPORAL_BINARY
    ) as env, Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[PaymentFailureCaseWorkflow, RunbookUpdateReviewWorkflow],
        activities=ALL_ACTIVITIES,
    ):
        case_id = str(uuid.uuid4())
        handle = await env.client.start_workflow(
            PaymentFailureCaseWorkflow.run,
            CaseInput(case_id=case_id, event_payload={"error_code": "card_declined"}),
            id=f"case-{case_id}",
            task_queue=TASK_QUEUE,
        )

        await handle.signal(
            PaymentFailureCaseWorkflow.submit_approval,
            ApprovalDecision(decision="approve", approver="test-approver"),
        )

        result = await handle.result()

        assert result == CaseStatus.CASE_CLOSED
        assert await handle.query(PaymentFailureCaseWorkflow.get_status) == (
            CaseStatus.CASE_CLOSED
        )
