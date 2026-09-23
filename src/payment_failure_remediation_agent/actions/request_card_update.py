"""Sprint 4 stub for asking the customer to update their card on file.

Real body (sending an update-payment-method request, e.g. email/notification)
lands in Sprint 7/8 alongside the other action implementations. Added in
Sprint 4 so the seeded runbook corpus can recommend an action name that
actually resolves to a registered Temporal activity.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import ActionResult


class RequestCardUpdateAction:
    async def execute(self, case_id: str, idempotency_key: str) -> ActionResult:
        return ActionResult(success=True, detail="request_card_update: stubbed success")


@activity.defn(name="request_card_update")
async def request_card_update(case_id: str, idempotency_key: str) -> ActionResult:
    return await RequestCardUpdateAction().execute(case_id, idempotency_key)
