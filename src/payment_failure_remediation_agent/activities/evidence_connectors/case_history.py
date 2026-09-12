"""Sprint 1 stub for the prior-case-history evidence connector.

Implements the `Connector` protocol from `base.py` with fixed fixture
data. Sprint 2 replaces `fetch`'s body with a real query against the
`cases`/`audit_events` tables for this customer's prior cases -- the
activity name/signature stay the same.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Evidence


class CaseHistoryConnector:
    async def fetch(self, case_id: str) -> Evidence:
        return Evidence(
            source="case_history",
            data={"prior_cases": "0", "prior_similar_failures": "0"},
        )


@activity.defn(name="fetch_case_history_evidence")
async def fetch_case_history_evidence(case_id: str) -> Evidence:
    return await CaseHistoryConnector().fetch(case_id)
