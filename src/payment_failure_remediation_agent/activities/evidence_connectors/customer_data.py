"""Sprint 1 stub for the customer/account-data evidence connector.

Implements the `Connector` protocol from `base.py` with fixed fixture
data. Sprint 2 replaces `fetch`'s body with a real query against
synthetic customer/account records -- the activity name/signature stay
the same.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Evidence


class CustomerDataConnector:
    async def fetch(self, case_id: str) -> Evidence:
        return Evidence(
            source="customer_data",
            data={"account_status": "active", "disputes_flag": "none"},
        )


@activity.defn(name="fetch_customer_data_evidence")
async def fetch_customer_data_evidence(case_id: str) -> Evidence:
    return await CustomerDataConnector().fetch(case_id)
