"""Sprint 1 stub for the payment-gateway evidence connector.

Implements the `Connector` protocol from `base.py` with fixed fixture
data. Sprint 2 replaces `fetch`'s body with a real call against the
Payment Gateway Simulator -- the activity name/signature stay the same.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Evidence


class GatewayConnector:
    async def fetch(self, case_id: str) -> Evidence:
        return Evidence(
            source="gateway",
            data={"error_code": "card_declined", "decline_reason": "insufficient_funds"},
        )


@activity.defn(name="fetch_gateway_evidence")
async def fetch_gateway_evidence(case_id: str) -> Evidence:
    return await GatewayConnector().fetch(case_id)
