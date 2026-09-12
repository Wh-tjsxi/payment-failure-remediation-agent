"""Sprint 1 stub for the diagnosis agent.

Real body (Claude reasoning over evidence, schema-validated output) lands
in Sprint 3. Always returns the same fixed `Diagnosis` regardless of the
evidence passed in.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Diagnosis, Evidence


@activity.defn(name="diagnose")
async def diagnose(case_id: str, evidence: list[Evidence]) -> Diagnosis:
    return Diagnosis(
        root_cause="insufficient_funds",
        confidence=0.9,
        evidence_cited=[e.source for e in evidence],
    )
