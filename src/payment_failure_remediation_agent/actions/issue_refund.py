"""Sprint 1 stub for the refund/credit action (higher risk tier, maker-checker).

Real body lands in Sprint 8. Registered as a Temporal activity under its
own name so the workflow can dispatch to it by
`RemediationProposal.action_name` alone.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import ActionResult


class IssueRefundAction:
    async def execute(self, case_id: str, idempotency_key: str) -> ActionResult:
        return ActionResult(success=True, detail="issue_refund: stubbed success")


@activity.defn(name="issue_refund")
async def issue_refund(case_id: str, idempotency_key: str) -> ActionResult:
    return await IssueRefundAction().execute(case_id, idempotency_key)
