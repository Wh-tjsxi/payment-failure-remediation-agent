"""Customer-complaint evidence connector.

Surfaces the customer's own free-text account of what happened, when one
was given at intake (`event_payload["complaint_text"]`). Unlike the other
connectors this never represents a *failed* fetch -- "the customer didn't
write anything" is just empty data, not a connector failure, so `missing`
always stays `False` here (never renders as "UNAVAILABLE (connector
failed)" in the diagnosis prompt).

Free text is useful context for diagnosis (root_cause/confidence) and,
through the diagnosis it feeds, for the runbook judge's reasoning -- but it
must never reach `policy/rules_engine.py`, which only looks up evidence by
the "gateway"/"case_history" keywords this source's name doesn't match.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Evidence


class CustomerComplaintConnector:
    async def fetch(self, case_id: str, event_payload: dict[str, str]) -> Evidence:
        complaint_text = event_payload.get("complaint_text", "")
        return Evidence(
            source="customer_complaint",
            data={"complaint_text": complaint_text} if complaint_text else {},
        )


@activity.defn(name="fetch_customer_complaint_evidence")
async def fetch_customer_complaint_evidence(
    case_id: str, event_payload: dict[str, str]
) -> Evidence:
    return await CustomerComplaintConnector().fetch(case_id, event_payload)
