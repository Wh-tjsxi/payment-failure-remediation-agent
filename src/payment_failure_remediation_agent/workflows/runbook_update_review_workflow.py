"""Runbook knowledge-curation child workflow (docs/DESIGN.md Section 1).

Spawned by `PaymentFailureCaseWorkflow` only when resolution analysis
finds something the runbook didn't already know -- fire-and-forget
(`parent_close_policy=ABANDON`) so the parent case can close immediately
without waiting on a human reviewer. Implements the design's
`UnderReview -> Merged/Discarded` states, with a self-loop back to
`UnderReview` on "changes requested".
"""

from temporalio import workflow

from payment_failure_remediation_agent.models import RunbookReviewDecision, RunbookReviewInput


@workflow.defn
class RunbookUpdateReviewWorkflow:
    def __init__(self) -> None:
        self.status: str = "UnderReview"
        self._decision: RunbookReviewDecision | None = None

    @workflow.query
    def get_status(self) -> str:
        return self.status

    @workflow.signal
    async def submit_review_decision(self, decision: RunbookReviewDecision) -> None:
        self._decision = decision

    @workflow.run
    async def run(self, review_input: RunbookReviewInput) -> str:
        while True:
            self._decision = None
            await workflow.wait_condition(lambda: self._decision is not None)
            decision = self._decision
            assert decision is not None

            if decision.decision == "approve":
                self.status = "Merged"
                return self.status
            if decision.decision == "reject":
                self.status = "Discarded"
                return self.status
            # "request_changes" -> self-loop, stays UnderReview
