"""Deterministic policy/risk engine (docs/DESIGN.md Sprint 5).

Non-LLM by design: `decide()` never sees a `Diagnosis`, only the runbook
entry and the raw evidence, so a miscategorized or hallucinated diagnosis
can never grant autonomy it shouldn't have. Rules run in a fixed order,
first match wins, and every outcome records which rule fired
(`PolicyDecision.rule_fired`) so the decision is always explainable.
"""

from temporalio import activity

from payment_failure_remediation_agent.models import Evidence, PolicyDecision, RunbookEntry

# Raw gateway decline codes that must never be auto-remediated, whatever the
# customer, amount, or matched runbook entry. Deliberately not derived from
# `Diagnosis.decline_category` -- `expired_card` is also a HARD_DECLINE but
# is safely fixable with a backup card, so the category can't drive this.
FRAUD_DECLINE_CODES = {"fraudulent", "stolen_card"}

# $100 or more always goes to a human, regardless of diagnosis or match
# quality.
AUTO_APPROVE_BELOW_AMOUNT = 100.0

# Risk tier per registered action activity name. An action not listed here
# (e.g. a runbook entry recommending something unrecognized) is treated as
# high-risk, never as an unlisted-therefore-safe default.
ACTION_RISK_TIERS = {
    "retry_payment": "low",
    "request_card_update": "low",
    "switch_backup_payment_method": "high",
    "issue_refund": "high",
    "toggle_feature_flag": "high",
}


def _find_evidence(evidence: list[Evidence], keyword: str) -> Evidence | None:
    """Looks up an evidence item by a substring of its source name.

    A successful connector reports the short source name ("gateway",
    "case_history"; see evidence_connectors/{gateway,case_history}.py), but
    a failed connector reaches the workflow as
    `Evidence(source=<activity name>, missing=True)` -- e.g.
    "fetch_gateway_evidence" -- via the workflow's own exception fallback.
    Both forms contain the same keyword, so substring match finds either.
    """
    return next((e for e in evidence if keyword in e.source), None)


def decide(runbook_entry: RunbookEntry, evidence: list[Evidence]) -> PolicyDecision:
    gateway = _find_evidence(evidence, "gateway")
    case_history = _find_evidence(evidence, "case_history")

    gateway_ok = gateway is not None and not gateway.missing
    decline_code = gateway.data.get("decline_code") if gateway_ok and gateway else None
    amount = gateway.data.get("amount") if gateway_ok and gateway else None

    # Rule 1: fraud hard block.
    if decline_code in FRAUD_DECLINE_CODES:
        return PolicyDecision(
            approved=False,
            reason=f"gateway decline_code {decline_code!r} is a fraud signal; never auto-remediated",
            rule_fired="fraud_hard_block",
            requires_approval=True,
        )

    # Rule 2: evidence missing/incomplete -- can't rule out fraud or check
    # the amount rule, so a human decides.
    if not gateway_ok or decline_code is None or amount is None:
        return PolicyDecision(
            approved=True,
            reason="gateway evidence missing or incomplete; cannot verify fraud/amount safely",
            rule_fired="evidence_missing_fail_safe",
            requires_approval=True,
        )

    # Rule 3: action risk tier.
    risk_tier = ACTION_RISK_TIERS.get(runbook_entry.recommended_action, "high")
    if risk_tier != "low":
        return PolicyDecision(
            approved=True,
            reason=f"action {runbook_entry.recommended_action!r} is risk tier {risk_tier!r}",
            rule_fired="high_risk_action",
            requires_approval=True,
        )

    # Rule 4: amount threshold.
    if float(amount) >= AUTO_APPROVE_BELOW_AMOUNT:  # type: ignore[arg-type]
        return PolicyDecision(
            approved=True,
            reason=f"amount {amount} is at or above the ${AUTO_APPROVE_BELOW_AMOUNT:.0f} auto-approve limit",
            rule_fired="amount_at_or_above_threshold",
            requires_approval=True,
        )

    # Rule 5: first attempt only. `.get()` (not truthiness alone) so a real
    # `False`/`0` reads as "first attempt", distinct from "unknown" (key
    # absent, or the whole evidence source missing).
    case_history_ok = case_history is not None and not case_history.missing
    prior_attempted = (
        case_history.data.get("prior_remediation_attempted")
        if case_history_ok and case_history
        else None
    )
    if not case_history_ok or prior_attempted is None or bool(prior_attempted):
        return PolicyDecision(
            approved=True,
            reason="prior remediation already attempted, or attempt history unknown",
            rule_fired="not_first_attempt_or_unknown_history",
            requires_approval=True,
        )

    # Otherwise: low-risk, non-fraud, evidence complete, under the amount
    # threshold, first attempt -- safe to run unattended.
    return PolicyDecision(
        approved=True,
        reason="low-risk first attempt under the auto-approve amount threshold",
        rule_fired="auto_approve_low_risk_first_attempt",
        requires_approval=False,
    )


@activity.defn(name="evaluate_policy")
async def evaluate_policy(
    case_id: str, runbook_entry: RunbookEntry, evidence: list[Evidence]
) -> PolicyDecision:
    return decide(runbook_entry, evidence)
