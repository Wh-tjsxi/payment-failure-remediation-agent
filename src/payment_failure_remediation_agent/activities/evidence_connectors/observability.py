"""Sprint 1 stub for the observability (logs/traces/metrics) evidence connector.

Implements the `Connector` protocol from `base.py` with fixed fixture
data. Sprint 2 replaces `fetch`'s body with a real query against the
local OTel/Jaeger stack -- the activity name/signature stay the same.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Evidence


class ObservabilityConnector:
    async def fetch(self, case_id: str) -> Evidence:
        return Evidence(
            source="observability",
            data={"trace_id": "stub-trace-0001", "span_error": "timeout_calling_processor"},
        )


@activity.defn(name="fetch_observability_evidence")
async def fetch_observability_evidence(case_id: str) -> Evidence:
    return await ObservabilityConnector().fetch(case_id)
