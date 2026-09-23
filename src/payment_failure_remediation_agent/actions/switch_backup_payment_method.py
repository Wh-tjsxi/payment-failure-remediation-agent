"""Sprint 4 stub for switching a case to the customer's backup payment method.

Real body (charging the backup instrument via the Payment Gateway Simulator)
lands in Sprint 7/8 alongside the other action implementations. Added in
Sprint 4 so the seeded runbook corpus can recommend an action name that
actually resolves to a registered Temporal activity.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import ActionResult


class SwitchBackupPaymentMethodAction:
    async def execute(self, case_id: str, idempotency_key: str) -> ActionResult:
        return ActionResult(
            success=True, detail="switch_backup_payment_method: stubbed success"
        )


@activity.defn(name="switch_backup_payment_method")
async def switch_backup_payment_method(
    case_id: str, idempotency_key: str
) -> ActionResult:
    return await SwitchBackupPaymentMethodAction().execute(case_id, idempotency_key)
