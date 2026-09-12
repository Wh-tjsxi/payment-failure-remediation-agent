"""Core case-lifecycle workflow (docs/DESIGN.md Section 1).

One execution per Case. Every step's *logic* is stubbed per the Sprint 1
plan (fixture evidence, fixed diagnosis, hardcoded runbook match,
always-approve policy, no-op executor, always-resolved verification) --
but every state/transition/signal-gate in the design's state diagram is
real, wired code. A single demo run only ever traverses the happy path;
every other branch is proven by `tests/test_workflow_branches.py`, using
`CaseInput.force_scenario` to override a stub activity's outcome, or a
real injected signal for the human-in-the-loop branches.

Uses Temporal's own execution history as the state machine -- no separate
state-machine library, just ordinary Python control flow (`while` loops
for the SLA-escalation, "try a different remediation", and reinvestigation
loops).
"""

import asyncio
from dataclasses import replace
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from payment_failure_remediation_agent.models import (
    ActionResult,
    ApprovalDecision,
    CaseInput,
    CaseStatus,
    Diagnosis,
    Evidence,
    PolicyDecision,
    RemediationProposal,
    ResolutionAnalysis,
    RunbookEntry,
    RunbookReviewInput,
    Verification,
)
from payment_failure_remediation_agent.workflows.runbook_update_review_workflow import (
    RunbookUpdateReviewWorkflow,
)

DEFAULT_ACTIVITY_TIMEOUT = timedelta(seconds=30)
DEFAULT_RETRY_POLICY = RetryPolicy(maximum_attempts=3)

# How long AWAITING_APPROVAL waits for a signal before escalating to the
# next approval tier (docs/DESIGN.md's "Escalated_SLA -> notify next
# tier" loop). Sized for a real approval queue, not this sprint's <60s
# happy-path demo -- the demo always signals well before this fires.
APPROVAL_SLA = timedelta(hours=4)
MAX_APPROVAL_ESCALATIONS = 2
MAX_REINVESTIGATION_ATTEMPTS = 3

# CaseInput.force_scenario values used by branch tests to override a
# stub activity's hardcoded outcome. Approval-signal branches
# (reject/SLA-timeout) don't need a flag here -- branch tests drive those
# by literally sending a different signal instead.
FORCE_NO_RUNBOOK_MATCH = "no_runbook_match"
FORCE_POLICY_HARD_REJECT = "policy_hard_reject"
FORCE_EXECUTION_FAILS = "execution_fails"
FORCE_VERIFICATION_NOT_RESOLVED = "verification_not_resolved"
FORCE_NEW_RUNBOOK_INFO = "new_runbook_info"


@workflow.defn
class PaymentFailureCaseWorkflow:
    def __init__(self) -> None:
        self.status: CaseStatus = CaseStatus.CASE_CREATED
        self._runbook_authoring_entry: RunbookEntry | None = None
        self._approval_decision: ApprovalDecision | None = None

    @workflow.query
    def get_status(self) -> CaseStatus:
        return self.status

    @workflow.signal
    async def author_runbook(self, entry: RunbookEntry) -> None:
        self._runbook_authoring_entry = entry

    @workflow.signal
    async def submit_approval(self, decision: ApprovalDecision) -> None:
        self._approval_decision = decision

    async def _transition(
        self,
        case_id: str,
        to_status: CaseStatus,
        attempt_count: int,
        detail: dict[str, str] | None = None,
    ) -> None:
        from_status = self.status
        self.status = to_status
        await workflow.execute_activity(
            "persist_case_status",
            args=[case_id, to_status.value, attempt_count],
            start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY_POLICY,
        )
        await workflow.execute_activity(
            "append_audit_event",
            args=[case_id, from_status.value, to_status.value, detail],
            start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY_POLICY,
        )

    async def _audit(self, case_id: str, detail: dict[str, str]) -> None:
        """Append an audit row without a real state change (e.g. an SLA
        escalation notice) -- from_status/to_status both stay the current
        status."""
        await workflow.execute_activity(
            "append_audit_event",
            args=[case_id, self.status.value, self.status.value, detail],
            start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY_POLICY,
        )

    async def _collect_evidence(self, case_id: str) -> list[Evidence]:
        activity_names = [
            "fetch_gateway_evidence",
            "fetch_observability_evidence",
            "fetch_customer_data_evidence",
            "fetch_case_history_evidence",
        ]
        results = await asyncio.gather(
            *[
                workflow.execute_activity(
                    name,
                    args=[case_id],
                    result_type=Evidence,
                    start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )
                for name in activity_names
            ],
            return_exceptions=True,
        )
        evidence: list[Evidence] = []
        for name, result in zip(activity_names, results):
            if isinstance(result, BaseException):
                evidence.append(Evidence(source=name, data={}, missing=True))
            else:
                evidence.append(result)
        return evidence

    async def _await_approval(self, case_id: str) -> ApprovalDecision | None:
        """Waits for `submit_approval`, escalating to the next tier on each
        SLA timeout. Returns None once escalations are exhausted.

        `_approval_decision` is cleared only *after* being consumed, never
        before waiting -- clearing it first would risk wiping out a
        decision that arrives while this round's earlier activities
        (RUNBOOK_RETRIEVAL/POLICY_RISK_CHECK/REMEDIATION_PROPOSED) are
        still in flight, since a signal can be delivered at any await
        point, not just once this method is actually waiting.
        """
        escalation_level = 0
        while True:
            try:
                await workflow.wait_condition(
                    lambda: self._approval_decision is not None, timeout=APPROVAL_SLA
                )
            except TimeoutError:
                escalation_level += 1
                if escalation_level > MAX_APPROVAL_ESCALATIONS:
                    return None
                await self._audit(
                    case_id,
                    {"event": "sla_escalation", "level": str(escalation_level)},
                )
                continue
            decision = self._approval_decision
            self._approval_decision = None
            return decision

    @workflow.run
    async def run(self, case_input: CaseInput) -> CaseStatus:
        case_id = case_input.case_id
        attempt_count = 0

        # First audit row has from_status=NULL, so it's written directly
        # rather than through _transition (which always reads self.status,
        # already CASE_CREATED, as "from").
        await workflow.execute_activity(
            "persist_case_status",
            args=[case_id, CaseStatus.CASE_CREATED.value, attempt_count],
            start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY_POLICY,
        )
        await workflow.execute_activity(
            "append_audit_event",
            args=[case_id, None, CaseStatus.CASE_CREATED.value, None],
            start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        while True:  # reinvestigation loop
            await self._transition(case_id, CaseStatus.EVIDENCE_COLLECTION, attempt_count)
            evidence = await self._collect_evidence(case_id)

            await self._transition(case_id, CaseStatus.DIAGNOSIS, attempt_count)
            diagnosis: Diagnosis = await workflow.execute_activity(
                "diagnose",
                args=[case_id, evidence],
                result_type=Diagnosis,
                start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )

            runbook_entry: RunbookEntry
            proposal: RemediationProposal

            while True:  # candidate loop: "try a different remediation" loops back here
                await self._transition(case_id, CaseStatus.RUNBOOK_RETRIEVAL, attempt_count)
                runbook_entry = await workflow.execute_activity(
                    "retrieve_runbook_entry",
                    args=[case_id, diagnosis],
                    result_type=RunbookEntry,
                    start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )
                if case_input.force_scenario == FORCE_NO_RUNBOOK_MATCH:
                    runbook_entry = replace(runbook_entry, match_found=False)

                if not runbook_entry.match_found:
                    await self._transition(
                        case_id, CaseStatus.HUMAN_RUNBOOK_AUTHORING, attempt_count
                    )
                    # Same non-reset-before-waiting rule as _await_approval:
                    # clear only after consuming, so an eager signal that
                    # lands during the transition's own awaits isn't lost.
                    await workflow.wait_condition(
                        lambda: self._runbook_authoring_entry is not None
                    )
                    authored_entry = self._runbook_authoring_entry
                    self._runbook_authoring_entry = None
                    assert authored_entry is not None
                    runbook_entry = authored_entry

                await self._transition(case_id, CaseStatus.POLICY_RISK_CHECK, attempt_count)
                policy_decision = await workflow.execute_activity(
                    "evaluate_policy",
                    args=[case_id, diagnosis, runbook_entry],
                    result_type=PolicyDecision,
                    start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )
                if case_input.force_scenario == FORCE_POLICY_HARD_REJECT:
                    policy_decision = replace(
                        policy_decision,
                        approved=False,
                        reason="forced hard reject for branch test",
                        rule_fired="forced_scenario",
                    )

                if not policy_decision.approved:
                    await self._transition(
                        case_id,
                        CaseStatus.CASE_ESCALATED,
                        attempt_count,
                        detail={
                            "reason": "policy_hard_reject",
                            "rule_fired": policy_decision.rule_fired,
                        },
                    )
                    return CaseStatus.CASE_ESCALATED

                await self._transition(case_id, CaseStatus.REMEDIATION_PROPOSED, attempt_count)
                proposal = await workflow.execute_activity(
                    "propose_remediation",
                    args=[case_id, diagnosis, runbook_entry],
                    result_type=RemediationProposal,
                    start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )

                await self._transition(case_id, CaseStatus.AWAITING_APPROVAL, attempt_count)
                approval_decision = await self._await_approval(case_id)

                if approval_decision is None:
                    await self._transition(
                        case_id,
                        CaseStatus.CASE_ESCALATED,
                        attempt_count,
                        detail={"reason": "approval_sla_escalations_exhausted"},
                    )
                    return CaseStatus.CASE_ESCALATED
                if approval_decision.decision == "approve":
                    break
                if approval_decision.decision == "reject_try_different":
                    continue
                await self._transition(
                    case_id,
                    CaseStatus.CASE_ESCALATED,
                    attempt_count,
                    detail={
                        "reason": "approval_reject_no_automation",
                        "approver": approval_decision.approver,
                    },
                )
                return CaseStatus.CASE_ESCALATED

            await self._transition(case_id, CaseStatus.EXECUTING, attempt_count)
            idempotency_key = str(workflow.uuid4())
            action_result: ActionResult = await workflow.execute_activity(
                proposal.action_name,
                args=[case_id, idempotency_key],
                result_type=ActionResult,
                start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            if case_input.force_scenario == FORCE_EXECUTION_FAILS:
                action_result = replace(
                    action_result, success=False, detail="forced execution failure"
                )

            if not action_result.success:
                await self._transition(
                    case_id,
                    CaseStatus.CASE_ESCALATED,
                    attempt_count,
                    detail={
                        "reason": "execution_retries_exhausted",
                        "detail": action_result.detail,
                    },
                )
                return CaseStatus.CASE_ESCALATED

            await self._transition(case_id, CaseStatus.VERIFICATION, attempt_count)
            verification: Verification = await workflow.execute_activity(
                "verify_resolution",
                args=[case_id, action_result],
                result_type=Verification,
                start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            if case_input.force_scenario == FORCE_VERIFICATION_NOT_RESOLVED:
                verification = replace(verification, resolved=False, detail="forced not-resolved")

            if verification.resolved:
                await self._transition(case_id, CaseStatus.RESOLUTION_ANALYSIS, attempt_count)
                resolution: ResolutionAnalysis = await workflow.execute_activity(
                    "analyze_resolution",
                    args=[case_id, verification],
                    result_type=ResolutionAnalysis,
                    start_to_close_timeout=DEFAULT_ACTIVITY_TIMEOUT,
                    retry_policy=DEFAULT_RETRY_POLICY,
                )
                if case_input.force_scenario == FORCE_NEW_RUNBOOK_INFO:
                    resolution = replace(
                        resolution, new_info_found=True, summary="forced new info found"
                    )

                if resolution.new_info_found:
                    await workflow.start_child_workflow(
                        RunbookUpdateReviewWorkflow.run,
                        RunbookReviewInput(case_id=case_id, proposed_entry=runbook_entry),
                        id=f"runbook-review-{case_id}",
                        parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                    )

                await self._transition(case_id, CaseStatus.CASE_CLOSED, attempt_count)
                return CaseStatus.CASE_CLOSED

            attempt_count += 1
            if attempt_count > MAX_REINVESTIGATION_ATTEMPTS:
                await self._transition(
                    case_id,
                    CaseStatus.CASE_ESCALATED,
                    attempt_count,
                    detail={
                        "reason": "max_reinvestigation_attempts_exceeded",
                        "attempt_count": str(attempt_count),
                    },
                )
                return CaseStatus.CASE_ESCALATED

            await self._transition(
                case_id,
                CaseStatus.REINVESTIGATION,
                attempt_count,
                detail={"attempt_count": str(attempt_count)},
            )
            # loop back to the top: another evidence-collection pass
