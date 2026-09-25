"""Branch-coverage Temporal tests for `PaymentFailureCaseWorkflow`.

The happy-path test only ever proves one path through the Section 1
state diagram. This file proves every other one, using
`CaseInput.force_scenario` to override a stub activity's outcome for
branches that don't involve a human (policy hard-reject, execution
failure, verification not-resolved/reinvestigation, new runbook info),
and real injected signals -- combined with the time-skipping
environment's simulated clock -- for the human-in-the-loop branches
(runbook authoring, approval reject/SLA-escalation).

Same time-skipping environment and in-memory persistence fakes as
`test_workflow_happy_path.py`; the small amount of setup boilerplate is
duplicated rather than shared, since it's just the one other file.
"""

import asyncio
import shutil
import uuid

from temporalio import activity
from temporalio.client import WorkflowHandle
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from payment_failure_remediation_agent.actions import (
    issue_refund,
    retry_payment,
    toggle_feature_flag,
)
from payment_failure_remediation_agent.activities import (
    remediation_proposal_agent,
    resolution_analysis,
    verification,
)
from payment_failure_remediation_agent.activities.evidence_connectors import (
    case_history,
    customer_data,
    gateway,
    observability,
)
from payment_failure_remediation_agent.models import (
    ApprovalDecision,
    CaseInput,
    CaseStatus,
    DeclineCategory,
    Diagnosis,
    Evidence,
    RunbookEntry,
)
from payment_failure_remediation_agent.policy import rules_engine
from payment_failure_remediation_agent.workflows.payment_failure_case_workflow import (
    FORCE_EXECUTION_FAILS,
    FORCE_NEW_RUNBOOK_INFO,
    FORCE_NO_RUNBOOK_MATCH,
    FORCE_POLICY_HARD_REJECT,
    FORCE_VERIFICATION_NOT_RESOLVED,
    MAX_REINVESTIGATION_ATTEMPTS,
    PaymentFailureCaseWorkflow,
)
from payment_failure_remediation_agent.workflows.runbook_update_review_workflow import (
    RunbookUpdateReviewWorkflow,
)

TASK_QUEUE = "test-payment-failure-case-queue-branches"

# Same "use an already-installed CLI if present" fallback as the happy
# path test -- see that file for why.
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


# Same reasoning as test_workflow_happy_path.py's fake_diagnose: Sprint
# 3 made `diagnose` a real Claude activity, faked here so branch tests
# don't need ANTHROPIC_API_KEY to prove workflow logic.
@activity.defn(name="diagnose")
async def fake_diagnose(case_id: str, evidence: list[Evidence]) -> Diagnosis:
    return Diagnosis(
        root_cause="insufficient_funds",
        decline_category=DeclineCategory.FUNDS_ISSUE,
        confidence=0.9,
        evidence_cited=[e.source for e in evidence],
    )


# Sprint 4 made `retrieve_runbook_entry` need Postgres + Claude. Faked for the
# same reason as `diagnose`: these tests prove workflow logic, not retrieval
# (test_runbook_retrieval_golden_set.py covers the real thing).
@activity.defn(name="retrieve_runbook_entry")
async def fake_retrieve_runbook_entry(case_id: str, diagnosis: Diagnosis) -> RunbookEntry:
    return RunbookEntry(
        entry_id="RB-0001",
        title="Insufficient funds, standard customer, no backup card",
        recommended_action="retry_payment",
        match_found=True,
    )


ALL_ACTIVITIES = [
    gateway.fetch_gateway_evidence,
    observability.fetch_observability_evidence,
    customer_data.fetch_customer_data_evidence,
    case_history.fetch_case_history_evidence,
    fake_diagnose,
    fake_retrieve_runbook_entry,
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


async def _wait_for_status(
    handle: WorkflowHandle, status: CaseStatus, timeout_seconds: float = 10.0
) -> None:
    """Polls `get_status` until it matches, or raises after
    `timeout_seconds` of real wall-clock time.

    This is real-time polling from the *test process*, separate from the
    time-skipping environment's simulated workflow clock -- simulated
    time only auto-advances while the workflow is blocked purely on a
    timer, so polling a query still needs real (short) waits between
    checks regardless of the environment.
    """
    interval = 0.05
    elapsed = 0.0
    last_seen: CaseStatus | None = None
    while elapsed < timeout_seconds:
        last_seen = await handle.query(PaymentFailureCaseWorkflow.get_status)
        if last_seen == status:
            return
        await asyncio.sleep(interval)
        elapsed += interval
    raise AssertionError(f"timed out waiting for status {status}; last saw {last_seen}")


async def test_no_runbook_match_routes_to_human_authoring_then_closes() -> None:
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
            CaseInput(
                case_id=case_id,
                event_payload={},
                force_scenario=FORCE_NO_RUNBOOK_MATCH,
            ),
            id=f"case-{case_id}",
            task_queue=TASK_QUEUE,
        )

        await _wait_for_status(handle, CaseStatus.HUMAN_RUNBOOK_AUTHORING)
        await handle.signal(
            PaymentFailureCaseWorkflow.author_runbook,
            RunbookEntry(
                entry_id="RB-TEST",
                title="Test-authored entry",
                recommended_action="retry_payment",
                match_found=True,
            ),
        )

        await _wait_for_status(handle, CaseStatus.AWAITING_APPROVAL)
        await handle.signal(
            PaymentFailureCaseWorkflow.submit_approval,
            ApprovalDecision(decision="approve", approver="test-approver"),
        )

        assert await handle.result() == CaseStatus.CASE_CLOSED


async def test_policy_hard_reject_escalates() -> None:
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
            CaseInput(
                case_id=case_id,
                event_payload={},
                force_scenario=FORCE_POLICY_HARD_REJECT,
            ),
            id=f"case-{case_id}",
            task_queue=TASK_QUEUE,
        )

        assert await handle.result() == CaseStatus.CASE_ESCALATED


async def test_approval_reject_try_different_loops_back_then_closes() -> None:
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
            CaseInput(case_id=case_id, event_payload={}),
            id=f"case-{case_id}",
            task_queue=TASK_QUEUE,
        )

        # Round 1: reject and ask for a different remediation -- this must
        # loop back to RUNBOOK_RETRIEVAL and reach AWAITING_APPROVAL again,
        # not get stuck.
        await _wait_for_status(handle, CaseStatus.AWAITING_APPROVAL)
        await handle.signal(
            PaymentFailureCaseWorkflow.submit_approval,
            ApprovalDecision(
                decision="reject_try_different", approver="test-approver", reason="try again"
            ),
        )

        # Round 2: approve.
        await _wait_for_status(handle, CaseStatus.RUNBOOK_RETRIEVAL)
        await _wait_for_status(handle, CaseStatus.AWAITING_APPROVAL)
        await handle.signal(
            PaymentFailureCaseWorkflow.submit_approval,
            ApprovalDecision(decision="approve", approver="test-approver"),
        )

        assert await handle.result() == CaseStatus.CASE_CLOSED


async def test_approval_reject_no_automation_escalates() -> None:
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
            CaseInput(case_id=case_id, event_payload={}),
            id=f"case-{case_id}",
            task_queue=TASK_QUEUE,
        )

        await _wait_for_status(handle, CaseStatus.AWAITING_APPROVAL)
        await handle.signal(
            PaymentFailureCaseWorkflow.submit_approval,
            ApprovalDecision(
                decision="reject_no_automation", approver="test-approver", reason="too risky"
            ),
        )

        assert await handle.result() == CaseStatus.CASE_ESCALATED


async def test_approval_sla_escalations_exhausted() -> None:
    """No approval signal is ever sent -- the time-skipping environment
    fast-forwards through the SLA timers while `handle.result()` is
    awaited, and the workflow must self-escalate once escalations run
    out rather than waiting forever."""
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
            CaseInput(case_id=case_id, event_payload={}),
            id=f"case-{case_id}",
            task_queue=TASK_QUEUE,
        )

        assert await handle.result() == CaseStatus.CASE_ESCALATED


async def test_execution_fails_escalates() -> None:
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
            CaseInput(
                case_id=case_id,
                event_payload={},
                force_scenario=FORCE_EXECUTION_FAILS,
            ),
            id=f"case-{case_id}",
            task_queue=TASK_QUEUE,
        )

        await _wait_for_status(handle, CaseStatus.AWAITING_APPROVAL)
        await handle.signal(
            PaymentFailureCaseWorkflow.submit_approval,
            ApprovalDecision(decision="approve", approver="test-approver"),
        )

        assert await handle.result() == CaseStatus.CASE_ESCALATED


async def test_verification_not_resolved_reinvestigates_then_escalates() -> None:
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
            CaseInput(
                case_id=case_id,
                event_payload={},
                force_scenario=FORCE_VERIFICATION_NOT_RESOLVED,
            ),
            id=f"case-{case_id}",
            task_queue=TASK_QUEUE,
        )

        # Every attempt (the initial one plus every reinvestigation) fails
        # verification, so this needs one approval per round: the initial
        # attempt (attempt_count 0->1) plus MAX_REINVESTIGATION_ATTEMPTS
        # more before the workflow gives up and escalates.
        for _ in range(MAX_REINVESTIGATION_ATTEMPTS + 1):
            await _wait_for_status(handle, CaseStatus.AWAITING_APPROVAL)
            await handle.signal(
                PaymentFailureCaseWorkflow.submit_approval,
                ApprovalDecision(decision="approve", approver="test-approver"),
            )

        assert await handle.result() == CaseStatus.CASE_ESCALATED


async def test_new_runbook_info_spawns_review_child_workflow() -> None:
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
            CaseInput(
                case_id=case_id,
                event_payload={},
                force_scenario=FORCE_NEW_RUNBOOK_INFO,
            ),
            id=f"case-{case_id}",
            task_queue=TASK_QUEUE,
        )

        await _wait_for_status(handle, CaseStatus.AWAITING_APPROVAL)
        await handle.signal(
            PaymentFailureCaseWorkflow.submit_approval,
            ApprovalDecision(decision="approve", approver="test-approver"),
        )

        assert await handle.result() == CaseStatus.CASE_CLOSED

        # parent_close_policy=ABANDON means the child survives the parent
        # closing -- confirm it was actually started and is UnderReview.
        review_handle = env.client.get_workflow_handle(f"runbook-review-{case_id}")
        assert await review_handle.query(RunbookUpdateReviewWorkflow.get_status) == "UnderReview"
