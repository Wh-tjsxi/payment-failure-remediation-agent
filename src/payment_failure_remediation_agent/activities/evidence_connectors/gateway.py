"""Payment-gateway evidence connector (docs/DESIGN.md Section 3, Sprint 2).

Looks up the case's scripted scenario -- keyed by `event_payload["scenario"]`,
defaulting to the standard-customer/insufficient-funds scenario when none is
given -- and returns that scenario's gateway-side evidence: the raw decline
code, amount, and currency a real Stripe/Adyen webhook would carry. Never
the decline-category classification itself; that's Sprint 3's job.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Evidence
from payment_failure_remediation_agent.simulator import get_scenario


class GatewayConnector:
    async def fetch(self, case_id: str, event_payload: dict[str, str]) -> Evidence:
        scenario = get_scenario(event_payload.get("scenario"))
        return Evidence(source="gateway", data=dict(scenario.gateway))


@activity.defn(name="fetch_gateway_evidence")
async def fetch_gateway_evidence(case_id: str, event_payload: dict[str, str]) -> Evidence:
    return await GatewayConnector().fetch(case_id, event_payload)
