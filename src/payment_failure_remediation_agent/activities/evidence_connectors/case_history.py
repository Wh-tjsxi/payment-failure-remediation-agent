"""Prior-case-history evidence connector (docs/DESIGN.md Section 3, Sprint 2).

Surfaces `prior_remediation_attempted` from the case's scripted scenario --
stops the system from proposing an already-failed fix twice. Stands in for
a real query against this system's own `cases`/`audit_events` tables,
which Sprint 2 deliberately defers: there's no `customer_id` column yet to
key that query on, and nothing in this sprint needs it (docs/DESIGN.md
Section 3's DB-schema recommendation).
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Evidence
from payment_failure_remediation_agent.simulator import get_scenario


class CaseHistoryConnector:
    async def fetch(self, case_id: str, event_payload: dict[str, str]) -> Evidence:
        scenario = get_scenario(event_payload.get("scenario"))
        return Evidence(source="case_history", data=dict(scenario.case_history))


@activity.defn(name="fetch_case_history_evidence")
async def fetch_case_history_evidence(case_id: str, event_payload: dict[str, str]) -> Evidence:
    return await CaseHistoryConnector().fetch(case_id, event_payload)
