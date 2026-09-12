"""Sprint 1 stub for the deterministic policy/risk engine.

docs/DESIGN.md Section 2 calls for a non-LLM rules engine (spend limits,
customer tier, blast radius, compliance holds) whose output is always
explainable via `PolicyDecision.rule_fired`. Sprint 1 always approves --
the real rule table lands in Sprint 5. The hard-reject branch
(POLICY_RISK_CHECK -> CASE_ESCALATED, "no eligible remediation") lives in
the workflow's own if/else, not here, per the Sprint 1 plan.

Per the Section 1 state diagram, POLICY_RISK_CHECK runs on the runbook
candidate *before* REMEDIATION_PROPOSED synthesizes a full proposal (the
proposal generator then combines diagnosis + runbook + this policy
result) -- so this takes the runbook entry directly, not a
`RemediationProposal`.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Diagnosis, PolicyDecision, RunbookEntry


@activity.defn(name="evaluate_policy")
async def evaluate_policy(
    case_id: str, diagnosis: Diagnosis, runbook_entry: RunbookEntry
) -> PolicyDecision:
    return PolicyDecision(
        approved=True,
        reason="Sprint 1 stub: policy engine always approves",
        rule_fired="stub_always_approve",
    )
