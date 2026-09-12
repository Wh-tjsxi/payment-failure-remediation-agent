"""Sprint 1 stub for the retry/reprocess-payment action (lower risk tier).

Real body (idempotent retry against the Payment Gateway Simulator) lands
in Sprint 7. Registered as a Temporal activity under its own name so the
workflow can dispatch to it by `RemediationProposal.action_name` alone.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import ActionResult


class RetryPaymentAction:
    async def execute(self, case_id: str, idempotency_key: str) -> ActionResult:
        return ActionResult(success=True, detail="retry_payment: stubbed success")


@activity.defn(name="retry_payment")
async def retry_payment(case_id: str, idempotency_key: str) -> ActionResult:
    return await RetryPaymentAction().execute(case_id, idempotency_key)
