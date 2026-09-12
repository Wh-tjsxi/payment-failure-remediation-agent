"""Sprint 1 stub for the feature-flag/routing/fraud-threshold action
(medium-high risk tier).

Real body lands in Sprint 8. Registered as a Temporal activity under its
own name so the workflow can dispatch to it by
`RemediationProposal.action_name` alone.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import ActionResult


class ToggleFeatureFlagAction:
    async def execute(self, case_id: str, idempotency_key: str) -> ActionResult:
        return ActionResult(success=True, detail="toggle_feature_flag: stubbed success")


@activity.defn(name="toggle_feature_flag")
async def toggle_feature_flag(case_id: str, idempotency_key: str) -> ActionResult:
    return await ToggleFeatureFlagAction().execute(case_id, idempotency_key)
