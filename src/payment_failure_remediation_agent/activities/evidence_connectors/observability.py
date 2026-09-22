"""Observability (logs/traces/metrics) evidence connector.

Still a stub in Sprint 2 -- the decline-code taxonomy and proprietary
customer/case-history evidence (docs/DESIGN.md Section 3) are this
sprint's actual scope; real OTel/Jaeger integration is deferred, since
it doesn't change any remediation decision the MVP needs to demonstrate.
Signature matches the other three connectors (`Connector` protocol, now
`fetch(case_id, event_payload)`) so the workflow can keep dispatching
all four uniformly.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Evidence


class ObservabilityConnector:
    async def fetch(self, case_id: str, event_payload: dict[str, str]) -> Evidence:
        return Evidence(
            source="observability",
            data={"trace_id": "stub-trace-0001", "span_error": "timeout_calling_processor"},
        )


@activity.defn(name="fetch_observability_evidence")
async def fetch_observability_evidence(case_id: str, event_payload: dict[str, str]) -> Evidence:
    return await ObservabilityConnector().fetch(case_id, event_payload)
