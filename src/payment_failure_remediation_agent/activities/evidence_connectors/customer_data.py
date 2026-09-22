"""Customer/account-data evidence connector (docs/DESIGN.md Section 3, Sprint 2).

Surfaces proprietary, merchant-side fields a real payment processor
structurally can't see -- `customer_tier` and `has_backup_payment_method`
-- each chosen because it flips the correct remediation for an otherwise
identical decline code. Data comes from the case's scripted scenario,
keyed the same way as the gateway connector.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Evidence
from payment_failure_remediation_agent.simulator import get_scenario


class CustomerDataConnector:
    async def fetch(self, case_id: str, event_payload: dict[str, str]) -> Evidence:
        scenario = get_scenario(event_payload.get("scenario"))
        return Evidence(source="customer_data", data=dict(scenario.customer_data))


@activity.defn(name="fetch_customer_data_evidence")
async def fetch_customer_data_evidence(case_id: str, event_payload: dict[str, str]) -> Evidence:
    return await CustomerDataConnector().fetch(case_id, event_payload)
