"""Sprint 1 stub for the remediation proposal generator.

Real body (Claude combining diagnosis + runbook + policy into a concrete
proposal) lands alongside real diagnosis/runbook logic in later sprints.
Always proposes the runbook entry's own recommended action, so
`RemediationProposal.action_name` lines up with a real action activity
name (see `actions/base.py`).
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Diagnosis, RemediationProposal, RunbookEntry


@activity.defn(name="propose_remediation")
async def propose_remediation(
    case_id: str, diagnosis: Diagnosis, runbook_entry: RunbookEntry
) -> RemediationProposal:
    return RemediationProposal(
        action_name=runbook_entry.recommended_action,
        rationale=f"Runbook {runbook_entry.entry_id} recommends this for {diagnosis.root_cause}",
        risk_tier="auto",
    )
