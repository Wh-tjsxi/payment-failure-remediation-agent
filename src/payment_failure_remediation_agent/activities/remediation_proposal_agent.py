"""Remediation proposal generator (docs/DESIGN.md Sprint 5, Phase 3).

Deterministic, not an LLM call: the runbook judge (`runbook/judge.py`) has
already made the one real judgment call -- which action fits, and why -- so
a second LLM call here would just restate that reasoning at extra cost and
latency with no new decision made. Reuses `ACTION_RISK_TIERS` directly from
the policy engine so risk tier has one source of truth, not a second copy
that could drift from it.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import RemediationProposal, RunbookEntry
from payment_failure_remediation_agent.policy.rules_engine import ACTION_RISK_TIERS


@activity.defn(name="propose_remediation")
async def propose_remediation(case_id: str, runbook_entry: RunbookEntry) -> RemediationProposal:
    return RemediationProposal(
        action_name=runbook_entry.recommended_action,
        rationale=runbook_entry.reason or f"Runbook {runbook_entry.entry_id} recommends this action",
        risk_tier=ACTION_RISK_TIERS.get(runbook_entry.recommended_action, "high"),
    )
